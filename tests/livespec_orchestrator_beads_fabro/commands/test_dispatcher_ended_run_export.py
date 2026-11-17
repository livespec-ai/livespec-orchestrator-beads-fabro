"""The ended-run export reports the step that stopped it and prunes only expired exports."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_ended_run_export import (
    EXPORT_RETENTION_SECONDS,
    EXPORT_ROOT,
    export_ended_run,
    prune_expired_exports,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroPort, FabroTarget


@dataclass(kw_only=True)
class _DumpRunner:
    """Writes one file for `fabro dump <run> ... -o <dir>`."""

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env, stdin)
        out = Path(argv[argv.index("-o") + 1])
        _ = (out / "events.jsonl").write_text('{"event":"run.completed"}\n', encoding="utf-8")
        return CommandResult(exit_code=0, stdout="", stderr="")


def _port(*, tmp_path: Path) -> FabroPort:
    return FabroPort(
        fabro_bin="fabro",
        target=FabroTarget(server_url="https://factory.test"),
        runner=_DumpRunner(),
        cwd=tmp_path,
    )


def test_a_successful_export_reports_its_location_size_and_digest(tmp_path: Path) -> None:
    exported = export_ended_run(port=_port(tmp_path=tmp_path), repo=tmp_path, run_id="01RUN")

    assert exported.ok
    assert exported.location == tmp_path / EXPORT_ROOT / "01RUN"
    assert exported.total_bytes == len('{"event":"run.completed"}\n')
    assert exported.sha256 is not None
    assert exported.failed_step is None


def test_an_unreadable_dumped_file_is_a_failed_manifest_step_not_an_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _refuse(self: Path) -> bytes:
        raise PermissionError(str(self))

    monkeypatch.setattr(Path, "read_bytes", _refuse)

    exported = export_ended_run(port=_port(tmp_path=tmp_path), repo=tmp_path, run_id="01RUN")

    assert (exported.ok, exported.failed_step) == (False, "manifest")
    assert "PermissionError" in exported.detail


def test_an_export_directory_that_cannot_be_created_is_a_failed_prepare_step(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "tmp").write_text("a file where the export root's parent should be")

    exported = export_ended_run(port=_port(tmp_path=tmp_path), repo=tmp_path, run_id="01RUN")

    assert (exported.ok, exported.failed_step) == (False, "prepare")


def test_a_manifest_that_does_not_match_the_files_fails_the_read_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = Path.write_text

    def _corrupt(self: Path, data: str, *args: object, **kwargs: object) -> int:
        if self.name == "MANIFEST.json":
            wrong = json.loads(data)
            wrong["files"][0]["sha256"] = "0" * 64
            data = json.dumps(wrong)
        return original(self, data, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", _corrupt)

    exported = export_ended_run(port=_port(tmp_path=tmp_path), repo=tmp_path, run_id="01RUN")

    assert (exported.ok, exported.failed_step) == (False, "read-back")


def test_pruning_ignores_a_plain_file_and_removes_only_expired_directories(tmp_path: Path) -> None:
    root = tmp_path / EXPORT_ROOT
    expired = root / "01EXPIRED"
    expired.mkdir(parents=True)
    _ = (root / "stray.txt").write_text("not an export", encoding="utf-8")
    aged = time.time() - EXPORT_RETENTION_SECONDS - 3600
    os.utime(expired, (aged, aged))

    prune_expired_exports(repo=tmp_path, now_epoch=time.time())

    assert (expired.exists(), (root / "stray.txt").exists()) == (False, True)


def test_pruning_with_no_export_root_does_nothing(tmp_path: Path) -> None:
    prune_expired_exports(repo=tmp_path, now_epoch=time.time())

    assert not (tmp_path / EXPORT_ROOT).exists()
