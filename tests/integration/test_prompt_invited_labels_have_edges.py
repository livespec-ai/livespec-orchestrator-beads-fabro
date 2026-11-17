"""Every label a stage prompt invites has an edge, and the needs-human label rests the run.

The converse of the schema guard in
`test_agent_label_edges_route_under_the_engine_contract.py`: that file requires
every `preferred_label=` edge to leave a node whose contract can set the label;
this file requires every label a prompt tells its agent to emit to have an edge
that reads it, so no invited label falls through the unconditional edge.

Measured on the v0.333.0 canary, bd-ib-m5cpnl run 01M7GDVE6VKD (2026-11-15):
red@2 and red@3 ended with `{"preferred_next_label":"needs-human"}` (glued to a
prose line, Codex-shaped). The red node had no edge for that label, so each
request for a human fell through `red -> commit_red`, which refused a Red with
no test file, and the stage spent its bound re-entering red. The red and green
prompts now name that label and the graph routes it to a command node that
writes the turn's final message as the needs-human cause and rests the run.

bd-ib-eqtyyr run 01M7GE2A69NN, red@2, ended with `publish_draft`, a label no
prompt invites. A catch-all edge on each of red and green now sends every label
the node does not route to a command node that logs it, appends a refusal
section to the handoff and re-enters the stage, or, on green, grades a turn that
stated its completion field.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import cast

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import (
    DotGraph,
    parse_dot_graph,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKFLOW_ROOTS = (
    _REPO_ROOT / ".claude-plugin" / ".fabro" / "workflows",
    _REPO_ROOT / ".fabro" / "workflows",
)
_IMPLEMENT = _REPO_ROOT / ".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"
_INVITED_LABEL = re.compile(r'"preferred_next_label":\s*"([A-Za-z0-9_-]+)"')

# `output.text` of the recorded m5cpnl red@2 step.finished outcome, byte for byte.
_M5CPNL_RED_2_TEXT = "".join(
    (
        "I\u2019ll first audit the preserved attempt against the current checkout and run its ",
        "focused tests. Then I\u2019ll complete any gaps, keeping `.github/workflows/` untouched, ",
        "and publish the requested branch if the repository\u2019s checks pass.The preserved ",
        "attempt contains only a test that asserts a new shim trigger; it made no ",
        "implementation change. The governing contract confirms the actual fix requires ",
        "changes to both reusable workflow behavior and the shim trigger, which this factory ",
        "branch is explicitly prohibited from editing. I\u2019m running the focused checks to ",
        "record the incomplete state, then I\u2019ll preserve only a valid, non-workflow ",
        "contribution if one exists; otherwise I\u2019ll hand this off cleanly to the attended ",
        "workflow-edit route rather than publishing a misleading partial fix.",
        '{"definition_of_done_complete":false,"preferred_next_label":"needs-human"}',
    )
)


def _graph(path: Path) -> DotGraph:
    graph = parse_dot_graph(text=path.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), (path, graph)
    return graph


def _dispatched_graphs() -> list[tuple[Path, DotGraph]]:
    """Every committed graph the Dispatcher can dispatch.

    `workflow.pre-petri.fabro` is the retired pre-petri engine's graph, kept
    for its history; no Dispatcher path resolves it, and its review and
    proof_verify nodes already lack the `recapture` edge their prompts invite.
    """
    return [
        (path, _graph(path))
        for root in _WORKFLOW_ROOTS
        for path in sorted(root.rglob("workflow.fabro"))
    ]


def _invited_labels(*, graph_path: Path, graph: DotGraph, node: str) -> set[str]:
    prompt = graph.nodes[node].get("prompt", "")
    if not prompt.startswith("@"):
        return set()
    text = (graph_path.parent / prompt[1:]).read_text(encoding="utf-8")
    return set(_INVITED_LABEL.findall(text))


def _routed_labels(*, graph: DotGraph, node: str) -> set[str]:
    routed: set[str] = set()
    for edge in graph.edges:
        condition = edge.attributes.get("condition") or ""
        if edge.source == node and condition.startswith("preferred_label="):
            routed.add(condition.removeprefix("preferred_label=").split(" ")[0])
    return routed


def _last_directive_label(text: str) -> str:
    """The engine's reading of a final message with no schema: the last object's label.

    Every recorded canary message ends with its directive as the last JSON object,
    so the last `{` opens it; the full object scan lives in the sibling module.
    """
    found = cast("dict[str, object]", json.loads(text[text.rindex("{") :]))
    label = found["preferred_next_label"]
    assert isinstance(label, str), found
    return label


# The last 700 characters of the recorded eqtyyr red@2 `output.text` (run
# 01M7GE2A69NN): a label no prompt invites and no edge carried.
_EQTYYR_RED_2_TAIL = "".join(
    (
        "eiling described in the repo guidance; the detached gate design is preserving the run ",
        "safely. No refusal has been recorded.The coverage pytest workers have completed; the ",
        "aggregate is now finishing its report and remaining check targets. I\u2019m still waiting ",
        "for the authoritative push-gate result.The push gate passed: 89 targets completed with ",
        "zero failures, and the exact branch ref is published. I\u2019m creating the pull request ",
        "now.The branch is published and gated green. This sandbox\u2019s publication policy ",
        "refused `gh pr create` at the implement stage, so PR creation is correctly deferred to ",
        "its dedicated publication stage.",
        '{"definition_of_done_complete":true,"preferred_next_label":"publish_draft"}',
    )
)


def _run_route(
    *, graph: DotGraph, route: str, stdin: str, tmp_path: Path
) -> tuple[subprocess.CompletedProcess[str], Path]:
    checkout = tmp_path / route
    _ = subprocess.run(("git", "init", "--quiet", str(checkout)), check=True)
    result = subprocess.run(
        ("sh", "-c", graph.nodes[route]["script"]),
        check=False,
        cwd=checkout,
        input=stdin,
        capture_output=True,
        text=True,
    )
    return result, checkout


def test_every_label_a_prompt_invites_has_an_edge_that_reads_it() -> None:
    """In every dispatched graph, each `preferred_next_label` a node's prompt names leaves the node."""
    unrouted: list[tuple[str, str, str]] = []
    for graph_path, graph in _dispatched_graphs():
        for node in graph.nodes:
            invited = _invited_labels(graph_path=graph_path, graph=graph, node=node)
            routed = _routed_labels(graph=graph, node=node)
            unrouted.extend(
                (graph_path.relative_to(_REPO_ROOT).as_posix(), node, label)
                for label in sorted(invited - routed)
            )

    assert unrouted == []


