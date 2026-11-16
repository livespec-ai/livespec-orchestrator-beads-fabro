"""A passing test's `tmp_path_factory.mktemp` directories are removed after the test.

pytest's `tmp_path_retention_policy` prunes only the `tmp_path` fixture's directory, so
the directories fixtures make through `tmp_path_factory.mktemp` (seven per test in
tests/conftest.py) stay in /tmp until the host runs out of inodes
(livespec-dev-tooling-jxhi63, follow-up to livespec-orchestrator-beads-fabro#5385).
"""

import ast
import os
from pathlib import Path

import pytest
import tomli

__all__: list[str] = []

pytest_plugins = ("pytester",)

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
_CONFTEST = Path(__file__).resolve().parent / "conftest.py"
_LIFTED = ("_CALL_REPORT", "pytest_runtest_makereport", "_make_removable", "_factory_dirs_removed")

_WRITER = """
def test_makes_factory_dirs(tmp_path_factory):
    scratch = tmp_path_factory.mktemp("factory-marker")
    (scratch / "factory_marker_file.txt").write_text("x")
    guarded = tmp_path_factory.mktemp("factory-guarded") / "sub"
    guarded.mkdir()
    (guarded / "factory_marker_guarded.txt").write_text("x")
    guarded.chmod(0o555)
"""

_FAILING_WRITER = """
def test_makes_factory_dirs_then_fails(tmp_path_factory):
    scratch = tmp_path_factory.mktemp("factory-marker")
    (scratch / "factory_marker_kept.txt").write_text("x")
    assert False
"""


def _lifted_conftest() -> str:
    """The real factory-dir cleanup of tests/conftest.py, lifted into a conftest."""
    source = _CONFTEST.read_text(encoding="utf-8")
    lines = source.splitlines()
    chunks = []
    for node in ast.parse(source).body:
        name = (
            node.targets[0].id
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
            else getattr(node, "name", None)
        )
        if name in _LIFTED:
            first = min(
                [node.lineno, *(item.lineno for item in getattr(node, "decorator_list", []))]
            )
            chunks.append("\n".join(lines[first - 1 : node.end_lineno]))
    header = "import os\nimport shutil\nfrom collections.abc import Generator, Iterator\nfrom pathlib import Path\nimport pytest\n\n\n"
    return header + "\n\n\n".join(chunks) + "\n"


def _run(
    *, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, writer: str
) -> tuple[pytest.RunResult, Path]:
    options = tomli.loads(_PYPROJECT.read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    temproot = tmp_path / "temproot"
    temproot.mkdir()
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temproot))
    ini_lines = ["[pytest]"] + [
        f"{key} = {options[key]}" for key in options if key.startswith("tmp_path_retention")
    ]
    pytester.makeini("\n".join(ini_lines))
    pytester.makeconftest(_lifted_conftest())
    pytester.makepyfile(writer)
    result = pytester.runpytest_inprocess("-p", "no:cacheprovider")
    return result, temproot


def _unlock(*, root: Path) -> None:
    for directory, _subdirectories, _files in os.walk(root):
        Path(directory).chmod(0o755)


def test_a_passing_tests_factory_dirs_are_removed(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, temproot = _run(
        pytester=pytester, monkeypatch=monkeypatch, tmp_path=tmp_path, writer=_WRITER
    )

    leftovers = [str(path) for path in temproot.rglob("factory_marker_*.txt")]
    _unlock(root=temproot)
    result.assert_outcomes(passed=1)
    assert leftovers == []


def test_a_failing_tests_factory_dirs_are_kept_for_diagnosis(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result, temproot = _run(
        pytester=pytester, monkeypatch=monkeypatch, tmp_path=tmp_path, writer=_FAILING_WRITER
    )

    kept = [path.name for path in temproot.rglob("factory_marker_kept.txt")]
    result.assert_outcomes(failed=1)
    assert kept == ["factory_marker_kept.txt"]
