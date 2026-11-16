"""Scenario 285 — a red already-satisfied declaration on a seeded tree re-enters Red.

`SPECIFICATION/contracts.md`, paragraph "A seeded run enters the implement stage
from its seed", bullet "Carried work that already meets the Definition of Done is
published": a seeded run's `red` turn MUST NOT declare the already-satisfied
outcome, the run MUST take the carried changes through `commit_red`, `green` and
`commit_green` to publication, and it MUST NOT end "at the already-satisfied
ending ... nor at any variant of that ending that reports the outcome
unprovable". Scenario 285's "A seed whose carried changes already meet the
Definition of Done is published" states the same.

Measured on the v0.333.1 re-canary (livespec-dev-tooling-eqtyyr, petri run
01M7GVZD6AEJWV05A4YK7DFVDV, 2026-11-16): the seed `preserve/run-01M7EE9HKDPQ`
carried a complete Red-Green pair above the dispatch base, the red turn declared
already-satisfied against its own prompt, the `red -> already_satisfied` edge
fired, and the terminal ended the run `LIVESPEC_ALREADY_SATISFIED_UNPROVABLE` —
the ending the clause forbids. The graph had no conformant recovery for a red
turn that broke the rule.

The committed graph now routes the already-satisfied label through
`already_satisfied_route`, a routing-schema command node. An unchanged tree
routes `unchanged` to the `already_satisfied` terminal exactly as before; a tree
that differs routes `carried`, refuses the declaration into the handoff file
naming the carried paths and the seeded-run rule, and re-enters `red` through
`red_admission`, so the run reaches commit and publish through the Red-Green pair
rather than entering the terminal. A base the node cannot compare against fails
closed with no directive.

Every behavioural case EXECUTES the shipped node bytes (taken through
`parse_dot_graph`, never retyped) under `sh` in a real throwaway repository
whose shape is the measured one: a dispatch base, an authored Red-Green pair
above it, and an engine checkpoint commit on top. Two controls carry the module.
The unchanged-tree case is what makes the carried case evidence of the route and
not of a node that re-enters red on every visit, and it composes onward into the
terminal's own script so the Dispatcher's ending is shown still reachable. And
the terminal's own bytes are run against the seeded checkout, which still
reports the unprovable ending: that is what the route now stands in front of.
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

_REPO_ROOT = Path(__file__).resolve().parents[2]
_IMPLEMENT = _REPO_ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_DEFAULT_BRANCH_TEMPLATE = re.compile(r"\{\{\s*inputs\.default_branch\s*\}\}")
_ROUTE = "already_satisfied_route"
_TERMINAL = "already_satisfied"
_CHECKPOINT_RUN = "01M7EE9HKDPQHQ97WQ2FB52B1S"

# The shape of the eqtyyr red@49 ending as the engine records a final message
# with no schema: prose, then the directive as the last JSON object.
_SEEDED_RED_DECLARATION = "".join(
    (
        "The preserved tree already carries the fix and its test; both pass on the ",
        "working tree, so no failing test can be written.",
        '{"preferred_next_label":"already-satisfied"}',
    )
)


def _graph() -> DotGraph:
    graph = parse_dot_graph(text=_IMPLEMENT.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    return graph


def _clean_environment() -> dict[str, str]:
    """The child environment without GIT_ or coverage variables from an outer commit hook."""
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COV_CORE", "COVERAGE"))
    }
    environment["GIT_CONFIG_GLOBAL"] = "/dev/null"
    environment["GIT_CONFIG_SYSTEM"] = "/dev/null"
    return environment


def _git(*, repo: Path, argv: tuple[str, ...]) -> str:
    result = subprocess.run(
        ("git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", *argv),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env=_clean_environment(),
    )
    return result.stdout.strip()


def _base_repository(*, tmp_path: Path) -> Path:
    """A clone at its dispatch base: one product file, one test file, `origin/master` at HEAD."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _ = _git(repo=checkout, argv=("init", "--quiet", "-b", "master"))
    (checkout / "tests").mkdir()
    _ = (checkout / "pkg.py").write_text("def answer():\n    return 41\n", encoding="utf-8")
    _ = (checkout / "tests" / "test_pkg.py").write_text(
        "def test_nothing():\n    pass\n", encoding="utf-8"
    )
    _ = _git(repo=checkout, argv=("add", "."))
    _ = _git(repo=checkout, argv=("commit", "--quiet", "-m", "base"))
    _ = _git(repo=checkout, argv=("update-ref", "refs/remotes/origin/master", "HEAD"))
    return checkout