def test_the_guard_has_subjects() -> None:
    """The red, green and review nodes of the implement graph each invite at least one label."""
    graph = _graph(_IMPLEMENT)
    for node in ("red", "green", "review"):
        assert _invited_labels(graph_path=_IMPLEMENT, graph=graph, node=node), node


@pytest.mark.parametrize(
    ("node", "route", "stage_text", "code"),
    [
        ("red", "red_needs_human_route", _M5CPNL_RED_2_TEXT, "LIVESPEC_RED_NEEDS_HUMAN_LABEL"),
        (
            "green",
            "green_needs_human_route",
            'The fix needs a workflow edit.{"preferred_next_label":"needs-human"}',
            "LIVESPEC_GREEN_NEEDS_HUMAN_LABEL",
        ),
    ],
)
def test_the_needs_human_label_rests_the_run_with_the_turns_message(
    node: str, route: str, stage_text: str, code: str, tmp_path: Path
) -> None:
    """A needs-human label routes to a node that writes the final message as the cause and fails."""
    graph = _graph(_IMPLEMENT)
    label = _last_directive_label(stage_text)
    assert label == "needs-human"
    matching = [
        edge.destination
        for edge in graph.edges
        if edge.source == node and edge.attributes.get("condition") == f"preferred_label={label}"
    ]
    assert matching == [route]
    assert graph.nodes[route]["stdin_source"] == f"context.response.{node}"
    failed = [
        edge.destination
        for edge in graph.edges
        if edge.source == route and edge.attributes.get("condition") == "outcome=failed"
    ]
    assert failed == ["needs_human"]

    result, checkout = _run_route(graph=graph, route=route, stdin=stage_text, tmp_path=tmp_path)

    assert result.returncode == 1, result.stderr
    assert code in result.stderr
    cause = (checkout / ".git" / "livespec-stage-cause").read_text(encoding="utf-8")
    assert cause.startswith("stage: implement\ncause: " + code)
    assert "prohibited from editing" in cause or "workflow edit" in cause


def test_an_unknown_red_label_is_refused_into_the_handoff_and_re_enters_red_without_spending_admission(
    tmp_path: Path,
) -> None:
    """The refusal returns directly to bounded Red without spending admission."""
    graph = _graph(_IMPLEMENT)
    assert graph.nodes["red"].get("max_visits") == "4"
    routes = [
        (edge.destination, edge.attributes.get("condition", ""))
        for edge in graph.edges
        if edge.source == "red_unknown_label_route"
    ]
    assert routes == [("red", "outcome=failed"), ("red", "")]

    result, checkout = _run_route(
        graph=graph, route="red_unknown_label_route", stdin=_EQTYYR_RED_2_TAIL, tmp_path=tmp_path
    )

    assert result.returncode == 1, result.stderr
    assert (
        "LIVESPEC_RED_UNKNOWN_LABEL: the red turn ended with preferred_next_label 'publish_draft'"
        in result.stderr
    )
    handoff = (checkout / ".git" / "livespec-implement-handoff.md").read_text(encoding="utf-8")
    assert "## red-label-refused" in handoff
    assert "'publish_draft'" in handoff
    assert "seeded-open-red, seeded-red-passes, already-satisfied and needs-human" in handoff


def test_an_unknown_green_label_grades_a_stated_completion_and_refuses_the_rest(
    tmp_path: Path,
) -> None:
    """A stated completion field is graded despite the noise label; no field means a refused lap."""
    graph = _graph(_IMPLEMENT)
    by_condition = {
        edge.attributes.get("condition", ""): edge.destination
        for edge in graph.edges
        if edge.source == "green_unknown_label_route"
    }
    assert by_condition == {"outcome=failed": "green_admission", "": "implement_completion"}

    graded, _ = _run_route(
        graph=graph,
        route="green_unknown_label_route",
        stdin='Done.{"definition_of_done_complete":true,"preferred_next_label":"complete"}',
        tmp_path=tmp_path / "graded",
    )
    assert graded.returncode == 0, graded.stderr
    assert "LIVESPEC_GREEN_UNKNOWN_LABEL_GRADED" in graded.stderr
    assert "'complete'" in graded.stderr

    refused, checkout = _run_route(
        graph=graph,
        route="green_unknown_label_route",
        stdin='Pushed the branch.{"preferred_next_label":"publish_draft"}',
        tmp_path=tmp_path / "refused",
    )
    assert refused.returncode == 1, refused.stderr
    assert (
        "LIVESPEC_GREEN_UNKNOWN_LABEL: the green turn ended with preferred_next_label 'publish_draft'"
        in refused.stderr
    )
    handoff = (checkout / ".git" / "livespec-implement-handoff.md").read_text(encoding="utf-8")
    assert "## green-label-refused" in handoff
