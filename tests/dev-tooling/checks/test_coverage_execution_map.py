"""Cases for the producer of the affected-tests coverage-execution map."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import coverage
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "dev-tooling" / "checks" / "_coverage_execution_map.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("coverage_execution_map", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _record(*, data_file: Path, root: Path) -> None:
    """Write coverage data in which several contexts execute lines of two modules."""
    data = coverage.CoverageData(basename=str(data_file))
    data.set_context("")
    data.add_lines({str(root / "pkg" / "a.py"): [1]})
    data.set_context("tests/pkg/test_b.py::test_one|run")
    data.add_lines({str(root / "pkg" / "a.py"): [2], str(root / "pkg" / "c.py"): [1]})
    data.set_context("tests/pkg/test_a.py::test_two|run")
    data.add_lines({str(root / "pkg" / "a.py"): [2, 3], "/elsewhere/outside.py": [1]})
    data.set_context("tests/pkg/test_a.py::test_three|run")
    data.add_lines({str(root / "tests" / "pkg" / "test_a.py"): [1]})
    data.write()


def _git(*, root: Path, arguments: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@e.invalid", *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def test_a_module_maps_to_the_sorted_test_modules_whose_contexts_executed_it(
    *, tmp_path: Path
) -> None:
    """Contexts name tests; the empty context, outside files and tests are left out."""
    module = _load()
    data_file = tmp_path / "coverage.dat"
    _record(data_file=data_file, root=tmp_path)

    recorded = module.build_map(data_file=data_file, root=tmp_path, commit="abc")

    assert recorded == {
        "default_branch_commit": "abc",
        "modules": {
            "pkg/a.py": ["tests/pkg/test_a.py", "tests/pkg/test_b.py"],
            "pkg/c.py": ["tests/pkg/test_b.py"],
        },
    }


def test_main_writes_the_map_recorded_at_the_merge_base_with_the_default_branch(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The map is written one module per line, tied to the default-branch merge base."""
    module = _load()
    root = tmp_path / "repo"
    root.mkdir()
    _ = _git(root=root, arguments=["init", "--quiet", "-b", "master"])
    _ = (root / "f.txt").write_text("x", encoding="utf-8")
    _ = _git(root=root, arguments=["add", "."])
    _ = _git(root=root, arguments=["commit", "-qm", "base"])
    base = _git(root=root, arguments=["rev-parse", "HEAD"])
    _ = _git(root=root, arguments=["update-ref", "refs/remotes/origin/master", base])
    data_file = tmp_path / "coverage.dat"
    _record(data_file=data_file, root=root)
    output = tmp_path / "out" / "map.json"
    monkeypatch.chdir(root)
    monkeypatch.setattr(sys, "argv", ["prog", str(data_file), str(output)])

    status = module.main()

    assert status == 0
    text = output.read_text(encoding="utf-8")
    assert json.loads(text)["default_branch_commit"] == base
    assert '    "pkg/c.py": ["tests/pkg/test_b.py"]' in text.splitlines()
    assert text.endswith("\n")
