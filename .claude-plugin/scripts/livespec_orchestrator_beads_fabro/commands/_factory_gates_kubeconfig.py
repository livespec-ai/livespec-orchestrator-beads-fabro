"""The optional gate-delegation kubeconfig one factory declares, as read."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._config import FactoryTarget

__all__: list[str] = [
    "FACTORY_GATES_KUBECONFIG_KEY",
    "NO_FACTORY_GATES_KUBECONFIG",
    "FactoryGatesKubeconfig",
    "factory_gates_kubeconfig_from_entry",
    "factory_gates_kubeconfig_path",
    "factory_gates_kubeconfig_refusal",
    "mountable_gates_kubeconfig",
    "render_gates_kubeconfig_mount",
]

FACTORY_GATES_KUBECONFIG_KEY = "gates_kubeconfig"
_GATES_KUBECONFIG_ENV_VAR = "GATES_KUBECONFIG"
_DEFAULT_GATES_KUBECONFIG_PATH = "/etc/ci-runner/gates.kubeconfig"


@dataclass(frozen=True, kw_only=True)
class FactoryGatesKubeconfig:
    """One factory entry's gate credential declaration, before it is graded."""

    declared: bool = False
    path: Path | None = None


NO_FACTORY_GATES_KUBECONFIG = FactoryGatesKubeconfig()


def factory_gates_kubeconfig_from_entry(*, entry: dict[str, Any]) -> FactoryGatesKubeconfig:
    """Read an optional non-empty path declaration without inspecting the file."""
    if FACTORY_GATES_KUBECONFIG_KEY not in entry:
        return NO_FACTORY_GATES_KUBECONFIG
    value = entry[FACTORY_GATES_KUBECONFIG_KEY]
    if not isinstance(value, str) or value == "":
        return FactoryGatesKubeconfig(declared=True)
    return FactoryGatesKubeconfig(declared=True, path=Path(value))


def factory_gates_kubeconfig_path(*, factory: FactoryTarget) -> Path | None:
    """Return the already-resolved credential path, if this factory declared one."""
    return factory.gates_kubeconfig.path


def factory_gates_kubeconfig_refusal(*, factory: FactoryTarget | None) -> str | None:
    """Refuse an empty or non-string gate credential declaration before claim."""
    if factory is None or not factory.gates_kubeconfig.declared:
        return None
    if factory.gates_kubeconfig.path is not None:
        return None
    key = f"dispatcher.factories.{factory.name}.{FACTORY_GATES_KUBECONFIG_KEY}"
    return f"ERROR: {key} must be a non-empty string naming a kubeconfig file\n"


def mountable_gates_kubeconfig(
    *, gates_kubeconfig: Path | None, warn_missing: Callable[[Path], object] | None
) -> Path | None:
    """Return an existing credential file, warning once when a declared one is absent."""
    if gates_kubeconfig is None or gates_kubeconfig.is_file():
        return gates_kubeconfig
    if warn_missing is not None:
        _ = warn_missing(gates_kubeconfig)
    return None


def render_gates_kubeconfig_mount(*, gates_kubeconfig: Path | None) -> str:
    """Render one read-only host-file mount without reading credential contents."""
    if gates_kubeconfig is None:
        return ""
    target = os.environ.get(_GATES_KUBECONFIG_ENV_VAR, _DEFAULT_GATES_KUBECONFIG_PATH)
    return (
        "[run.sandbox]\n"
        "mounts = [{ "
        f"source = {json.dumps(str(gates_kubeconfig))}, "
        f"target = {json.dumps(target)}, read_only = true }}]\n"
    )
