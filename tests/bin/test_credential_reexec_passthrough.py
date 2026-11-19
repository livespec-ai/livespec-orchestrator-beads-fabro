"""Integration coverage for credential-wrapper re-exec exit surfaces.

These tests use the shipped Dispatcher bin entry point with its real bootstrap
and a real wrapper process.  The first wrapper supplies the missing tenant
secret and the re-executed Dispatcher rejects an invalid command.  That makes
the child write only its normal argparse refusal to stderr, so both its stream
and exit code must survive the bootstrap unchanged.  The second wrapper path
cannot start at all, exercising the bootstrap diagnostic rather than a raw
``subprocess.run`` traceback.  The direct test covers both Python startup
exceptions because the real child intentionally runs without coverage
instrumentation.

Real processes are required to observe re-exec and the child's OS exit status,
so this file is declared in ``subprocess_spawn_allowlist`` and scrubs coverage
instrumentation from every child environment.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from livespec_runtime.credentials import CREDENTIAL_REEXEC_SENTINEL, Reexec

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DISPATCHER = _REPO_ROOT / ".claude-plugin" / "scripts" / "bin" / "dispatcher.py"
_BIN_DIR = _DISPATCHER.parent
_WRAPPER_SEPARATOR = "--"
_TIMEOUT_SECONDS = 60


def _child_environment(*, marker: Path | None = None) -> dict[str, str]:
    """Build an uncredentialed, uninstrumented environment for one entry point."""
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in {"BEADS_DOLT_PASSWORD", "COVERAGE_PROCESS_START"}
        and not name.startswith("COV_CORE_")
        and not name.startswith("GIT_")
    }
    _ = environment.pop("LIVESPEC_CREDENTIAL_REEXEC", None)
    if marker is not None:
        environment["LIVESPEC_TEST_CREDENTIAL_WRAPPER_MARKER"] = str(marker)
    return environment


def _write_target(*, root: Path, credential_wrapper: list[str]) -> None:
    """Make ``root`` a server-ledger target that must self-heal credentials."""
    beads = root / ".beads"
    beads.mkdir()
    _ = (beads / "config.yaml").write_text("dolt.mode: server\n", encoding="utf-8")
    _ = (root / ".livespec.jsonc").write_text(
        json.dumps({"credential_wrapper": credential_wrapper}), encoding="utf-8"
    )


def _import_bootstrap() -> object:
    if str(_BIN_DIR) not in sys.path:
        sys.path.insert(0, str(_BIN_DIR))
    sys.modules.pop("_bootstrap", None)
    return importlib.import_module("_bootstrap")


def _run_dispatcher(*, cwd: Path, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_DISPATCHER), "not-a-dispatcher-command"],
        capture_output=True,
        check=False,
        cwd=str(cwd),
        env=environment,
        text=True,
        timeout=_TIMEOUT_SECONDS,
    )


def test_reexecuted_dispatcher_refusal_preserves_its_exit_and_stderr(tmp_path: Path) -> None:
    """A real child refusal is never relabelled as a credential-wrapper failure."""
    marker = tmp_path / "wrapper-invoked"
    wrapper = tmp_path / "credential-wrapper.sh"
    _ = wrapper.write_text(
        "#!/bin/sh\n"
        f'[ "$1" = "{_WRAPPER_SEPARATOR}" ] && shift\n'
        'printf invoked > "$LIVESPEC_TEST_CREDENTIAL_WRAPPER_MARKER"\n'
        "export BEADS_DOLT_PASSWORD=test-not-a-real-secret\n"
        "export GITHUB_APP_ID=test-not-a-real-app-id\n"
        "export GITHUB_PRIVATE_KEY=test-not-a-real-private-key\n"
        'exec "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    target = tmp_path / "target"
    target.mkdir()
    _write_target(root=target, credential_wrapper=[str(wrapper), _WRAPPER_SEPARATOR])

    completed = _run_dispatcher(cwd=target, environment=_child_environment(marker=marker))

    assert marker.exists(), f"credential wrapper was not invoked:\n{completed.stderr}"
    assert completed.returncode == 2, completed.stderr
    assert "invalid choice" in completed.stderr
    assert "credential_wrapper could not run" not in completed.stderr


def test_unstartable_credential_wrapper_reports_argv_and_missing_secret(tmp_path: Path) -> None:
    """A missing wrapper is diagnosed cleanly and identifies its configuration."""
    target = tmp_path / "target"
    target.mkdir()
    missing_wrapper = target / "credential-wrapper-is-missing"
    _write_target(root=target, credential_wrapper=[str(missing_wrapper), _WRAPPER_SEPARATOR])

    completed = _run_dispatcher(cwd=target, environment=_child_environment())

    assert completed.returncode == 3
    assert "credential_wrapper could not run in this environment" in completed.stderr
    assert str(missing_wrapper) in completed.stderr
    assert "BEADS_DOLT_PASSWORD" in completed.stderr
    assert "Traceback" not in completed.stderr


@pytest.mark.parametrize("startup_error", [FileNotFoundError, PermissionError])
def test_reexec_wrapper_startup_error_reports_configured_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    startup_error: type[OSError],
) -> None:
    """Both wrapper startup errors return the configured diagnostic cleanly."""
    wrapper = tmp_path / "credential-wrapper"
    _write_target(root=tmp_path, credential_wrapper=[str(wrapper), _WRAPPER_SEPARATOR])
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(CREDENTIAL_REEXEC_SENTINEL, raising=False)
    monkeypatch.setattr(
        "livespec_runtime.credentials.decide_credentials",
        lambda **_kwargs: Reexec(argv=(str(wrapper), _WRAPPER_SEPARATOR, "next.py")),
    )
    monkeypatch.setattr(
        subprocess, "run", lambda *_args, **_kwargs: (_ for _ in ()).throw(startup_error())
    )

    bootstrap_module = _import_bootstrap()
    with pytest.raises(SystemExit) as excinfo:
        bootstrap_module._self_heal_credentials()  # type: ignore[attr-defined]  # noqa: SLF001

    assert excinfo.value.code == 3
    captured = capsys.readouterr()
    assert str(wrapper) in captured.err
    assert "BEADS_DOLT_PASSWORD" in captured.err
    assert "Traceback" not in captured.err
