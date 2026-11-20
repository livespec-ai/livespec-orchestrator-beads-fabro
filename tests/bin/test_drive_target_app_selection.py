"""The direct ``drive`` entry point selects the target repository's App.

The host wrapper's default projection can still name a retired personal App.
This is deliberately a process-level test: only the real ``bin/drive.py``
bootstrap has to apply the target repository's committed credential wrapper
before importing and dispatching the command.  Calling a helper directly would
leave a regression that direct operator invocations can still reach.
"""

from __future__ import annotations

import runpy
import sys
import types
from pathlib import Path

import pytest

_BIN_DIR = Path(__file__).resolve().parents[2] / ".claude-plugin" / "scripts" / "bin"
_DRIVE = _BIN_DIR / "drive.py"


def test_direct_drive_requires_the_target_app_credential_projection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A direct drive must apply its target's wrapper even with an ambient App.

    The force flag is the entry-point half of the no-launcher guarantee.  It
    prevents the generic credential bootstrap from treating an already-present
    (but retired) App as sufficient and skipping the target repository's
    committed projection.
    """
    calls: list[dict[str, object]] = []
    bootstrap_module = types.ModuleType("_bootstrap")
    bootstrap_module.bootstrap = lambda **kwargs: calls.append(kwargs)  # type: ignore[attr-defined]
    command_module = types.ModuleType("livespec_orchestrator_beads_fabro.commands.drive")
    command_module.main = lambda: 0  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "_bootstrap", bootstrap_module)
    monkeypatch.setitem(
        sys.modules, "livespec_orchestrator_beads_fabro.commands.drive", command_module
    )

    with pytest.raises(SystemExit) as excinfo:
        runpy.run_path(str(_DRIVE), run_name="__main__")

    assert excinfo.value.code == 0
    assert calls == [{"force_credential_wrapper": True}]
