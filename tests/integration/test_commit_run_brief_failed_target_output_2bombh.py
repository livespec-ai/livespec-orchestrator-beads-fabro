"""A failed commit run's repair brief carries each failed target's own output (bd-ib-2bombh).

`SPECIFICATION/contracts.md` section "ACP node timeouts" requires a commit-run re-entry
brief to take its failed target names and its hook error lines from the commit run's FULL
recorded output, never only from its final lines, so that output ending in the hook's
per-target timing table still yields the files that failed. The aggregate prints each
target's own section first and a per-target wall-time table, the `Failed targets` list
and the failure digest last. Measured on run 01M7S59GMK53 (bd-ib-3jzrjy): the last 80
lines of the recorded output were 61 timing rows plus the digest, so the ruff and pyright
lines of the two failed targets never reached the re-entered fix turn.

Every case runs the LANDED runner program's own `brief_text` on a recorded output shaped
like the aggregate's, exactly as the commit runner builds the brief for a settled run.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry import PLUGINS_ROOT

from tests.prepare_step_support import land_helpers

_RUFF = (
    ".claude-plugin/scripts/pkg/_drive_merge_hold_valve.py:56:5: F401 [*] `observe_item_run_liveness`"
    " imported but unused"
)
_PYRIGHT = (
    "  /workspace/.claude-plugin/scripts/pkg/_drive_merge_hold_valve.py:56:5 - error: Import"
    ' "observe_item_run_liveness" is not accessed (reportUnusedImport)'
)
_TIMING_ROWS = tuple(f"  0.{index % 10}s  check-passing-{index}" for index in range(95))


def _aggregate_output() -> str:
    """Target sections first, then the summary tail that fills the brief's last 80 lines."""
    lines = [
        "::: just check-lint [FAILED, wall: 0.1s]",
        "uv run ruff check .",
        _RUFF,
        "Found 1 error.",
        "",
        "::: just check-format [ok, wall: 0.1s]",
        "format-passing-line",
        "",
        "::: just check-types [FAILED, wall: 12.0s]",
        "uv run pyright",
        _PYRIGHT,
        "1 error, 0 warnings, 0 informations",
        "",
        "--- parallel check summary ---",
        "passed: 1, failed: 2, skipped: 0",
        "",
        "per-target wall times (longest first):",
        *_TIMING_ROWS,
        "",
        "Failed targets (2):",
        "  - check-lint",
        "  - check-types",
        "check-lint: failed without a structured failure_mode — read this target's captured output above",
        "check-types: failed without a structured failure_mode — read this target's captured output above",
    ]
    return "\n".join(lines) + "\n"


def _brief(*, tmp_path: Path, recorded: str) -> str:
    """The landed runner's own `brief_text`, run in-process on a settled failed run."""
    plugins = tmp_path / "plugins"
    _ = land_helpers(roots={PLUGINS_ROOT: plugins})
    runner = plugins / COMMIT_RUNNER_PROGRAM_FILENAME
    namespace: dict[str, object] = {"__name__": "livespec_commit_runner_under_test"}
    exec(compile(runner.read_text(encoding="utf-8"), str(runner), "exec"), namespace)  # noqa: S102 — the landed program's exact source
    builder = namespace["brief_text"]
    assert callable(builder)
    path = tmp_path / "commit-run.json"
    _ = path.with_suffix(".output").write_text(recorded, encoding="utf-8")
    return str(builder("run-1", path, {"exit_code": 1, "hook_ran": True}, "failed", 60))


def test_a_brief_whose_hook_output_ends_in_the_timing_table_still_carries_each_failed_targets_lines(
    tmp_path: Path,
) -> None:
    brief = _brief(tmp_path=tmp_path, recorded=_aggregate_output())

    assert _RUFF in brief
    assert _PYRIGHT in brief


def test_the_failing_files_list_names_the_file_and_line_of_a_lint_and_a_type_finding(
    tmp_path: Path,
) -> None:
    brief = _brief(tmp_path=tmp_path, recorded=_aggregate_output())

    assert "failing files: none reported" not in brief
    assert "_drive_merge_hold_valve.py:56" in brief.split("Commit run")[0]


def test_a_passing_target_s_own_lines_stay_out_of_the_failed_target_output(
    tmp_path: Path,
) -> None:
    brief = _brief(tmp_path=tmp_path, recorded=_aggregate_output())

    assert "format-passing-line" not in brief


@pytest.mark.parametrize("target", ["check-lint", "check-types"])
def test_each_failed_target_s_output_is_headed_by_its_own_name(tmp_path: Path, target: str) -> None:
    brief = _brief(tmp_path=tmp_path, recorded=_aggregate_output())

    assert f"::: just {target}\n" in brief