def _seed_carried_changes(*, checkout: Path) -> None:
    """The measured seed: a complete Red-Green pair above the base, then an engine checkpoint."""
    _ = (checkout / "pkg.py").write_text("def answer():\n    return 42\n", encoding="utf-8")
    _ = (checkout / "tests" / "test_pkg.py").write_text(
        "from pkg import answer\n\n\ndef test_answer():\n    assert answer() == 42\n",
        encoding="utf-8",
    )
    _ = _git(repo=checkout, argv=("add", "."))
    message = (
        "fix: answer is 42\n\nTDD-Red-Test: tests/test_pkg.py\n"
        "TDD-Green-Verified-At: 2026-11-15T02:52:28Z"
    )
    _ = _git(repo=checkout, argv=("commit", "--quiet", "-m", message))
    checkpoint = f"fabro({_CHECKPOINT_RUN}): red (success)"
    _ = _git(repo=checkout, argv=("commit", "--quiet", "--allow-empty", "-m", checkpoint))


def _run_node(*, node: str, checkout: Path) -> subprocess.CompletedProcess[str]:
    script = _DEFAULT_BRANCH_TEMPLATE.sub("master", _graph().nodes[node]["script"])
    return subprocess.run(
        ("sh", "-c", script),
        cwd=checkout,
        check=False,
        capture_output=True,
        text=True,
        input="",
        env=_clean_environment(),
    )


def _directive_labels(*, stdout: str) -> list[str]:
    """Every `preferred_next_label` the node printed as a JSON object line, in order."""
    labels: list[str] = []
    for line in stdout.splitlines():
        if not line.startswith("{"):
            continue
        payload = cast("dict[str, object]", json.loads(line))
        label = payload.get("preferred_next_label")
        assert isinstance(label, str), payload
        labels.append(label)
    return labels


def _destination(*, source: str, preferred_label: str | None) -> str:
    """Resolve a label as the engine does: its conditional edge if one exists, else the fallthrough."""
    outgoing = [edge for edge in _graph().edges if edge.source == source]
    matching = [
        edge.destination
        for edge in outgoing
        if edge.attributes.get("condition") == f"preferred_label={preferred_label}"
    ]
    fallthrough = [edge.destination for edge in outgoing if "condition" not in edge.attributes]
    assert len(matching) <= 1, (source, matching)
    assert len(fallthrough) == 1, (source, fallthrough)
    return matching[0] if matching else fallthrough[0]


def _last_directive_label(text: str) -> str:
    found = cast("dict[str, object]", json.loads(text[text.rindex("{") :]))
    label = found["preferred_next_label"]
    assert isinstance(label, str), found
    return label


def test_the_already_satisfied_label_leaves_red_for_the_route_not_the_terminal() -> None:
    """The committed graph puts the route between red and the terminal, as a routing-schema node."""
    graph = _graph()
    assert _ROUTE in graph.nodes
    assert graph.nodes[_ROUTE].get("output_schema") == "routing"

    assert _destination(source="red", preferred_label="already-satisfied") == _ROUTE
    assert _last_directive_label(_SEEDED_RED_DECLARATION) == "already-satisfied"

    by_condition = {
        edge.attributes.get("condition", ""): edge.destination
        for edge in graph.edges
        if edge.source == _ROUTE
    }
    # Exactly the two routes: carried changes re-enter Red through its admission
    # bound, and everything else — the unchanged tree — falls through to the
    # terminal. No `outcome=failed` edge: an incomparable base fails the run closed.
    assert by_condition == {"preferred_label=carried": "red_admission", "": _TERMINAL}
    # The terminal is reached only through the route now.
    assert [edge.source for edge in graph.edges if edge.destination == _TERMINAL] == [_ROUTE]


