"""The tmp hygiene fixtures survive tests that patch the filesystem or leave threads running.

livespec-orchestrator-beads-fabro#5385 and #5391 added autouse fixtures that remove a passing
test's tmp_path and tmp_path_factory directories. Tests in other fleet repos monkeypatch
`shutil.rmtree` and `Path.stat`, and some start a background thread that is still writing into
a directory when the test ends, so removal at teardown broke them (livespec-dev-tooling-jxhi63).
The fixtures must tolerate both.
"""

import ast
from pathlib import Path

import pytest

__all__: list[str] = []

pytest_plugins = ("pytester",)

_CONFTEST = Path(__file__).resolve().parent / "conftest.py"
_LIFTED = (
    "_tmp_path_stays_removable",
    "_CALL_REPORT",
    "pytest_runtest_makereport",
    "_make_removable",
    "_factory_dirs_removed",
)

_PATCHING_TEST = """
import shutil
from pathlib import Path


def _refuse(*_args, **_kwargs):
    raise OSError("controlled refusal")


def test_patches_rmtree_and_stat(tmp_path, tmp_path_factory, monkeypatch):
    (tmp_path_factory.mktemp("patched-factory") / "file.txt").write_text("x")
    (tmp_path / "file.txt").write_text("x")
    monkeypatch.setattr(shutil, "rmtree", _refuse)
    monkeypatch.setattr(Path, "stat", _refuse)
"""

_DEFERRED_TESTS = """
import pytest


@pytest.fixture(scope="module")
def made():
    return {}


def test_a_makes_a_factory_dir(tmp_path_factory, made):
    made["path"] = tmp_path_factory.mktemp("still-in-use")
    (made["path"] / "file.txt").write_text("x")


def test_b_finds_it_still_there(made):
    assert (made["path"] / "file.txt").exists()
"""


def _lifted_conftest() -> str:
    """The real fixtures of tests/conftest.py, lifted into a conftest."""
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
    header = (
        "import os\nimport shutil\nfrom collections.abc import Generator, Iterator\n"
        "from pathlib import Path\nimport pytest\n\n\n"
    )
    return header + "\n\n\n".join(chunks) + "\n"


def _session(
    *, pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tests: str
) -> pytest.RunResult:
    temproot = tmp_path / "temproot"
    temproot.mkdir()
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(temproot))
    pytester.makeini("[pytest]\ntmp_path_retention_policy = failed\ntmp_path_retention_count = 1")
    pytester.makeconftest(_lifted_conftest())
    pytester.makepyfile(tests)
    return pytester.runpytest_inprocess("-p", "no:cacheprovider")


def test_a_test_that_patches_rmtree_and_stat_is_not_broken_at_teardown(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _session(
        pytester=pytester, monkeypatch=monkeypatch, tmp_path=tmp_path, tests=_PATCHING_TEST
    )

    result.assert_outcomes(passed=1)


def test_a_passing_tests_factory_dir_outlives_the_test_until_the_session_ends(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result = _session(
        pytester=pytester, monkeypatch=monkeypatch, tmp_path=tmp_path, tests=_DEFERRED_TESTS
    )

    result.assert_outcomes(passed=2)
