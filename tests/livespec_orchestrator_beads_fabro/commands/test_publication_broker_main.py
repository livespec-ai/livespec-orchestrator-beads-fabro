"""The broker's executable entry point, bound in-process to this process's own streams."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_publication_broker_serve as serve
from livespec_orchestrator_beads_fabro.commands.publication_broker import main


def _files(*, tmp_path: Path) -> list[str]:
    launch = tmp_path / "launch.json"
    launch.write_text(json.dumps({"stage": "review", "pull_request_number": 5}), encoding="utf-8")
    launch.chmod(0o600)
    credential = tmp_path / "credential"
    credential.write_text("broker-secret\n", encoding="utf-8")
    credential.chmod(0o600)
    return [
        serve.LAUNCH_FILE_FLAG,
        str(launch),
        serve.CREDENTIAL_FILE_FLAG,
        str(credential),
    ]


_FORGED = json.dumps({"operation": "merge", "claimed_stage": "pr", "pull_request_number": 5})


def test_main_binds_this_process_streams_and_refuses_a_merge_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = io.StringIO()
    monkeypatch.setattr(sys, "argv", ["publication_broker.py", *_files(tmp_path=tmp_path)])
    monkeypatch.setattr(sys, "stdin", io.StringIO(_FORGED + "\n"))
    monkeypatch.setattr(sys, "stdout", out)

    status = main()

    reply = json.loads(out.getvalue())
    assert status == 0
    assert "only a new comment" in reply["refusal"]
    assert reply["exit_code"] is None


def test_main_serves_an_explicit_argv_instead_of_the_process_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = io.StringIO()
    monkeypatch.setattr(sys, "argv", ["publication_broker.py"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(_FORGED + "\n"))
    monkeypatch.setattr(sys, "stdout", out)

    status = main(argv=_files(tmp_path=tmp_path))

    assert status == 0
    assert "only a new comment" in json.loads(out.getvalue())["refusal"]


def test_main_without_its_two_files_refuses_to_start(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["publication_broker.py"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    status = main()

    assert status == 1
    assert "usage" in capsys.readouterr().err
