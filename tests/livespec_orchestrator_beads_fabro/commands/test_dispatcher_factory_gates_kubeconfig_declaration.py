"""Scenario 381's absent, missing, and malformed factory credential arms."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._config import resolve_fabro_factory
from livespec_orchestrator_beads_fabro.commands._factory_gates_kubeconfig import (
    factory_gates_kubeconfig_path,
    factory_gates_kubeconfig_refusal,
    mountable_gates_kubeconfig,
)
from livespec_orchestrator_beads_fabro.commands.dispatcher import dispatch_preamble

_FACTORY = "petri"
_EXIT_PRECONDITION_ERROR = 3


def _write_config(*, repo: Path, value: object = None, declared: bool = False) -> None:
    factory: dict[str, object] = {}
    if declared:
        factory["gates_kubeconfig"] = value
    payload = {
        "livespec-orchestrator-beads-fabro": {
            "dispatcher": {"factories": {_FACTORY: factory}, "default_factory": _FACTORY}
        }
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(payload), encoding="utf-8")


def test_absent_key_projects_no_path_or_mount(tmp_path: Path) -> None:
    _write_config(repo=tmp_path)

    target = resolve_fabro_factory(cwd=tmp_path)

    assert factory_gates_kubeconfig_path(factory=target) is None
    assert mountable_gates_kubeconfig(gates_kubeconfig=None, warn_missing=None) is None


def test_existing_file_declaration_is_accepted_without_reading_it(tmp_path: Path) -> None:
    credential = tmp_path / "factory-gates.kubeconfig"
    _write_config(repo=tmp_path, value=str(credential), declared=True)

    target = resolve_fabro_factory(cwd=tmp_path)

    assert factory_gates_kubeconfig_path(factory=target) == credential
    assert factory_gates_kubeconfig_refusal(factory=target) is None
    assert factory_gates_kubeconfig_refusal(factory=None) is None
    assert mountable_gates_kubeconfig(gates_kubeconfig=credential, warn_missing=None) is None


def test_missing_file_warns_once_and_does_not_select_a_mount(tmp_path: Path) -> None:
    missing = tmp_path / "missing-gates.kubeconfig"
    warnings: list[Path] = []

    mounted = mountable_gates_kubeconfig(gates_kubeconfig=missing, warn_missing=warnings.append)

    assert mounted is None
    assert warnings == [missing]


@pytest.mark.parametrize("value", ["", 7, None, [], {}])
def test_invalid_factory_value_refuses_before_claim(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], *, value: object
) -> None:
    _write_config(repo=tmp_path, value=value, declared=True)

    result = dispatch_preamble(
        args=argparse.Namespace(fabro_bin=None, janitor=None, journal=None), repo=tmp_path
    )

    assert result == (None, _EXIT_PRECONDITION_ERROR)
    assert f"dispatcher.factories.{_FACTORY}.gates_kubeconfig" in capsys.readouterr().err
