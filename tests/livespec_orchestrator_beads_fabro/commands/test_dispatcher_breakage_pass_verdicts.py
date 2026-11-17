"""Focused behaviour coverage for S1 of the scheduled-workflow breakage pass."""

# ruff: noqa: SLF001

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult


@dataclass
class _Runner:
    results: list[CommandResult]
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = cwd, timeout_seconds, env, stdin
        self.calls.append(argv)
        return self.results.pop(0)


def _ok(payload: object = "") -> CommandResult:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return CommandResult(exit_code=0, stdout=text, stderr="")


def _repo(tmp_path: Path, declaration: object = ["ci.yml"]) -> Path:
    (tmp_path / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {"breakage_workflows": declaration}
                }
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _module():
    return importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_breakage_pass"
    )


def test_green_workflow_prints_green_and_uses_cached_api(tmp_path: Path, capsys) -> None:
    runner = _Runner(
        results=[
            _ok("origin/master"),
            _ok({"workflow_runs": [{"conclusion": "success", "html_url": "https://run"}]}),
        ]
    )
    assert _module().breakage_pass(repo=_repo(tmp_path), runner=runner) == 0
    assert "workflow=ci.yml run=https://run green" in capsys.readouterr().out
    assert runner.calls[1][:4] == ["gh", "api", "--cache", "1h"]


def test_failed_workflow_dry_run_reports_one_line_per_failed_job(tmp_path: Path, capsys) -> None:
    runner = _Runner(
        results=[
            _ok("origin/master"),
            _ok(
                {
                    "workflow_runs": [
                        {
                            "id": 8,
                            "conclusion": "failure",
                            "html_url": "https://run",
                            "head_sha": "abc",
                        }
                    ]
                }
            ),
            _ok(
                {
                    "jobs": [
                        {"id": 3, "name": "check-types", "conclusion": "failure"},
                        {"id": 4, "name": "green", "conclusion": "success"},
                    ]
                }
            ),
            _ok("FAILED tests/test_api.py::test_value - AssertionError"),
        ]
    )
    assert _module().breakage_pass(repo=_repo(tmp_path), runner=runner) == 0
    line = capsys.readouterr().out
    assert "would-file job=check-types run=https://run head=abc" in line
    assert "failing-tests=tests/test_api.py::test_value" in line
    assert len(runner.calls) == 4
    assert all(call[:4] == ["gh", "api", "--cache", "1h"] for call in runner.calls[1:])


def test_missing_or_empty_declaration_does_not_read_the_forge(tmp_path: Path) -> None:
    module = _module()
    runner = _Runner(results=[])
    assert module.breakage_pass(repo=tmp_path, runner=runner) == 0
    assert module.breakage_pass(repo=_repo(tmp_path, []), runner=runner) == 0
    assert runner.calls == []


def test_invalid_declaration_fails_visibly(tmp_path: Path, capsys) -> None:
    assert _module().breakage_pass(repo=_repo(tmp_path, "ci.yml"), runner=_Runner(results=[])) == 1
    assert "dispatcher.breakage_workflows" in capsys.readouterr().err


def test_unreadable_run_and_no_completed_run_are_reported(tmp_path: Path, capsys) -> None:
    module = _module()
    unreadable = _Runner(
        results=[_ok("origin/master"), CommandResult(exit_code=1, stdout="", stderr="no")]
    )
    assert module.breakage_pass(repo=_repo(tmp_path), runner=unreadable) == 1
    assert "unreadable workflow run" in capsys.readouterr().out
    none = _Runner(results=[_ok("origin/master"), _ok({"workflow_runs": []})])
    assert module.breakage_pass(repo=_repo(tmp_path), runner=none) == 0
    assert "no-completed-run" in capsys.readouterr().out


def test_failed_job_read_errors_and_non_failure_conclusions_are_visible(
    tmp_path: Path, capsys
) -> None:
    module = _module()
    cancelled = _Runner(
        results=[
            _ok("origin/master"),
            _ok({"workflow_runs": [{"conclusion": "cancelled", "html_url": "u"}]}),
        ]
    )
    assert module.breakage_pass(repo=_repo(tmp_path), runner=cancelled) == 0
    assert "not-concluded cancelled" in capsys.readouterr().out
    broken = _Runner(
        results=[
            _ok("origin/master"),
            _ok(
                {
                    "workflow_runs": [
                        {"id": 8, "conclusion": "failure", "html_url": "u", "head_sha": "a"}
                    ]
                }
            ),
            CommandResult(exit_code=1, stdout="", stderr="no"),
        ]
    )
    assert module.breakage_pass(repo=_repo(tmp_path), runner=broken) == 1
    assert "unreadable failed run" in capsys.readouterr().out


def test_cli_arguments_and_handler_are_a_thin_pass_through(tmp_path: Path, monkeypatch) -> None:
    module = _module()
    parser = argparse.ArgumentParser()
    module.add_breakage_pass_arguments(parser=parser)
    args = parser.parse_args(["--repo", str(tmp_path), "--dry-run"])
    assert args.dry_run is True
    captured: dict[str, object] = {}
    monkeypatch.setattr(module, "breakage_pass", lambda **kwargs: captured.update(kwargs) or 7)
    assert module.run_breakage_pass_command(args=args) == 7
    assert captured["repo"] == tmp_path


