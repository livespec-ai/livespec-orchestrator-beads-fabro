"""Tests for the broker's separately launched entry point and its workflow-owned launch."""

from __future__ import annotations

import io
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_broker_serve import (
    CREDENTIAL_FILE_FLAG,
    LAUNCH_FILE_FLAG,
    credential_reader,
    load_launch,
    main,
    request_from_line,
)


@dataclass(kw_only=True)
class _Runner:
    calls: list[tuple[list[str], Mapping[str, str | None] | None]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        del cwd, timeout_seconds, stdin
        self.calls.append((argv, env))
        return CommandResult(exit_code=0, stdout="posted", stderr="child-diagnostic")


def _private(*, path: Path, text: str, mode: int = 0o600) -> Path:
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)
    return path


def _launch_file(*, tmp_path: Path, stage: str = "proof_verify") -> Path:
    staging = tmp_path / "staging"
    staging.mkdir(exist_ok=True)
    document = {
        "stage": stage,
        "pull_request_number": 73,
        "proof_asset_store": "proof-assets",
        "request_directory": str(staging),
    }
    return _private(path=tmp_path / "launch.json", text=json.dumps(document))


def _credential_file(*, tmp_path: Path) -> Path:
    return _private(path=tmp_path / "credential", text="broker-secret\n")


def _argv(*, tmp_path: Path) -> list[str]:
    return [
        LAUNCH_FILE_FLAG,
        str(_launch_file(tmp_path=tmp_path)),
        CREDENTIAL_FILE_FLAG,
        str(_credential_file(tmp_path=tmp_path)),
    ]


def _line(**fields: object) -> str:
    request: dict[str, object] = {
        "operation": "comment",
        "claimed_stage": "proof_verify",
        "pull_request_number": 73,
    }
    request.update(fields)
    return json.dumps(request)


def _serve(
    *, argv: list[str], lines: list[str], runner: _Runner, tmp_path: Path
) -> tuple[int, list[dict[str, object]]]:
    out = io.StringIO()
    status = main(argv=argv, request_lines=lines, runner=runner, cwd=tmp_path, stdout=out)
    replies = [json.loads(reply) for reply in out.getvalue().splitlines()]
    return status, replies


def test_the_entry_point_serves_only_the_launch_file_stage_and_never_a_request_claim(
    tmp_path: Path,
) -> None:
    body = tmp_path / "staging" / "record.md"
    argv = _argv(tmp_path=tmp_path)
    body.write_text("proof", encoding="utf-8")
    runner = _Runner()

    status, replies = _serve(
        argv=argv,
        lines=[
            "",
            _line(comment_body=str(body)),
            _line(claimed_stage="pr", comment_body=str(body)),
            _line(operation="merge"),
            _line(stage="pr", comment_body=str(body)),
            _line(launch={"stage": "pr"}, comment_body=str(body)),
            "not json",
        ],
        runner=runner,
        tmp_path=tmp_path,
    )

    assert status == 0
    assert replies[0] == {"refusal": None, "exit_code": 0, "stdout": "posted"}
    refusals = [str(reply["refusal"]) for reply in replies[1:]]
    assert "claimed stage" in refusals[0]
    assert "only a new comment" in refusals[1]
    assert "unknown field 'stage'" in refusals[2]
    assert "unknown field 'launch'" in refusals[3]
    assert "not JSON" in refusals[4]
    assert all(reply["exit_code"] is None for reply in replies[1:])
    assert runner.calls == [
        (
            ["gh", "pr", "comment", "73", "--body-file", str(body)],
            {"GH_TOKEN": "broker-secret", "GITHUB_TOKEN": None},
        )
    ]


def test_the_reply_never_carries_the_child_standard_error(tmp_path: Path) -> None:
    body = tmp_path / "staging" / "record.md"
    argv = _argv(tmp_path=tmp_path)
    body.write_text("proof", encoding="utf-8")
    out = io.StringIO()

    _ = main(
        argv=argv,
        request_lines=[_line(comment_body=str(body))],
        runner=_Runner(),
        cwd=tmp_path,
        stdout=out,
    )

    assert "child-diagnostic" not in out.getvalue()


