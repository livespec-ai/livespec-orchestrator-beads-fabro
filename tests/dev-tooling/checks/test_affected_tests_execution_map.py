"""Validation cases for the affected-tests coverage-execution map."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "_affected_tests_selection.py"
_PACKAGE = ".claude-plugin/scripts/pkg"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("affected_tests_selection_map", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run(*, root: Path, arguments: list[str]) -> None:
    completed = subprocess.run(
        ["git", *arguments], cwd=root, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def _repository(*, tmp_path: Path) -> tuple[Path, str]:
    root = tmp_path / "repo"
    files = {
        "pyproject.toml": (
            "[tool.livespec_dev_tooling]\n"
            f'source_tree_prefixes = ["{_PACKAGE}/"]\n'
            "[[tool.livespec_dev_tooling.mirror_pairings]]\n"
            f'source_tree = "{_PACKAGE}"\n'
            'test_tree = "tests/pkg"\n'
        ),
        f"{_PACKAGE}/__init__.py": "",
        f"{_PACKAGE}/a.py": "VALUE = 1\n",
        f"{_PACKAGE}/b.py": "from . import a\n",
        "tests/pkg/test_a.py": "def test_a() -> None: ...\n",
        "tests/pkg/test_b.py": "import pkg.b\n",
        "tests/pkg/test_direct.py": "import pkg.a\n",
    }
    for relative, text in files.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _ = target.write_text(text, encoding="utf-8")
    _run(root=root, arguments=["init", "--quiet", "-b", "master"])
    _run(root=root, arguments=["add", "."])
    _run(
        root=root,
        arguments=["-c", "user.name=t", "-c", "user.email=t@e.invalid", "commit", "-qm", "base"],
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    return root, commit


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"default_branch_commit": "not-a-commit", "modules": {}},
        {"default_branch_commit": "CURRENT", "modules": {_PACKAGE + "/a.py": "not-a-list"}},
        {"default_branch_commit": "CURRENT", "modules": {_PACKAGE + "/a.py": []}},
    ],
)
def test_an_invalid_coverage_execution_map_falls_back_to_importers(
    *, tmp_path: Path, payload: object
) -> None:
    """Malformed, stale, or empty records cannot narrow the conservative fallback."""
    module = _load()
    root, commit = _repository(tmp_path=tmp_path)
    map_path = root / "dev-tooling" / "coverage-execution-map.json"
    map_path.parent.mkdir()
    if isinstance(payload, dict):
        payload = json.loads(json.dumps(payload).replace("CURRENT", commit))
    _ = map_path.write_text(json.dumps(payload), encoding="utf-8")

    outcome = module.select(root=root, changed=[f"{_PACKAGE}/a.py"])

    assert "tests/pkg/test_b.py" in outcome.tests