def test_an_unchanged_tree_routes_to_the_terminal_whose_ending_the_dispatcher_reads(
    tmp_path: Path,
) -> None:
    """Tree == base: `unchanged`, the terminal, and the terminal's own sentinel still print."""
    checkout = _base_repository(tmp_path=tmp_path)
    base = _git(repo=checkout, argv=("rev-parse", "HEAD"))

    result = _run_node(node=_ROUTE, checkout=checkout)

    assert result.returncode == 0, result.stderr
    assert _directive_labels(stdout=result.stdout) == ["unchanged"]
    assert "LIVESPEC_ALREADY_SATISFIED_UNCHANGED" in result.stderr
    assert _destination(source=_ROUTE, preferred_label="unchanged") == _TERMINAL
    assert not (checkout / ".git" / "livespec-implement-handoff.md").exists()

    terminal = _run_node(node=_TERMINAL, checkout=checkout)
    assert terminal.returncode == 0, terminal.stderr
    assert f"LIVESPEC_ALREADY_SATISFIED: base={base}" in terminal.stderr


def test_a_seeded_tree_is_refused_into_the_handoff_and_re_enters_red(tmp_path: Path) -> None:
    """Tree != base: `carried`, a refusal section naming the carried paths, and red_admission."""
    checkout = _base_repository(tmp_path=tmp_path)
    base = _git(repo=checkout, argv=("rev-parse", "HEAD"))
    _seed_carried_changes(checkout=checkout)
    assert _git(repo=checkout, argv=("rev-parse", "HEAD")) != base

    result = _run_node(node=_ROUTE, checkout=checkout)

    assert result.returncode == 0, result.stderr
    assert _directive_labels(stdout=result.stdout) == ["carried"]
    assert _destination(source=_ROUTE, preferred_label="carried") == "red_admission"
    assert "LIVESPEC_ALREADY_SATISFIED_CARRIED_CHANGES" in result.stderr
    assert "LIVESPEC_ALREADY_SATISFIED_UNPROVABLE" not in result.stderr
    handoff = (checkout / ".git" / "livespec-implement-handoff.md").read_text(encoding="utf-8")
    assert "## already-satisfied-refused" in handoff
    assert base in handoff
    assert "pkg.py" in handoff
    assert "tests/test_pkg.py" in handoff
    assert "write the Red test" in handoff
    assert "re-entering red" in handoff

    # The control: the terminal's own bytes on this checkout still report the
    # unprovable ending the clause forbids, which is exactly what the route now
    # stands in front of.
    terminal = _run_node(node=_TERMINAL, checkout=checkout)
    assert terminal.returncode == 1
    assert "LIVESPEC_ALREADY_SATISFIED_UNPROVABLE" in terminal.stderr


def test_a_second_refusal_appends_to_the_handoff_rather_than_rewriting_it(
    tmp_path: Path,
) -> None:
    """The handoff is append-only: an earlier section survives a later refusal."""
    checkout = _base_repository(tmp_path=tmp_path)
    _seed_carried_changes(checkout=checkout)
    handoff_path = checkout / ".git" / "livespec-implement-handoff.md"
    _ = handoff_path.write_text("## red\n\nRed test file: tests/test_pkg.py\n", encoding="utf-8")

    first = _run_node(node=_ROUTE, checkout=checkout)
    second = _run_node(node=_ROUTE, checkout=checkout)

    assert (first.returncode, second.returncode) == (0, 0), (first.stderr, second.stderr)
    handoff = handoff_path.read_text(encoding="utf-8")
    assert handoff.startswith("## red\n\nRed test file: tests/test_pkg.py\n")
    assert handoff.count("## already-satisfied-refused") == 2


def test_a_base_the_node_cannot_compare_against_fails_closed_with_no_directive(
    tmp_path: Path,
) -> None:
    """No `origin/master`: a non-zero exit, no routing directive, and the cause on stderr."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    _ = _git(repo=checkout, argv=("init", "--quiet", "-b", "master"))
    _ = (checkout / "a.txt").write_text("base\n", encoding="utf-8")
    _ = _git(repo=checkout, argv=("add", "a.txt"))
    _ = _git(repo=checkout, argv=("commit", "--quiet", "-m", "base"))

    result = _run_node(node=_ROUTE, checkout=checkout)

    assert result.returncode != 0
    assert _directive_labels(stdout=result.stdout) == []
    assert "LIVESPEC_ALREADY_SATISFIED_BASE_UNREADABLE" in result.stderr
    assert not (checkout / ".git" / "livespec-implement-handoff.md").exists()
