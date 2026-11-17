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

from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort

__all__: list[str] = [
    "EXPORT_RETENTION_SECONDS",
    "EXPORT_ROOT",
    "EndedRunExport",
    "export_ended_run",
    "prune_expired_exports",
]

EXPORT_ROOT = Path("tmp") / "ended-run-exports"
EXPORT_RETENTION_SECONDS = 30 * 24 * 3600
_MANIFEST_NAME = "MANIFEST.json"
_DUMP_TIMEOUT_SECONDS = 600.0
_DETAIL_CHARS = 500


@dataclass(frozen=True, kw_only=True)
class EndedRunExport:
    """What the export left behind, or the step that stopped it."""

    ok: bool
    location: Path
    failed_step: str | None
    detail: str
    total_bytes: int
    sha256: str | None


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
