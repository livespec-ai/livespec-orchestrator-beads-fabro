"""Every commit-refusal brief names the failing files from the full output (bd-ib-b3qjzq).

`SPECIFICATION/contracts.md` section "ACP node timeouts" -> "Every commit-refusal
re-entry brief names the failing files from the full recorded output": a brief
takes its failed targets and failing files from the commit run's FULL recorded
output, so output ending in the hook's per-target timing table still names the
uncovered files; it lists at most the first 40 failing files in the output's
order and states how many further files it omitted. The commit runner owns the
one builder: its settle brief and its `refusal-section` operation, which the Red
and Green command programs run, print the same section for the same output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_commit_runner_program import (
    COMMIT_RUNNER_PROGRAM_FILENAME,
    commit_runner_program_source,
)

_RUN_ID = "commit-0123456789abcdef"
_TIMING_TAIL = "".join(f"0.{index}s check-target-{index}\n" for index in range(100))


def _program(*, tmp_path: Path) -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "livespec_commit_runner_under_test"}
    source = tmp_path / COMMIT_RUNNER_PROGRAM_FILENAME
    _ = source.write_text(commit_runner_program_source(), encoding="utf-8")
    exec(compile(source.read_text(encoding="utf-8"), str(source), "exec"), namespace)  # noqa: S102 — the materialized program's exact source
    return namespace


def _coverage_output(*, files: int) -> str:
    rows = "".join(
        f"pkg/module_{index:02d}.py      40      2      8      1    93%   {index + 10}-{index + 11}\r\n"
        for index in range(files)
    )
    return (
        "---------- coverage: platform linux, python 3.10.16-final-0 ----------\r\n"
        "Name                 Stmts   Miss Branch BrPart  Cover   Missing\r\n"
        "pkg/covered.py          10      0      2      0   100%\r\n"
        f"{rows}"
        "TOTAL                 900     20    100      5    97%\r\n"
        "Failed targets (1):\r\n"
        "  - check-per-file-coverage\r\n"
        f"{_TIMING_TAIL}"
    )


def _refusal_section(*, tmp_path: Path, output: str, capsys: pytest.CaptureFixture[str]) -> str:
    """Run the runner's `refusal-section` operation in-process on a recorded output."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    program = _program(tmp_path=tmp_path)
    recorded = tmp_path / "commit.output"
    _ = recorded.write_text(output, encoding="utf-8")
    _ = capsys.readouterr()
    status = program["main"](["refusal-section", str(recorded)], str(tmp_path / "runner"))
    captured = capsys.readouterr()
    assert status == 0, captured.err
    return captured.out


def test_a_coverage_refusal_ending_in_the_timing_table_names_its_uncovered_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    section = _refusal_section(capsys=capsys, tmp_path=tmp_path, output=_coverage_output(files=3))

    assert section == (
        "failed targets: check-per-file-coverage\n"
        "failing files (3):\n"
        "- pkg/module_00.py: uncovered lines 10-11 "
        "(2 missed, 1 partial branch; 93% covered)\n"
        "- pkg/module_01.py: uncovered lines 11-12 "
        "(2 missed, 1 partial branch; 93% covered)\n"
        "- pkg/module_02.py: uncovered lines 12-13 "
        "(2 missed, 1 partial branch; 93% covered)\n"
    )


def test_a_per_file_coverage_refusal_keeps_a_short_file_s_full_figures_from_early_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A rounded aggregate total never replaces the short file's own coverage figures."""
    output = (
        "---------- coverage: platform linux, python 3.10.16-final-0 ----------\n"
        "Name                                Stmts   Miss  Branch  BrPart  Cover   Missing\n"
        "ansible/factory_workspace_manifest.py   165      1      20       1    99%   97\n"
        "TOTAL                                9000      1     400       1  100.00%\n"
        "Failed targets (1):\n"
        "  - check-per-file-coverage\n" + _TIMING_TAIL
    )

    section = _refusal_section(capsys=capsys, tmp_path=tmp_path, output=output)

    assert section == (
        "failed targets: check-per-file-coverage\n"
        "failing files (1):\n"
        "- ansible/factory_workspace_manifest.py: uncovered lines 97 "
        "(1 missed, 1 partial branch; 99% covered)\n"
        "rounded total coverage 100.00% is not the pass criterion; "
        "ansible/factory_workspace_manifest.py is below 100%\n"
    )


