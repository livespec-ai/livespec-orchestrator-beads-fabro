"""_coverage_execution_map — records which test modules executed each product module.

The affected-tests gate (`_affected_tests_selection`) can select, for a changed product
module, the test modules a recorded coverage run saw execute it, instead of every test
module that reaches it through a hub module's imports (work-item bd-ib-uvx5l7). This is
the PRODUCER of that record: it reads the coverage data of ONE full-suite run taken with
`--cov-context=test` and writes `dev-tooling/coverage-execution-map.json`, one product
module per line, each mapped to the sorted test modules that executed a line of it.

A context is a pytest node id (`tests/x/test_y.py::test_z|run`); its test module is the
part before `::`. Lines run outside any test, at collection time, or in a subprocess carry
the empty context and name no test, so a module executed only that way is left out and the
gate falls back to the import graph for it. Files outside the repository root and the test
modules themselves are not product modules and are left out too.

The map records the default-branch commit the run was taken at, so the gate can tell a
record from an unrelated history. `just coverage-execution-map` runs the suite and calls
this module; a regenerated map is committed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import coverage

__all__: list[str] = ["build_map", "main"]

_DEFAULT_BRANCH_REF = "origin/master"
_TESTS_PREFIX = "tests/"


def _relative(*, file: str, root: Path) -> str | None:
    """The repo-relative path of a measured product file, or None when it is not one."""
    try:
        relative = Path(file).relative_to(root).as_posix()
    except ValueError:
        return None
    return None if relative.startswith(_TESTS_PREFIX) else relative


def _test_module(*, context: str) -> str | None:
    """The test module a pytest node-id context belongs to, or None for the empty context."""
    module, separator, _ = context.partition("::")
    return module if separator else None


def build_map(*, data_file: Path, root: Path, commit: str) -> dict[str, Any]:
    """The execution map for the coverage data in `data_file`, recorded at `commit`."""
    data = coverage.CoverageData(basename=str(data_file))
    data.read()
    modules: dict[str, list[str]] = {}
    for file in sorted(data.measured_files()):
        relative = _relative(file=file, root=root)
        if relative is None:
            continue
        contexts = {c for per_line in data.contexts_by_lineno(file).values() for c in per_line}
        executors = {_test_module(context=c) for c in contexts} - {None}
        if executors:
            modules[relative] = sorted(str(test) for test in executors)
    return {"default_branch_commit": commit, "modules": modules}


def _render(*, recorded: dict[str, Any]) -> str:
    """The map as JSON with one module per line, so a regeneration diffs per module."""
    rows = ",\n".join(
        f"    {json.dumps(module)}: {json.dumps(tests)}"
        for module, tests in recorded["modules"].items()
    )
    commit = json.dumps(recorded["default_branch_commit"])
    return f'{{\n  "default_branch_commit": {commit},\n  "modules": {{\n{rows}\n  }}\n}}\n'


def main() -> int:
    """Write the map for the coverage data named by argv[1] to the path named by argv[2]."""
    data_file, output = Path(sys.argv[1]), Path(sys.argv[2])
    commit = subprocess.run(
        ["git", "merge-base", "HEAD", _DEFAULT_BRANCH_REF],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    recorded = build_map(data_file=data_file, root=Path.cwd(), commit=commit)
    output.parent.mkdir(parents=True, exist_ok=True)
    _ = output.write_text(_render(recorded=recorded), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
