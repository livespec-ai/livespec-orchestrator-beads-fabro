"""Integration wiring for the bd-guard remote-exec client (livespec-dev-tooling-tbhqye).

The shell harness owns the behavioural observations (wire format, local-vs-remote
routing, 255 fallback, no retry on a remote nonzero status). This test binds
that harness, and the installer/rollback handling of the client, to the declared
``check-bd-guard`` target so it cannot become a locally runnable but un-gated
shell test.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GUARD_DIR = _REPO_ROOT / "bd-guard"


def test_check_bd_guard_runs_and_lints_the_remote_client_harness() -> None:
    """The declared gate lints bd-remote.sh and runs its hermetic harness."""
    check_body = (_REPO_ROOT / "dev-tooling" / "just-check-bd-guard.sh").read_text(encoding="utf-8")

    assert "bd-guard/bd-remote.sh" in check_body
    assert "bash bd-guard/test/test-bd-remote.sh" in check_body


def test_install_and_rollback_handle_the_remote_client_consistently() -> None:
    """install.sh lays bd-remote.sh beside the guard; rollback.sh removes it."""
    install_body = (_GUARD_DIR / "install.sh").read_text(encoding="utf-8")
    rollback_body = (_GUARD_DIR / "rollback.sh").read_text(encoding="utf-8")

    assert '"${BIN_DIR}/bd-remote.sh"' in install_body
    assert '"${BIN_DIR}/bd-remote.sh"' in rollback_body


def test_guard_routes_through_the_client_only_when_a_socket_is_configured() -> None:
    """The guard's opt-in gate requires the config file and a live socket."""
    guard_body = (_GUARD_DIR / "bd-guard.sh").read_text(encoding="utf-8")

    assert "livespec-bd-remote.conf" in guard_body
    assert '[ -S "$_bdg_sock" ]' in guard_body
