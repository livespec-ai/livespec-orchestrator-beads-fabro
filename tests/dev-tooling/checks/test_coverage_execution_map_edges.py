"""Edge cases for the producer of the affected-tests coverage-execution map."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import coverage

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "_coverage_execution_map.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("coverage_execution_map_edges", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_module_executed_only_outside_any_test_is_left_out_of_the_map(*, tmp_path: Path) -> None:
    """Collection-time and subprocess lines name no test, so the gate must fall back for them."""
    module = _load()
    data_file = tmp_path / "coverage.dat"
    data = coverage.CoverageData(basename=str(data_file))
    data.set_context("")
    data.add_lines({str(tmp_path / "pkg" / "only_import.py"): [1]})
    data.write()

    recorded = module.build_map(data_file=data_file, root=tmp_path, commit="abc")

    assert recorded == {"default_branch_commit": "abc", "modules": {}}
