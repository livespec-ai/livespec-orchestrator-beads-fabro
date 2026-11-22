"""Credential-handling contract for the Honeycomb run_turn trigger provisioner.

The configuration key can write triggers, so it must reach curl through stdin
(`--header @-`), never through curl's argument vector, where it is readable
from `/proc/<pid>/cmdline` while a call runs. A recording `curl` shim on PATH
captures every argv and stdin, and the test asserts the key is absent from
every argv and present as an `X-Honeycomb-Team` header on every call's stdin.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO_ROOT / "orchestrator-image" / "provision-honeycomb-run-turn-trigger.sh"
_API_KEY = "run-turn-test-key-7f3a91"
_STDIN_MARKER = "-- curl stdin --"


def _write_recording_curl_stub(*, bin_dir: Path, recipients_json: str) -> None:
    stub = bin_dir / "curl"
    _ = stub.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'%s\\0\' "$@" >> "${CURL_ARGV_LOG}"\n'
        'printf \'%s\\n\' "-- curl stdin --" >> "${CURL_STDIN_LOG}"\n'
        "if [[ ! -t 0 ]]; then\n"
        '  cat >> "${CURL_STDIN_LOG}"\n'
        "fi\n"
        'cat "${RECIPIENTS_JSON}"\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    _ = (bin_dir / "recipients.json").write_text(recipients_json, encoding="utf-8")


def test_provisioner_keeps_the_api_key_out_of_curl_argv_and_sends_it_as_a_header(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl_argv_log = tmp_path / "curl-argv.log"
    curl_stdin_log = tmp_path / "curl-stdin.log"
    curl_argv_log.touch()
    curl_stdin_log.touch()
    recipients = [
        {
            "id": "email-recipient-1",
            "type": "email",
            "details": {"email_address": "operator@example.test"},
        }
    ]
    _write_recording_curl_stub(bin_dir=bin_dir, recipients_json=json.dumps(recipients))

    result = subprocess.run(
        ["bash", str(_SCRIPT)],
        check=False,
        env={
            **os.environ,
            "CURL_ARGV_LOG": str(curl_argv_log),
            "CURL_STDIN_LOG": str(curl_stdin_log),
            "DRY_RUN": "1",
            "HONEYCOMB_API_BASE": "https://honeycomb.test",
            "HONEYCOMB_CONFIG_KEY_LIVESPEC": _API_KEY,
            "HONEYCOMB_OPERATOR_ALERT_RECIPIENT": "operator@example.test",
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "RECIPIENTS_JSON": str(bin_dir / "recipients.json"),
        },
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    argv = curl_argv_log.read_bytes()
    stdin = curl_stdin_log.read_text(encoding="utf-8")
    calls = stdin.count(f"{_STDIN_MARKER}\n")
    assert calls > 0
    assert _API_KEY.encode() not in argv
    assert stdin.count(f"X-Honeycomb-Team: {_API_KEY}\n") == calls
