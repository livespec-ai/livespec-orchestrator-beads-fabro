"""Compose the publication broker's helper bundle for the sandbox registry.

The broker is the process that holds a forge credential beside an agent stage, so
it must come from the dispatching build, never from the target repository's clone
(only this orchestrator's own clone carries it). It rides the helper-fetch bundle
exactly as the App-token mint helper does: the registry names each file and its
sha256, and the setup step writes them, digest-verified at the pinned commit,
below the gh-refresh bundle root and OUTSIDE the run's working tree.

The helper-fetch checkout is deleted after setup, so the broker's few package
files are written beside its entry point, under `lib/`, and the entry point puts
that directory (and nothing from the target clone) on `sys.path`. The set below is
the broker's whole import closure: `_dispatcher_command_types` exists so it stays
that small instead of reaching `_dispatcher_engine_types` and its ~75 modules.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_model import Helper

__all__: list[str] = [
    "PUBLICATION_BROKER_RELPATH",
    "publication_broker_entry_source",
    "publication_broker_helpers",
]

_GH_REFRESH_ROOT = "gh-refresh"
_EXECUTABLE = 0o755
_READABLE = 0o644
# Where the entry point lands, relative to the gh-refresh bundle root; the two
# prompts that launch the broker name it.
PUBLICATION_BROKER_RELPATH = "bin/publication_broker.py"
_LIBRARY_DIRECTORY = "lib"
_PACKAGE = "livespec_orchestrator_beads_fabro"
# The broker's whole import closure, relative to the plugin's `scripts/` directory.
_PACKAGE_FILES = (
    f"{_PACKAGE}/__init__.py",
    f"{_PACKAGE}/commands/__init__.py",
    f"{_PACKAGE}/commands/_dispatcher_command_types.py",
    f"{_PACKAGE}/commands/_dispatcher_publication_broker.py",
    f"{_PACKAGE}/commands/_dispatcher_publication_broker_serve.py",
    f"{_PACKAGE}/commands/_dispatcher_shell_runner.py",
    f"{_PACKAGE}/commands/publication_broker.py",
    f"{_PACKAGE}/effects/__init__.py",
    f"{_PACKAGE}/effects/_attempt.py",
    f"{_PACKAGE}/io/__init__.py",
    f"{_PACKAGE}/io/_stdio.py",
)
_ENTRY_SOURCE = """#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from livespec_orchestrator_beads_fabro.commands.publication_broker import main

raise SystemExit(main())
"""


def publication_broker_entry_source() -> str:
    """The bundled launcher: it imports only from the bundle's own `lib/` directory."""
    return _ENTRY_SOURCE


def _file(*, path: Path) -> Callable[[], bytes]:
    return path.read_bytes


def publication_broker_helpers(*, scripts_root: Path) -> tuple[Helper, ...]:
    """The broker's launcher plus, file by file, the package modules it imports."""
    entry = Helper(
        name="publication-broker",
        root=_GH_REFRESH_ROOT,
        path=PUBLICATION_BROKER_RELPATH,
        mode=_EXECUTABLE,
        compose=lambda: publication_broker_entry_source().encode("utf-8"),
    )
    library = tuple(
        Helper(
            name=f"publication-broker-support/{relpath}",
            root=_GH_REFRESH_ROOT,
            path=f"{_LIBRARY_DIRECTORY}/{relpath}",
            mode=_READABLE,
            compose=_file(path=scripts_root / relpath),
        )
        for relpath in _PACKAGE_FILES
    )
    return (entry, *library)
