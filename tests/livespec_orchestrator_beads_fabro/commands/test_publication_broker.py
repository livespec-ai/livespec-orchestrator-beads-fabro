"""The broker launched as its own process: the real executable path, not an injected main."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[3] / ".claude-plugin" / "scripts"
_MODULE = "livespec_orchestrator_beads_fabro.commands.publication_broker"
_SECRET = "broker-only-secret"

# A stand-in `gh` that records what the broker's child could see: its own argv and
# GH_TOKEN, and the broker process's environment (its parent) as the kernel reports it.
_FAKE_GH = """#!/bin/sh
{
  printf 'argv=%s\\n' "$*"
  printf 'child_token=%s\\n' "$GH_TOKEN"
  if tr '\\0' '\\n' < "/proc/$PPID/environ" | grep -q '^GH_TOKEN='; then
    printf 'broker_env_has_token=yes\\n'
  else
    printf 'broker_env_has_token=no\\n'
  fi
} >> "$SEEN_FILE"
printf 'posted\\n'
"""


def _python_path() -> str:
    return os.pathsep.join((str(_SCRIPTS), str(_SCRIPTS / "_vendor")))


def _launch(*, tmp_path: Path, lines: list[str]) -> tuple[subprocess.CompletedProcess[str], Path]:
    seen = tmp_path / "seen.txt"
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    gh = fakebin / "gh"
    gh.write_text(_FAKE_GH, encoding="utf-8")
    gh.chmod(0o755)
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "record.md").write_text("proof", encoding="utf-8")
    state = tmp_path / "broker-state"
    state.mkdir(mode=0o700)
    launch = state / "launch.json"
    launch.write_text(
        json.dumps(
            {
                "stage": "proof_verify",
                "pull_request_number": 73,
                "proof_asset_store": "proof-assets",
                "request_directory": str(staging),
            }
        ),
        encoding="utf-8",
    )
    launch.chmod(0o600)
    credential = state / "credential"
    credential.write_text(_SECRET + "\n", encoding="utf-8")
    credential.chmod(0o600)
    environment = {
        "PATH": f"{fakebin}{os.pathsep}{os.environ['PATH']}",
        "PYTHONPATH": _python_path(),
        "SEEN_FILE": str(seen),
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            _MODULE,
            "--launch-file",
            str(launch),
            "--credential-file",
            str(credential),
        ],
        input="".join(line + "\n" for line in lines),
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env=environment,
        timeout=60,
    )
    return completed, seen


def _request(**fields: object) -> str:
    request: dict[str, object] = {
        "operation": "comment",
        "claimed_stage": "proof_verify",
        "pull_request_number": 73,
    }
    request.update(fields)
    return json.dumps(request)


@pytest.mark.skipif(
    not Path("/proc/self/environ").exists(), reason="reads the broker's environment from /proc"
)
def test_a_separately_launched_broker_holds_the_credential_and_the_agent_side_does_not(
    tmp_path: Path,
) -> None:
    body = f"{tmp_path}/staging/record.md"
    completed, seen = _launch(
        tmp_path=tmp_path,
        lines=[
            _request(comment_body=body),
            _request(claimed_stage="pr", comment_body=body),
            _request(operation="merge"),
        ],
    )

    replies = [json.loads(line) for line in completed.stdout.splitlines()]
    assert completed.returncode == 0, completed.stderr
    assert len(replies) == 3, completed.stdout
    assert replies[0] == {"refusal": None, "exit_code": 0, "stdout": "posted\n"}
    assert "claimed stage" in str(replies[1]["refusal"])
    assert "only a new comment" in str(replies[2]["refusal"])
    recorded = seen.read_text(encoding="utf-8")
    assert f"argv=pr comment 73 --body-file {body}" in recorded
    assert f"child_token={_SECRET}" in recorded
    assert "broker_env_has_token=no" in recorded
    assert recorded.count("argv=") == 1
    # What the agent side can reach: its own environment, the process output and the
    # staging directory it writes to.  None of them carries the credential.
    assert _SECRET not in "\n".join(os.environ.values())
    assert _SECRET not in completed.stdout + completed.stderr
    assert all(
        _SECRET not in path.read_text(encoding="utf-8") for path in (tmp_path / "staging").iterdir()
    )


def test_a_broker_launched_without_its_two_files_refuses_to_start(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", _MODULE],
        input="",
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
        env={"PATH": os.environ["PATH"], "PYTHONPATH": _python_path()},
        timeout=60,
    )

    assert completed.returncode == 1
    assert "usage" in completed.stderr
