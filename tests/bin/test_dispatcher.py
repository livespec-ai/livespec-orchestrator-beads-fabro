"""Per-wrapper coverage test for bin/dispatcher.py."""

import runpy
import sys
import types
from collections.abc import Callable
from pathlib import Path

import pytest

_DISPATCHER = (
    Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin" / "dispatcher.py"
)


def test_dispatcher_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "dispatcher.py",
        "livespec_orchestrator_beads_fabro.commands.dispatcher",
        0,
    )


def test_dispatcher_wrapper_selects_the_target_app_before_a_direct_resume(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []
    bootstrap_module = types.ModuleType("_bootstrap")
    bootstrap_module.bootstrap = lambda **kwargs: calls.append(kwargs)  # type: ignore[attr-defined]
    command_module = types.ModuleType("livespec_orchestrator_beads_fabro.commands.dispatcher")
    command_module.main = lambda: 0  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "_bootstrap", bootstrap_module)
    monkeypatch.setitem(
        sys.modules, "livespec_orchestrator_beads_fabro.commands.dispatcher", command_module
    )
    monkeypatch.setattr(sys, "argv", [str(_DISPATCHER), "resume"])

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(_DISPATCHER), run_name="__main__")

    assert excinfo.value.code == 0
    assert calls == [
        {
            "required": ("BEADS_DOLT_PASSWORD", "GITHUB_APP_ID", "GITHUB_PRIVATE_KEY"),
            "force_credential_wrapper_for_command": "resume",
        }
    ]