@pytest.mark.parametrize(
    "argv",
    [
        [],
        [LAUNCH_FILE_FLAG, "a", CREDENTIAL_FILE_FLAG],
        [LAUNCH_FILE_FLAG, "a", LAUNCH_FILE_FLAG, "b"],
        [LAUNCH_FILE_FLAG, "a", "--other", "b"],
    ],
)
def test_the_entry_point_refuses_to_start_without_exactly_its_two_files(
    argv: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    status, replies = _serve(argv=argv, lines=[_line()], runner=_Runner(), tmp_path=tmp_path)

    assert status == 1
    assert replies == []
    assert "usage" in capsys.readouterr().err


def test_the_entry_point_refuses_to_start_on_a_bad_launch_or_credential_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = _argv(tmp_path=tmp_path)
    runner = _Runner()
    Path(argv[3]).chmod(0o640)

    credential_status, _ = _serve(argv=argv, lines=[_line()], runner=runner, tmp_path=tmp_path)
    credential_err = capsys.readouterr().err
    Path(argv[1]).chmod(0o660)
    launch_status, _ = _serve(argv=argv, lines=[_line()], runner=runner, tmp_path=tmp_path)
    launch_err = capsys.readouterr().err

    assert (credential_status, launch_status) == (1, 1)
    assert "credential file" in credential_err
    assert "launch file" in launch_err
    assert runner.calls == []


def test_a_launch_file_an_agent_could_have_written_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launch = _launch_file(tmp_path=tmp_path)

    assert not isinstance(load_launch(path=launch), str)
    launch.chmod(0o620)
    writable = load_launch(path=launch)
    launch.chmod(0o600)
    monkeypatch.setattr(os, "geteuid", lambda: launch.stat().st_uid + 1)
    foreign = load_launch(path=launch)

    assert isinstance(writable, str)
    assert "another user" in writable
    assert isinstance(foreign, str)
    assert "not owned by the broker's own user" in foreign


def test_a_launch_file_that_is_missing_or_not_a_file_is_refused(tmp_path: Path) -> None:
    missing = load_launch(path=tmp_path / "absent.json")
    directory = load_launch(path=tmp_path)

    assert isinstance(missing, str)
    assert "cannot be read" in missing
    assert isinstance(directory, str)
    assert "not a regular file" in directory


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("{", "not JSON"),
        ("[]", "not a JSON object"),
        ('{"stage": "proof_verify"}', "pull_request_number must be an integer"),
        (
            '{"stage": "", "pull_request_number": true, "extra": 1}',
            "unknown field 'extra'",
        ),
        (
            '{"stage": "review", "pull_request_number": 1, "request_directory": 7}',
            "request_directory must be a non-empty string or null",
        ),
    ],
)
def test_a_malformed_launch_file_is_refused(text: str, expected: str, tmp_path: Path) -> None:
    refusal = load_launch(path=_private(path=tmp_path / "launch.json", text=text))

    assert isinstance(refusal, str)
    assert expected in refusal


def test_a_launch_file_that_is_not_text_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "launch.json"
    path.write_bytes(b"\xff\xfe")
    path.chmod(0o600)

    refusal = load_launch(path=path)

    assert isinstance(refusal, str)
    assert "refused launch file" in refusal


def test_a_minimal_launch_file_carries_no_store_or_directory(tmp_path: Path) -> None:
    launch = load_launch(
        path=_private(
            path=tmp_path / "launch.json",
            text='{"stage": "review", "pull_request_number": 5}',
        )
    )

    assert not isinstance(launch, str)
    assert (launch.stage, launch.pull_request_number) == ("review", 5)
    assert launch.proof_asset_store is None
    assert launch.request_directory is None


def test_the_credential_is_read_again_at_each_use(tmp_path: Path) -> None:
    path = _private(path=tmp_path / "credential", text="first\n")
    read = credential_reader(path=path)
    first = read()
    path.write_text("second\n", encoding="utf-8")

    assert (first, read()) == ("first", "second")


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"pull_request_number": True}, "pull_request_number must be an integer"),
        ({"pull_request_number": "73"}, "pull_request_number must be an integer"),
        ({"comment_body": ""}, "comment_body must be a non-empty string or null"),
        ({"operation": 3}, "operation must be a non-empty string"),
        ({"credential": "x"}, "unknown field 'credential'"),
    ],
)
def test_a_request_with_the_wrong_shape_is_refused(
    fields: dict[str, object], expected: str
) -> None:
    refusal = request_from_line(line=_line(**fields))

    assert isinstance(refusal, str)
    assert expected in refusal


def test_a_request_parses_every_field_it_may_carry() -> None:
    request = request_from_line(
        line=_line(
            operation="proof_asset",
            proof_asset="/staging/a.txt",
            proof_asset_name="a.txt",
            proof_asset_store="proof-assets",
        )
    )

    assert not isinstance(request, str)
    assert request.proof_asset == Path("/staging/a.txt")
    assert (request.proof_asset_name, request.proof_asset_store) == ("a.txt", "proof-assets")
    assert request.comment_body is None
