"""A passing test leaves no tmp_path files behind under this repository's pytest config.

A suite run wrote about 105k files per run under pytest's basetemp on /tmp, and the
retained pytest-N directories of repeated runs exhausted a seat host's tmpfs inodes
(livespec-dev-tooling-jxhi63). The repository's own `[tool.pytest.ini_options]`
retention keys must make a passing test's `tmp_path` directory disappear.
"""

from pathlib import Path

import pytest
import tomli

__all__: list[str] = []

pytest_plugins = ("pytester",)

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"

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
