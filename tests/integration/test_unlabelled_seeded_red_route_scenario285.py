"""Scenario 285 — an unlabelled Red on a carried seed does not enter commit_red.

The Red prompt asks a turn that finds an already-complete seed to declare
``already-satisfied``.  A turn can still end without that directive.  When its
latest handoff section names no Red test and the tree differs from the dispatch
base, the graph must classify that ordinary fallthrough before ``commit_red``:
there is no test for the command node to commit, while the carried seed must
continue through Green.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)

_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW = _ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_ROUTE = "red_seeded_fallthrough_route"
_DEFAULT_BRANCH_TEMPLATE = re.compile(r"\{\{\s*inputs\.default_branch\s*\}\}")


def _graph() -> DotGraph:
    graph = parse_dot_graph(text=_WORKFLOW.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph


def _environment() -> dict[str, str]:
    """Keep the throwaway repository independent of an outer commit hook."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COV_CORE", "COVERAGE"))
    }
    environment["GIT_CONFIG_GLOBAL"] = "/dev/null"
    environment["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return environment


def _git(repo: Path, *argv: str) -> str:
    completed = subprocess.run(
        ("git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *argv),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_environment(),
    )
    return completed.stdout.strip()


def _destination(*, graph: DotGraph, source: str, preferred_label: str | None) -> str:
    outgoing = [edge for edge in graph.edges if edge.source == source]
    matching = [
        edge.destination
        for edge in outgoing
        if edge.attributes.get("condition") == f"preferred_label={preferred_label}"
    ]
    fallback = [edge.destination for edge in outgoing if "condition" not in edge.attributes]
    assert len(matching) <= 1, (source, matching)
    assert len(fallback) == 1, (source, fallback)
    return matching[0] if matching else fallback[0]


def test_unlabelled_red_with_a_carried_seed_and_no_red_test_reaches_green_admission(
    tmp_path: Path,
) -> None:
    """A missing preferred label cannot send an already-complete carried seed to commit_red."""
    graph = _graph()

    assert _ROUTE in graph.nodes
    assert _destination(graph=graph, source="red", preferred_label=None) == _ROUTE

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _git(checkout, "init", "--quiet", "-b", "master")
    (checkout / "product.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "--quiet", "-m", "dispatch base")
    _git(checkout, "update-ref", "refs/remotes/origin/master", "HEAD")

    (checkout / "product.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(checkout, "add", ".")
    _git(checkout, "commit", "--quiet", "-m", "carried implementation")
    _git(checkout, "commit", "--quiet", "--allow-empty", "-m", "fabro(run): red (success)")
    handoff = checkout / ".git" / "livespec-implement-handoff.md"
    handoff.write_text("## red\n\nNo Red test was written.\n", encoding="utf-8")

    script = _DEFAULT_BRANCH_TEMPLATE.sub("master", graph.nodes[_ROUTE]["script"])
    completed = subprocess.run(
        ("sh", "-c", script),
        cwd=checkout,
        check=False,
        capture_output=True,
        text=True,
        env=_environment(),
    )

    assert completed.returncode == 0, completed.stderr
    emitted = cast(dict[str, str], json.loads(completed.stdout))
    assert emitted == {"preferred_next_label": "seeded"}
    assert _destination(
        graph=graph, source=_ROUTE, preferred_label=emitted["preferred_next_label"]
    ) == ("green_admission")
