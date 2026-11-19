"""Export an ended run's whole record before the collector removes it.

The collector deletes a closed item's run from its factory server, and the run's
event journal and stage logs go with it. Run 01M7M6EPWDJT (bd-ib-s65bd2) was
collected that way and a wrong-item commit it produced could no longer be
diagnosed. This module is the export the deletion now waits for: `fabro dump`
writes the run into one directory per run under a fixed root, a MANIFEST.json
names every file with its size and sha256, and the manifest is read back against
the files before the export counts as done.

The deletion itself is unchanged: `contracts.md` says a closed item's run MUST be
deleted, so a FAILED export never defers it. The caller journals the failing
step and the run is removed anyway; the export is best effort by design and the
journal row is what makes a missing export visible.

The root is a fixed constant under the repository's `tmp/`, which is on disk and
beside the dispatch journal. It is deliberately not a setting: the ratified
settings are enumerated, and a retention a test pinned would be a config-value
test. Exports older than the retention constant are pruned on every pass.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_runs_export import (
    LedgerComments,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort
from livespec_orchestrator_beads_fabro.effects import attempt
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
    WorkItemNotFoundError,
)

__all__: list[str] = [
    "EXPORT_CEILING_BYTES",
    "EXPORT_FREE_SPACE_MULTIPLE",
    "EXPORT_RETENTION_SECONDS",
    "EXPORT_ROOT",
    "MIN_FREE_BYTES",
    "MIN_FREE_FRACTION",
    "DiskPressure",
    "EndedRunExport",
    "disk_pressure",
    "export_ended_run",
    "export_run_before_removal",
    "prune_expired_exports",
    "report_export_hold",
]

EXPORT_ROOT = Path("tmp") / "ended-run-exports"
# Seven days, measured against the host rather than chosen for comfort: a failed
# run exports about 0.2 MB per run-minute plus about 4 MB fixed, to a ceiling near
# 100 MB (n=3 failed runs, no succeeded run measured), and the dispatching
# host's disk was at 90% with 69 GB free on 2026-11-17.
EXPORT_RETENTION_SECONDS = 7 * 24 * 3600
# The measured per-export ceiling. The free-space floor below is a multiple of it,
# so the floor follows the ceiling instead of being a second number to keep in step.
EXPORT_CEILING_BYTES = 100 * 1024 * 1024
EXPORT_FREE_SPACE_MULTIPLE = 20
MIN_FREE_BYTES = EXPORT_CEILING_BYTES * EXPORT_FREE_SPACE_MULTIPLE
MIN_FREE_FRACTION = 0.05
_MANIFEST_NAME = "MANIFEST.json"
_DUMP_TIMEOUT_SECONDS = 600.0
_DETAIL_CHARS = 500
_HOLD_COMMENT_MARKER = "livespec-whole-record-export-held"
_LEDGER_ERRORS = (
    WorkItemNotFoundError,
    BeadsCommandError,
    BeadsConnectionError,
    BeadsMappingError,
    BeadsTenantMissingError,
    ConnectionPrefixMissingError,
)


@dataclass(frozen=True, kw_only=True)
class EndedRunExport:
    """What the export left behind, or the step that stopped it."""

    ok: bool
    location: Path
    failed_step: str | None
    detail: str
    total_bytes: int
    sha256: str | None


@dataclass(frozen=True, kw_only=True)
class DiskPressure:
    """The free-space reading that made the export skip, with the floor it was held to."""

    free_bytes: int
    total_bytes: int
    min_free_fraction: float
    min_free_bytes: int


def disk_pressure(*, repo: Path) -> DiskPressure | None:
    """The reading when the export root's filesystem is below the free-space floor.

    The floor is the LARGER of a fraction of the filesystem and a multiple of the
    per-export ceiling, so a big disk is held to its fraction and a small one to
    the byte floor. The reading is taken on the nearest existing ancestor of the
    export root, because the root is created by the first export. A filesystem
    that cannot be read is NOT pressure: the export is best effort and the run is
    removed either way, so an unreadable reading must not silence the one thing
    that preserves its evidence.
    """
    probe = repo / EXPORT_ROOT
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        usage = shutil.disk_usage(probe)
    except OSError:
        return None
    if usage.free >= max(int(usage.total * MIN_FREE_FRACTION), MIN_FREE_BYTES):
        return None
    return DiskPressure(
        free_bytes=usage.free,
        total_bytes=usage.total,
        min_free_fraction=MIN_FREE_FRACTION,
        min_free_bytes=MIN_FREE_BYTES,
    )


def export_ended_run(*, port: FabroPort, repo: Path, run_id: str) -> EndedRunExport:
    """Dump one run into its export directory and read the manifest back.

    Every filesystem step runs under ONE `OSError` handler that names the step
    it was in, so a refused write or an unreadable file is a journaled failure
    rather than an exception that would stop the pass before the run is removed.
    """
    location = repo / EXPORT_ROOT / run_id
    step = "prepare"
    try:
        shutil.rmtree(location, ignore_errors=True)
        location.mkdir(parents=True)
        step = "dump"
        dumped = port.dump(
            run_id=run_id, output_dir=location, timeout_seconds=_DUMP_TIMEOUT_SECONDS
        )
        if dumped.command.exit_code != 0:
            return _failed(
                location=location,
                step="dump",
                detail=dumped.command.stderr.strip()[:_DETAIL_CHARS],
            )
        paths = sorted(path for path in location.rglob("*") if path.is_file())
        if not paths:
            return _failed(location=location, step="dump-empty", detail="fabro dump wrote no file")
        step = "manifest"
        entries = [_entry(root=location, path=path) for path in paths]
        _ = (location / _MANIFEST_NAME).write_text(json.dumps({"files": entries}), encoding="utf-8")
        step = "read-back"
        verified = _read_back(root=location)
    except OSError as error:
        return _failed(location=location, step=step, detail=f"{type(error).__name__}: {error}")
    if verified is None:
        return _failed(
            location=location, step="read-back", detail="manifest does not match the files on disk"
        )
    return EndedRunExport(
        ok=True,
        location=location,
        failed_step=None,
        detail="exported and read back",
        total_bytes=sum(int(entry["bytes"]) for entry in entries),
        sha256=verified,
    )


def export_run_before_removal(*, port: FabroPort, repo: Path, run_id: str) -> EndedRunExport:
    """Take the whole-record precondition required before a live-run removal.

    The ended-run collector deliberately removes a closed run even when this
    export is unavailable.  Live-run removals have the opposite direction: a
    disk-pressure skip is a failed precondition, so their callers keep the run
    in place and journal this returned step rather than calling ``fabro rm``.
    The dump and manifest read-back remain the one implementation above.
    """
    location = repo / EXPORT_ROOT / run_id
    pressure = disk_pressure(repo=repo)
    if pressure is not None:
        return _failed(
            location=location,
            step="skipped-disk-pressure",
            detail=(
                "whole-record export skipped under disk pressure: "
                f"free_bytes={pressure.free_bytes} min_free_bytes={pressure.min_free_bytes}"
            ),
        )
    return export_ended_run(port=port, repo=repo, run_id=run_id)


def report_export_hold(
    *,
    ledger: LedgerComments | None,
    work_item_id: str,
    run_id: str,
    removal: str,
    exported: EndedRunExport,
) -> None:
    """Name a held destructive removal on the work item when its export failed."""
    if ledger is None:
        return
    body = "\n".join(
        (
            _HOLD_COMMENT_MARKER,
            "",
            f"work-item: {work_item_id}",
            f"run id: {run_id}",
            f"removal held at: {removal}",
            f"whole-record export directory: {exported.location}",
            f"failed step: {exported.failed_step}",
            f"cause: {exported.detail}",
            "",
            "The run remains on its factory because its whole-record export did not read back.",
        )
    )
    _ = attempt(
        action=lambda: ledger.add_comment(issue_id=work_item_id, body=body),
        exceptions=_LEDGER_ERRORS,
    )


def prune_expired_exports(*, repo: Path, now_epoch: float) -> None:
    """Remove export directories older than the retention constant."""
    root = repo / EXPORT_ROOT
    if not root.is_dir():
        return
    for directory in root.iterdir():
        if directory.is_dir() and now_epoch - directory.stat().st_mtime > EXPORT_RETENTION_SECONDS:
            shutil.rmtree(directory, ignore_errors=True)


def _failed(*, location: Path, step: str, detail: str) -> EndedRunExport:
    return EndedRunExport(
        ok=False, location=location, failed_step=step, detail=detail, total_bytes=0, sha256=None
    )


def _entry(*, root: Path, path: Path) -> dict[str, str | int]:
    body = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(body),
        "sha256": hashlib.sha256(body).hexdigest(),
    }


def _read_back(*, root: Path) -> str | None:
    """The export's digest when the manifest on disk matches the files, else None.

    The digest is over `path NUL file-sha256 NEWLINE` for each manifest entry in
    path order, so it names the whole export in one value the journal carries.
    """
    manifest = json.loads((root / _MANIFEST_NAME).read_text(encoding="utf-8"))
    digest = hashlib.sha256()
    for entry in sorted(manifest["files"], key=lambda item: item["path"]):
        if _entry(root=root, path=root / entry["path"]) != entry:
            return None
        digest.update(f"{entry['path']}\0{entry['sha256']}\n".encode())
    return digest.hexdigest()
