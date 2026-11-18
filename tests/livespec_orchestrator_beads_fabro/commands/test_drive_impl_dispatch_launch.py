"""What an `impl:` dispatch's launch decides and leaves behind, without a slice.

The scoped launch is bound at the integration tier by
`tests/integration/test_impl_dispatch_memory_slice_scenario371.py`. These cover
the other half the same clause owes: a host that does not provide the slice
launches with exactly the argv it always did, says so, and a fault writing the
launch's journal record never fails the dispatch.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _drive_impl_delivery as delivery
from livespec_orchestrator_beads_fabro.commands._drive_impl_dispatch import (
    CommandRun,
    build_dispatcher_argv,
    run_impl_dispatch,
)

_ITEM = "bd-ib-szbxu7"


class _Runner:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
        del cwd
        self.calls.append(argv)
        return CommandRun(argv=argv, returncode=0, stdout="[]", stderr="")


def _dispatch(*, repo: Path, runner: _Runner) -> dict[str, object]:
    return run_impl_dispatch(
        repo=repo,
        work_item_ref=_ITEM,
        runner=runner,
        dispatcher_bin=repo / "dispatcher.py",
        acp_nodes=(),
        workflow_name=None,
        identity=None,
    )


def test_a_host_without_the_slice_launches_the_unchanged_argv_and_says_so(tmp_path: Path) -> None:
    runner = _Runner()

    result = _dispatch(repo=tmp_path, runner=runner)

    loop_argv = build_dispatcher_argv(
        repo=tmp_path, dispatcher_bin=tmp_path / "dispatcher.py", work_item_ref=_ITEM
    )
    assert runner.calls == [loop_argv]
    assert result["launch"] == "unscoped"
    assert "scope_unit" not in result
    journal = tmp_path / "tmp" / "fabro-dispatch-journal.jsonl"
    (record,) = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert record["stage"] == "dispatch-launch-scope"
    assert record["work_item_id"] == _ITEM
    assert record["launch"] == "unscoped"
    assert "scope_unit" not in record


def test_a_fault_writing_the_launch_record_does_not_fail_the_dispatch(tmp_path: Path) -> None:
    _ = (tmp_path / "tmp").write_text(
        "a file where the journal directory belongs", encoding="utf-8"
    )
    runner = _Runner()

    result = _dispatch(repo=tmp_path, runner=runner)

    assert len(runner.calls) == 1
    assert result["status"] == "green"
    assert result["launch"] == "unscoped"


def test_a_final_ready_set_refusal_after_a_merged_pull_request_reports_delivery(
    tmp_path: Path,
) -> None:
    class _RefusingRunner:
        def __call__(self, *, argv: tuple[str, ...], cwd: Path | None = None) -> CommandRun:
            del argv, cwd
            return CommandRun(
                argv=("dispatcher.py",),
                returncode=3,
                stdout="",
                stderr="ERROR: requested work-item(s) not in the ready set: bd-ib-szbxu7\n",
            )

    result = run_impl_dispatch(
        repo=tmp_path,
        work_item_ref=_ITEM,
        runner=_RefusingRunner(),
        dispatcher_bin=tmp_path / "dispatcher.py",
        acp_nodes=(),
        workflow_name=None,
        identity=None,
        merged_pull_request_lookup=lambda _repo, _branch: 4963,
    )

    assert result["summary"] == (
        "Dispatcher delivered bd-ib-szbxu7: merged pull request #4963 landed before its final "
        "ready-set refusal."
    )


def test_only_the_final_ready_set_refusal_looks_up_a_merged_pull_request(tmp_path: Path) -> None:
    def lookup(_repo: Path, _branch: str) -> int | None:
        raise AssertionError("an unrelated Dispatcher failure must not query pull requests")

    assert (
        delivery.delivered_merged_pull_request(
            repo=tmp_path,
            work_item_ref=_ITEM,
            returncode=1,
            stderr="Dispatcher failed before listing a run",
            lookup=lookup,
        )
        is None
    )


def test_a_merged_ready_set_refusal_is_classified_as_delivery(tmp_path: Path) -> None:
    assert (
        delivery.delivered_merged_pull_request(
            repo=tmp_path,
            work_item_ref=_ITEM,
            returncode=3,
            stderr="ERROR: requested work-item(s) not in the ready set",
            lookup=lambda _repo, _branch: 4963,
        )
        == 4963
    )


def test_a_final_ready_set_refusal_uses_the_default_merged_pull_request_lookup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(delivery, "merged_pull_request_number", lambda **_kwargs: 4963)

    assert (
        delivery.delivered_merged_pull_request(
            repo=tmp_path,
            work_item_ref=_ITEM,
            returncode=3,
            stderr="ERROR: requested work-item(s) not in the ready set",
            lookup=None,
        )
        == 4963
    )


@pytest.mark.parametrize(
    ("gh", "returncode", "stdout", "expected"),
    [
        (None, 0, "[]", None),
        ("gh", 1, "[]", None),
        ("gh", 0, "{}", None),
        ("gh", 0, '[null, {"number": 0}, {"number": 4963}]', 4963),
    ],
)
def test_the_merged_pull_request_lookup_handles_forge_failures_and_results(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    gh: str | None,
    returncode: int,
    stdout: str,
    expected: int | None,
) -> None:
    monkeypatch.setattr(delivery.shutil, "which", lambda _command: gh)
    monkeypatch.setattr(
        delivery.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            args=("gh",), returncode=returncode, stdout=stdout, stderr=""
        ),
    )

    assert delivery.merged_pull_request_number(repo=tmp_path, branch=f"feat/{_ITEM}") == expected