def test_a_per_file_coverage_refusal_keeps_short_file_figures_when_total_is_not_rounded(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A short file's figures do not depend on the aggregate total's rounding."""
    output = (
        "---------- coverage: platform linux, python 3.10.16-final-0 ----------\n"
        "Name                                Stmts   Miss  Branch  BrPart  Cover   Missing\n"
        "ansible/factory_workspace_manifest.py   165      1      20       1    99%   97\n"
        "TOTAL                                9000     11     400       1  99.88%\n"
        "Failed targets (1):\n"
        "  - check-per-file-coverage\n" + _TIMING_TAIL
    )

    section = _refusal_section(capsys=capsys, tmp_path=tmp_path, output=output)

    assert section == (
        "failed targets: check-per-file-coverage\n"
        "failing files (1):\n"
        "- ansible/factory_workspace_manifest.py: uncovered lines 97 "
        "(1 missed, 1 partial branch; 99% covered)\n"
    )


def test_a_per_file_coverage_refusal_keeps_every_short_file_s_figures(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Every short file retains its own figures, regardless of its percentage."""
    output = (
        "---------- coverage: platform linux, python 3.10.16-final-0 ----------\n"
        "Name                                Stmts   Miss  Branch  BrPart  Cover   Missing\n"
        "ansible/factory_workspace_manifest.py   165      1      20       1    99%   97\n"
        "src/commit_replay_delegate.py            99      7      12       2    92%   133-138\n"
        "TOTAL                                9000     11     400       3  99.88%\n"
        "Failed targets (1):\n"
        "  - check-per-file-coverage\n" + _TIMING_TAIL
    )

    section = _refusal_section(capsys=capsys, tmp_path=tmp_path, output=output)

    assert section == (
        "failed targets: check-per-file-coverage\n"
        "failing files (2):\n"
        "- ansible/factory_workspace_manifest.py: uncovered lines 97 "
        "(1 missed, 1 partial branch; 99% covered)\n"
        "- src/commit_replay_delegate.py: uncovered lines 133-138 "
        "(7 missed, 2 partial branch; 92% covered)\n"
    )


def test_an_affected_tests_refusal_without_a_target_list_names_its_recipe_test_and_coverage(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The pre-commit affected-tests gate has no aggregate target list of its own."""
    output = (
        "│ lefthook v1.13.6  hook: pre-commit │\n"
        "FAILED tests/test_phase1_mechanical_coverage.py::"
        "test_phase1_mechanical_checks_have_no_newly_covered_warnings\n"
        "effects/_incident_authority_transition.py  300  18  90%  "
        "237, 273, 276, 286, 289, 291\n"
        "Coverage failure: total of 97 is less than fail-under=100\n"
        "error: Recipe `check-changed` failed\n"
        ":: affected-tests gate refused the commit\n"
    )

    section = _refusal_section(capsys=capsys, tmp_path=tmp_path, output=output)

    assert section == (
        "failed targets: check-changed\n"
        "failing files (2):\n"
        "- tests/test_phase1_mechanical_coverage.py::"
        "test_phase1_mechanical_checks_have_no_newly_covered_warnings: failed\n"
        "- effects/_incident_authority_transition.py: uncovered lines "
        "237, 273, 276, 286, 289, 291 (90% covered)\n"
    )


def test_the_section_lists_the_first_forty_files_and_counts_the_rest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    section = _refusal_section(capsys=capsys, tmp_path=tmp_path, output=_coverage_output(files=55))

    listed = [line for line in section.splitlines() if line.startswith("- ")]
    facts = [
        len(listed) == 40,
        listed[0] == "- pkg/module_00.py: uncovered lines 10-11 "
        "(2 missed, 1 partial branch; 93% covered)",
        listed[-1] == "- pkg/module_39.py: uncovered lines 49-50 "
        "(2 missed, 1 partial branch; 93% covered)",
        "failing files (55):" in section,
        section.endswith("15 further files omitted\n"),
    ]
    assert all(facts), section


def test_lloc_and_coverage_events_are_read_only_for_their_own_failed_targets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = (
        '{"file": "pkg/big.py", "lloc": 260, "hard_ceiling": 250,'
        ' "event": "file LLOC exceeds 250-line hard ceiling", "level": "error"}\n'
        '{"file": "pkg/soft.py", "lloc": 210, "event": "file LLOC exceeds 200-line soft'
        ' ceiling", "level": "warning"}\n'
        '{"file": "./pkg/thin.py", "line_percent": 50.0, "missing_lines": 4,'
        ' "event": "file below 100% coverage", "level": "error"}\n'
        "pkg/thin.py 10 4 60%   3-6\n"
        "not json {\n"
        '{"no": "file"}\n'
        "[1, 2]\n"
        '{"broken": \n'
        "Failed targets (2):\n"
        "  - check-file-lloc\n"
        "  - check-check-coverage-incremental\n"
    )
    unrelated = "pkg/a.py 10 1 90%\nFailed targets (1):\n  - check-lint\n"

    section = _refusal_section(capsys=capsys, tmp_path=tmp_path / "both", output=output)
    other = _refusal_section(capsys=capsys, tmp_path=tmp_path / "other", output=unrelated)
    bare = _refusal_section(capsys=capsys, tmp_path=tmp_path / "bare", output="pkg/b.py 10 1 90%\n")

    facts = [
        section
        == (
            "failed targets: check-file-lloc check-check-coverage-incremental\n"
            "failing files (2):\n"
            "- pkg/big.py: LLOC 260 over the 250-line hard ceiling\n"
            "- pkg/thin.py: uncovered lines 3-6 (60% covered)\n"
        ),
        other
        == "failed targets: check-lint\nfailing files: none reported in the recorded output\n",
        bare == "failed targets: none\nfailing files: none reported in the recorded output\n",
    ]
    assert all(facts), (section, other, bare)


def test_an_unreadable_output_file_prints_an_empty_section(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    program = _program(tmp_path=tmp_path)

    status = program["refusal_section"](str(tmp_path / "absent.output"))

    assert status == 0
    assert capsys.readouterr().out == (
        "failed targets: none\nfailing files: none reported in the recorded output\n"
    )


def test_the_settle_brief_carries_the_same_section_as_the_red_and_green_programs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    program = _program(tmp_path=tmp_path)
    runs = tmp_path / "runs"
    runs.mkdir()
    record = {"state": "failed", "exit_code": 1, "hook_ran": True}
    path = runs / f"{_RUN_ID}.json"
    _ = path.write_text(json.dumps(record), encoding="utf-8")
    output = _coverage_output(files=2)
    _ = path.with_suffix(".output").write_text(output, encoding="utf-8")

    brief = program["brief_text"](_RUN_ID, path, record, "failed", 300)
    section = _refusal_section(capsys=capsys, tmp_path=tmp_path / "programs", output=output)

    assert brief.startswith(section + "\n")
    assert "- pkg/module_01.py: uncovered lines 11-12" in brief
