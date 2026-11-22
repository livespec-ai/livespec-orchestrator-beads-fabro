"""The credential helper is driven by REAL git over http, from an agent stage.

Measured 2026-11-22 in the factory sandbox image: over http, git asks its credential helper
from `git remote-http`, a child of the user's `git fetch` or `git push`. The helper walked up
to the nearest `git` ancestor and read its subcommand, which was `remote-http`: not a read
subcommand, so a real `git fetch` was refused as `git_push`. The fake `git` of the sibling
tests asks the helper directly and never exercised that shape.

These tests use real git and a real local http remote (`git http-backend`, answering 401
until it is given a credential), with the installed wrapper as git's credential helper and the
dispatcher's record naming an agent stage. A fetch must be served a credential and a push must
be refused, whatever the process tree git builds.
"""

import http.server
import os
import subprocess
import threading
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_agent_stage_record_ssipvb import (
    _RECORD_NAME,
    _agent_env,
    _installed_wrapper,
    _record_stage,
)
from tests.livespec_orchestrator_beads_fabro.commands.test_dispatcher_gh_refresh_worktree import (
    _write_executable,
)


def _handler(*, root: Path) -> type[http.server.BaseHTTPRequestHandler]:
    class Handler(http.server.BaseHTTPRequestHandler):
        def _serve(self) -> None:
            if "Authorization" not in self.headers:
                self.send_response(401)
                self.send_header("WWW-Authenticate", 'Basic realm="r"')
                self.end_headers()
                return
            path, _, query = self.path.partition("?")
            length = int(self.headers.get("Content-Length") or 0)
            env = {
                "GIT_PROJECT_ROOT": str(root),
                "GIT_HTTP_EXPORT_ALL": "1",
                "PATH_INFO": path,
                "QUERY_STRING": query,
                "REQUEST_METHOD": self.command,
                "CONTENT_TYPE": self.headers.get("Content-Type", ""),
                "CONTENT_LENGTH": str(length),
                "REMOTE_USER": "x",
                "PATH": os.environ["PATH"],
            }
            out = subprocess.run(
                ["git", "http-backend"],
                input=self.rfile.read(length),
                env=env,
                capture_output=True,
                check=False,
            ).stdout
            head, _, body = out.partition(b"\r\n\r\n")
            status = 200
            for line in head.split(b"\r\n"):
                if line.lower().startswith(b"status:"):
                    status = int(line.split()[1])
            self.send_response(status)
            for line in head.split(b"\r\n"):
                if line and not line.lower().startswith(b"status:"):
                    key, _, value = line.partition(b":")
                    self.send_header(key.decode(), value.strip().decode())
            self.end_headers()
            self.wfile.write(body)

        do_GET = _serve  # noqa: N815
        do_POST = _serve  # noqa: N815

        def log_message(self, format: str, *args: object) -> None:  # noqa: ARG002
            return

    return Handler


@pytest.fixture
def http_remote(tmp_path: Path) -> Iterator[str]:
    """A bare repository behind a local http server that wants a credential."""
    served = tmp_path / "srv"
    bare = served / "repo.git"
    bare.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "-C", str(bare), "config", "http.receivepack", "true"], check=True)
    server = http.server.HTTPServer(("127.0.0.1", 0), _handler(root=served))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/repo.git"
    server.shutdown()
    thread.join()


def _agent_git(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str, remote: str
) -> tuple[Path, dict[str, str], Path]:
    """The installed wrapper as git's credential helper, a recorded agent stage, a real remote."""
    repo, bundle_root, bin_dir, capture = _installed_wrapper(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )
    _record_stage(record=bundle_root / _RECORD_NAME, stage=stage)
    # The real gh behind the wrapper serves a credential for `auth git-credential`.
    _write_executable(
        path=bin_dir / "gh.livespec-real",
        source="#!/usr/bin/env bash\n"
        'printf "args=%s\\n" "$*" >> "$GH_CAPTURE"\n'
        'if test "$1 $2" = "auth git-credential"; then\n'
        "  cat >/dev/null\n"
        '  printf "username=x-access-token\\npassword=stub-token\\n"\n'
        "fi\n",
    )
    for key, value in (
        ("remote.origin.url", remote),
        ("remote.origin.fetch", "+refs/heads/*:refs/remotes/origin/*"),
        ("credential.helper", "!gh auth git-credential"),
    ):
        subprocess.run(["git", "config", key, value], cwd=repo, check=True)
    env = _agent_env(bin_dir=bin_dir, capture=capture, tmp_path=tmp_path)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return repo, env, capture


@pytest.mark.parametrize("stage", ["implement", "proof_verify"])
def test_a_real_git_fetch_over_http_still_gets_a_credential(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, http_remote: str, stage: str
) -> None:
    repo, env, capture = _agent_git(
        tmp_path=tmp_path, monkeypatch=monkeypatch, stage=stage, remote=http_remote
    )

    result = subprocess.run(
        ["git", "fetch", "origin"], cwd=repo, env=env, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert "args=auth git-credential get" in capture.read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("stage", ["implement", "proof_verify"])
def test_a_real_git_push_over_http_is_refused_and_nothing_lands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, http_remote: str, stage: str
) -> None:
    repo, env, _capture = _agent_git(
        tmp_path=tmp_path, monkeypatch=monkeypatch, stage=stage, remote=http_remote
    )

    result = subprocess.run(
        ["git", "push", "origin", "HEAD:refs/heads/feat/x"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert f"LIVESPEC_AGENT_PUBLICATION_DENIED: stage={stage} action=git_push" in result.stderr
    landed = subprocess.run(
        ["git", "-C", str(tmp_path / "srv" / "repo.git"), "for-each-ref"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert landed.stdout == ""
