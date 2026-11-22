"""The reattach module is on no module-level import cycle, so it imports first."""

from __future__ import annotations

import ast
from pathlib import Path

import livespec_orchestrator_beads_fabro.commands as commands_package

_COMMANDS = "livespec_orchestrator_beads_fabro.commands"
_REATTACH = "_dispatcher_fabro_reattach"
_POST_RUN_TERMINAL = "_dispatcher_post_run_terminal"


def _module_level_imports(*, path: Path, known: frozenset[str]) -> frozenset[str]:
    """Name the sibling command modules a module imports when it is first loaded.

    Only the statements directly in the module body count: an import inside a
    function body or an `if TYPE_CHECKING:` block does not run at import time.
    """
    imported: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
        else:
            continue
        for name in names:
            sibling = name.removeprefix(f"{_COMMANDS}.")
            if name.startswith(f"{_COMMANDS}.") and sibling in known:
                imported.add(sibling)
    return frozenset(imported)


def _import_graph() -> dict[str, frozenset[str]]:
    directory = Path(commands_package.__file__).parent
    known = frozenset(path.stem for path in directory.glob("*.py"))
    return {
        path.stem: _module_level_imports(path=path, known=known) for path in directory.glob("*.py")
    }


def _reaches(*, graph: dict[str, frozenset[str]], start: str, goal: str) -> bool:
    seen: set[str] = set()
    pending = [start]
    while pending:
        module = pending.pop()
        if module in seen:
            continue
        seen.add(module)
        if module == goal:
            return True
        pending.extend(graph.get(module, ()))
    return False


def test_the_reattach_module_reaches_itself_through_no_module_level_import() -> None:
    """A test that imports the reattach module first must not meet it half-loaded."""
    graph = _import_graph()
    cycle_back = [
        dependency
        for dependency in graph[_REATTACH]
        if _reaches(graph=graph, start=dependency, goal=_REATTACH)
    ]
    assert cycle_back == []


def test_the_post_run_terminal_module_reaches_itself_through_no_module_level_import() -> None:
    """The engine side of the former cycle is on no import cycle either."""
    graph = _import_graph()
    cycle_back = [
        dependency
        for dependency in graph[_POST_RUN_TERMINAL]
        if _reaches(graph=graph, start=dependency, goal=_POST_RUN_TERMINAL)
    ]
    assert cycle_back == []
