"""A passing test leaves no tmp_path files behind under this repository's pytest config.

A suite run wrote about 105k files per run under pytest's basetemp on /tmp, and the
retained pytest-N directories of repeated runs exhausted a seat host's tmpfs inodes
(livespec-dev-tooling-jxhi63). The repository's own `[tool.pytest.ini_options]`
retention keys must make a passing test's `tmp_path` directory disappear.
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

_WRITER = """
def test_writes_files(tmp_path):
    for index in range(20):
        (tmp_path / f"retention_marker_{index}.txt").write_text("x")
"""


def test_a_passing_tests_tmp_path_files_are_removed(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    options = tomli.loads(_PYPROJECT.read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    temproot = tmp_path / "temproot"
    temproot.mkdir()
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temproot))
    ini_lines = ["[pytest]"] + [
        f"{key} = {options[key]}" for key in options if key.startswith("tmp_path_retention")
    ]
    pytester.makeini("\n".join(ini_lines))
    pytester.makepyfile(_WRITER)

    result = pytester.runpytest_inprocess("-p", "no:cacheprovider")

    result.assert_outcomes(passed=1)
    assert list(temproot.rglob("retention_marker_*.txt")) == []


def _removable_fixture_conftest() -> str:
    """The real `_tmp_path_stays_removable` fixture of tests/conftest.py, lifted into a conftest."""
    source = _CONFTEST.read_text(encoding="utf-8")
    fixture = next(
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef) and node.name == "_tmp_path_stays_removable"
    )
    first_line = fixture.decorator_list[0].lineno
    body = "\n".join(source.splitlines()[first_line - 1 : fixture.end_lineno])
    header = "import os\nfrom collections.abc import Iterator\nfrom pathlib import Path\nimport pytest\n\n\n"
    return header + body + "\n"


_READONLY_WRITER = """
import os


def test_leaves_a_non_writable_tree(tmp_path):
    objects = tmp_path / "run-from" / ".git" / "objects" / "ab"
    objects.mkdir(parents=True)
    (objects / "retention_marker_object").write_text("x")
    (objects / "retention_marker_object").chmod(0o444)
    for directory in (objects, objects.parent, objects.parent.parent, objects.parent.parent.parent):
        directory.chmod(0o555)
"""


def test_a_passing_tests_non_writable_tree_is_removed(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    options = tomli.loads(_PYPROJECT.read_text(encoding="utf-8"))["tool"]["pytest"]["ini_options"]
    temproot = tmp_path / "temproot"
    temproot.mkdir()
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temproot))
    ini_lines = ["[pytest]"] + [
        f"{key} = {options[key]}" for key in options if key.startswith("tmp_path_retention")
    ]
    pytester.makeini("\n".join(ini_lines))
    pytester.makeconftest(_removable_fixture_conftest())
    pytester.makepyfile(_READONLY_WRITER)

    result = pytester.runpytest_inprocess("-p", "no:cacheprovider")

    leftovers = [str(path) for path in temproot.rglob("retention_marker_object")]
    for directory, _subdirectories, _files in os.walk(temproot):
        Path(directory).chmod(0o755)
    result.assert_outcomes(passed=1)
    assert leftovers == []