def test_config_shape_errors_and_default_branch_failure_are_visible(tmp_path: Path, capsys) -> None:
    module = _module()
    cases = (
        "[]",
        '{"livespec-orchestrator-beads-fabro": 1}',
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": 1}}',
    )
    for document in cases:
        (tmp_path / ".livespec.jsonc").write_text(document, encoding="utf-8")
        assert module._watched_workflows(repo=tmp_path) is None
    (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")
    assert module._watched_workflows(repo=tmp_path) == ()
    (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {}}', encoding="utf-8"
    )
    assert module._watched_workflows(repo=tmp_path) == ()
    (tmp_path / ".livespec.jsonc").write_text(
        '{"livespec-orchestrator-beads-fabro": {"dispatcher": {}}}', encoding="utf-8"
    )
    assert module._watched_workflows(repo=tmp_path) == ()
    assert module._watched_workflows(repo=_repo(tmp_path, [""])) is None
    runner = _Runner(
        results=[
            CommandResult(exit_code=1, stdout="", stderr="no"),
            CommandResult(exit_code=1, stdout="", stderr="no"),
        ]
    )
    assert module.breakage_pass(repo=_repo(tmp_path), runner=runner) == 1
    assert "unreadable default branch" in capsys.readouterr().out


def test_workflow_and_job_payload_shape_errors_are_rejected(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path)
    for result in (
        _ok("not json"),
        _ok([]),
        _ok({}),
        _ok({"workflow_runs": "bad"}),
        _ok({"workflow_runs": ["bad"]}),
    ):
        assert (
            module._workflow_verdict(
                repo=repo, runner=_Runner(results=[result]), workflow="ci.yml", branch="master"
            )
            is None
        )
    assert module._failed_jobs(repo=repo, runner=_Runner(results=[]), run_id="") is None
    for result in (_ok("bad"), _ok([]), _ok({}), _ok({"jobs": "bad"})):
        assert module._failed_jobs(repo=repo, runner=_Runner(results=[result]), run_id="1") is None
    assert (
        module._failed_jobs(
            repo=repo,
            runner=_Runner(results=[_ok({"jobs": [{"conclusion": "success"}]})]),
            run_id="1",
        )
        == []
    )


def test_failed_job_and_log_edge_cases_are_visible(tmp_path: Path, capsys) -> None:
    module = _module()
    repo = _repo(tmp_path)
    assert module._job_log(repo=repo, runner=_Runner(results=[]), job_id="") is None
    assert (
        module._job_log(
            repo=repo,
            runner=_Runner(results=[CommandResult(exit_code=1, stdout="", stderr="no")]),
            job_id="1",
        )
        is None
    )
    assert (
        module._emit_outcome(workflow="ci.yml", outcome={}, repo=repo, runner=_Runner(results=[]))
        is False
    )
    missing_head = {"id": "1", "conclusion": "failure", "html_url": "u"}
    assert (
        module._emit_outcome(
            workflow="ci.yml",
            outcome=missing_head,
            repo=repo,
            runner=_Runner(results=[_ok({"jobs": []})]),
        )
        is True
    )
    missing_job_name = {"id": "1", "head_sha": "a", "conclusion": "failure", "html_url": "u"}
    assert (
        module._emit_outcome(
            workflow="ci.yml",
            outcome=missing_job_name,
            repo=repo,
            runner=_Runner(results=[_ok({"jobs": [{"id": 2, "conclusion": "failure"}]}), _ok("")]),
        )
        is True
    )
    no_test = {"id": "1", "head_sha": "a", "conclusion": "failure", "html_url": "u"}
    assert (
        module._emit_outcome(
            workflow="ci.yml",
            outcome=no_test,
            repo=repo,
            runner=_Runner(
                results=[
                    _ok({"jobs": [{"id": 2, "name": "check", "conclusion": "failure"}]}),
                    _ok("ordinary failure"),
                ]
            ),
        )
        is False
    )
    output = capsys.readouterr().out
    assert "no-completed-run" in output
    assert "unreadable failed job" in output
    assert "no failing test named" in output
    assert module._string(value=1) == "1"
    assert module._string(value=None) == ""


def test_failed_jobs_paginate_past_the_first_hundred_jobs(tmp_path: Path) -> None:
    module = _module()
    repo = _repo(tmp_path)
    first_page = [{"id": n, "name": f"job-{n}", "conclusion": "success"} for n in range(100)]
    runner = _Runner(
        results=[
            _ok({"jobs": first_page}),
            _ok({"jobs": [{"id": 200, "name": "late", "conclusion": "failure"}]}),
        ]
    )
    failed = module._failed_jobs(repo=repo, runner=runner, run_id="9")
    assert failed == [{"id": 200, "name": "late", "conclusion": "failure"}]
    assert len(runner.calls) == 2
    assert all(call[:4] == ["gh", "api", "--cache", "1h"] for call in runner.calls)
    assert "per_page=100" in runner.calls[0][-1]
    assert "page=1" in runner.calls[0][-1]
    assert "page=2" in runner.calls[1][-1]
    broken = _Runner(
        results=[_ok({"jobs": first_page}), CommandResult(exit_code=1, stdout="", stderr="no")]
    )
    assert module._failed_jobs(repo=repo, runner=broken, run_id="9") is None
