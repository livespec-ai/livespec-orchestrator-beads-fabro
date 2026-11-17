"""Every `preferred_label=` edge leaving an agent node is live under the engine's output contract.

The petri engine (thewoolleyman/petri `ac0b9fb`, the revision Fabro `d22808f` /
0.408.0 serves on gmktec) reads an agent node's final message through the
contract its `output_schema` declares (`crates/attractor/steps/src/contract.rs`):

- no `output_schema`: the LAST JSON object carrying a routing field
  (`preferred_next_label`, `outcome`, `failure_reason`, `suggested_next_ids`,
  `context_updates`) is a directive, and `Directive::apply_to` writes its label
  to `output.preferred_label` and its outcome onto the stage;
- `output_schema="routing"`: the same directive, and a message without one is
  a contract miss;
- `output_schema=<JSON Schema>`: the last JSON object is validated against the
  schema and stored ONLY as `output.structured` and
  `context_updates["output.<node>"]` (`agent.rs`, the `Parsed::Structured`
  arm). Nothing writes `output.preferred_label`, and the directive's `outcome`
  is never applied.

An edge condition `preferred_label=X` lowers to `output.preferred_label`
(`crates/attractor/frontend/src/condition.rs`). So an agent node that declares a
JSON-Schema `output_schema` can never take a `preferred_label=` edge, whatever
its final message says, and its `{"outcome": "failed", ...}` ending is read as a
success. Measured on the v0.333.0 canary, bd-ib-st4obs run
01M7GDPBANKE14DXX4HE4TVZVD (2026-11-15): every red@1..3 turn ended with
`{"preferred_next_label":"seeded-open-red"}` (parsed, recorded under
`output.structured`), the routing trace was empty, and the run took the
unconditional `red -> commit_red` edge three times into `commit_red: latest red
section names no test file` and a `RoutingBlocked` end.

Two more shapes from the same canary. bd-ib-m5cpnl run 01M7GDVE6VKD: red@2 and
red@3 ended with `{"preferred_next_label":"needs-human"}`, a label no red edge
carried, so each request for a human fell through to `commit_red`. bd-ib-eqtyyr
run 01M7GE2A69NN: red@2 ended with `{"preferred_next_label":"publish_draft"}`,
a label no prompt invites and no edge carries, and fell through the same way.
So the red and green nodes now route `needs-human` to a node that rests the run
with the turn's message as the question, and route EVERY OTHER label through a
catch-all edge (`preferred_label && preferred_label != <each routed label>`) to
a node that logs and refuses it; the unconditional edge is reached only by a
turn that set no label at all.

These cases carry the recorded engine outcomes as fixtures, port the contract
rules so a final message yields the same `output` the engine recorded, and
require every routed label in every committed graph to leave a node whose
contract can set it. The three recorded st4obs red messages — two Codex-shaped,
with the skills-budget warning and the label glued to the end of a prose line —
must route to `green_admission` through the committed red node.
"""

from __future__ import annotations

import json
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
_PROMPTS = _IMPLEMENT.parent / "prompts"

_ROUTING_FIELDS = (
    "preferred_next_label",
    "outcome",
    "failure_reason",
    "suggested_next_ids",
    "context_updates",
)

# The red node's `output_schema` as the canary run's registered graph carried it
# (workflow.fabro:396 at v0.333.0), kept here because the committed graph must
# no longer declare it.
_V0_333_0_RED_SCHEMA = "".join(
    (
        '{"type":"object","properties":{"definition_of_done_complete":{"type":"boolean"},',
        '"preferred_next_label":{"type":"string"}}}',
    )
)

# `output.text` of the three recorded red step.finished outcomes, byte for byte.
_ST4OBS_RED_TEXTS = (
    "".join(
        (
            "I\u2019ll first audit the preserved attempt at `3dc580\u2026`, including its diff and ",
            "focused checks, then I\u2019ll add exactly one failing acceptance test without touching ",
            "product code.The preserved tree contains an open Red commit (`99368c\u2026`) with a ",
            "61-line test addition but no Green trailer. Its focused test run has three genuine ",
            "assertion failures in the new preserved-run identifier cases, so I\u2019ll preserve that ",
            'Red/Green pair for the Green stage rather than add another test.{"preferred_next_label":',
            '"seeded-open-red"}',
        )
    ),
    "".join(
        (
            "Warning: Skill descriptions were shortened to fit the skills context budget. Codex can ",
            "still see every skill, but some descriptions are shorter. Disable unused skills or ",
            "plugins to leave more room for the rest.\n\nI\u2019ll first audit the preserved commit and ",
            "its test state, then add only the single failing Red test required by this stage.The ",
            "preserved tree contains an existing open Red at `99368c555`: it names the ",
            "publication-record test but has no Green verification trailer. I\u2019ll preserve that ",
            "pairing for Green rather than create another Red; I\u2019m running the repository gate on ",
            'the carried implementation now.{"definition_of_done_complete":false,',
            '"preferred_next_label":"seeded-open-red"}',
        )
    ),
    "".join(
        (
            "Warning: Skill descriptions were shortened to fit the skills context budget. Codex can ",
            "still see every skill, but some descriptions are shorter. Disable unused skills or ",
            "plugins to leave more room for the rest.\n\nI\u2019m inspecting the preserved seed and the ",
            "red-stage state first, then I\u2019ll either reuse its open Red or produce one focused ",
            "failing acceptance test.The preserved work already has an open Red commit: ",
            "`99368c\u2026` carries a Red checksum but no Green verification. Per the factory flow, ",
            "I\u2019m preserving that exact Red/Green pair and routing directly to Green rather than ",
            'creating a duplicate test.{"preferred_next_label":"seeded-open-red"}',
        )
    ),
)

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

# The last 700 characters of `output.text` of the recorded eqtyyr red@2 outcome
# (4,155 characters in all), byte for byte: the turn ran a push gate inside Red
# and asked for a node by name.
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

# The recorded `output` of red@1 (keys and routing-relevant values).
_ST4OBS_RED_1_OUTPUT_KEYS = {"failure_class", "outcome", "structured", "text", "turns"}
_ST4OBS_RED_1_STRUCTURED = {"preferred_next_label": "seeded-open-red"}

# The tail of `output.text` of a recorded `review` step.finished outcome on the
# same engine (run 01M7G9CGB2YA, hetzner-xubuntu-info hxi-mhzvbk, 2026-11-15);
# `review` declares no output_schema. Its recorded output keys follow.
_REVIEW_TEXT_TAIL = "".join(
    (
        "] provisioning/ansible/roles/hxi_fleet_ssh_client/files/hxi-fleet-host-key-guard ",
        "\u2014 when a differing entry is planted, the connection fails via a non-zero ",
        '`KnownHostsCommand` exit rather than ssh\'s literal "Host key verification failed" ',
        "path; the host-leg replayer should confirm that satisfies host-captured assertion 1's ",
        '"fails host-key verification" wording.\n\nNo blocking findings.\n\n',
        '{"preferred_next_label": "approve"}',
    )
)
_REVIEW_OUTPUT_KEYS = {"failure_class", "outcome", "preferred_label", "text", "turns"}


def _graph(path: Path) -> DotGraph:
    graph = parse_dot_graph(text=path.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), (path, graph)
    return graph


def _every_graph() -> list[tuple[str, DotGraph]]:
    found: list[tuple[str, DotGraph]] = []
    for root in _WORKFLOW_ROOTS:
        found.extend(
            (path.relative_to(_REPO_ROOT).as_posix(), _graph(path))
            for path in sorted(root.rglob("*.fabro"))
        )
    return found


# --- the engine's output contract, ported --------------------------------------


def _json_objects(text: str) -> list[str]:
    """Every outermost JSON object in `text`, as `directive.rs::json_objects` finds them.

    An opening brace that never closes costs only itself: the scan resumes one
    byte past it, so a trailing routing object after stray prose braces is found.
    """
    out: list[str] = []
    start_from = 0
    while True:
        unclosed = _scan_objects(text, start_from, out)
        if unclosed is None:
            return out
        start_from = unclosed + 1


def _string_state(char: str, *, escaped: bool) -> tuple[bool, bool]:
    """(still inside the string, next char is escaped) after `char` inside a JSON string."""
    if escaped:
        return True, False
    if char == "\\":
        return True, True
    return char != '"', False


def _scan_objects(text: str, start_from: int, out: list[str]) -> int | None:
    depth = 0
    start: int | None = None
    in_string = False
    escaped = False
    for index in range(start_from, len(text)):
        char = text[index]
        if in_string:
            in_string, escaped = _string_state(char, escaped=escaped)
            continue
        if char == '"' and depth > 0:
            in_string = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                out.append(text[start : index + 1])
                start = None
    return start


def _strip_accelerator(label: str) -> str:
    trimmed = label.strip()
    if trimmed.startswith("[") and "]" in trimmed:
        return trimmed[trimmed.index("]") + 1 :].lstrip()
    if len(trimmed) >= 2 and trimmed[1] == ")":
        return trimmed[2:].lstrip()
    if len(trimmed) >= 3 and trimmed[1:].startswith(" - "):
        return trimmed[4:]
    return trimmed


def _directive(text: str) -> dict[str, object] | None:
    """The last JSON object carrying a routing field, or None (`directive.rs::parse`)."""
    last: dict[str, object] | None = None
    for candidate in _json_objects(text):
        try:
            found = cast("dict[str, object]", json.loads(candidate))
        except json.JSONDecodeError:
            continue
        if any(field in found for field in _ROUTING_FIELDS):
            last = found
    return last


def _schema_accepts(schema: dict[str, object], present: dict[str, object]) -> bool:
    """Enough of JSON Schema for the schemas this repository's graphs ever declared.

    Every candidate is a parsed `{...}` slice, so the object type always holds and
    only the typed optional properties remain to check.
    """
    properties = cast("dict[str, dict[str, object]]", schema.get("properties", {}))
    types: dict[str, type] = {"boolean": bool, "string": str}
    return all(
        name not in present or isinstance(present[name], types[str(spec["type"])])
        for name, spec in properties.items()
    )


def _engine_output(*, output_schema: str | None, text: str) -> dict[str, object]:
    """The `output` an agent step reports for `text` under its declared contract.

    Ports `contract.rs::validate` and the `agent.rs` arms that apply the result
    to a succeeded stage. A contract miss is reported as `{"contract_miss": ...}`
    because the engine then takes a repair turn, which no edge can route on.
    """
    output: dict[str, object] = {
        "text": text,
        "turns": 1,
        "outcome": "succeeded",
        "failure_class": "",
    }
    if output_schema is None or output_schema == "routing":
        directive = _directive(text)
        if directive is None:
            if output_schema == "routing":
                return {"contract_miss": "no JSON object in the response carries a routing field"}
            return output
        label = directive.get("preferred_next_label")
        if isinstance(label, str):
            output["preferred_label"] = _strip_accelerator(label)
        outcome = directive.get("outcome")
        if isinstance(outcome, str):
            output["outcome"] = outcome
            if outcome == "failed":
                output["failure_reason"] = directive.get("failure_reason")
        return output
    schema = cast("dict[str, object]", json.loads(output_schema))
    objects = _json_objects(text)
    if not objects:
        return {"contract_miss": "no JSON object in the response"}
    value = cast("dict[str, object]", json.loads(objects[-1]))
    if not _schema_accepts(schema, value):
        return {"contract_miss": "the last JSON object does not satisfy the schema"}
    output["structured"] = value
    return output


def _clause_holds(clause: str, output: dict[str, object]) -> bool:
    """One clause of Fabro's edge-condition grammar over the keys these graphs use.

    `preferred_label` reads `output.preferred_label`; `outcome` reads the reported
    outcome. A bare key is a truthiness test (`condition.rs`), `!=` is not-equal.
    """
    clause = clause.strip()
    if "!=" in clause:
        key, _, expected = clause.partition("!=")
        return _key_text(key.strip(), output) != expected.strip()
    if "=" in clause:
        key, _, expected = clause.partition("=")
        return _key_text(key.strip(), output) == expected.strip()
    return _key_text(clause, output) != ""


def _key_text(key: str, output: dict[str, object]) -> str:
    assert key in {"preferred_label", "outcome"}, key
    value = output.get(key)
    return value if isinstance(value, str) else ""


def _destination(*, graph: DotGraph, source: str, output: dict[str, object]) -> str:
    """The edge the engine takes: a matching conditional edge outranks the fallthrough."""
    matching: list[str] = []
    fallthrough: list[str] = []
    for edge in graph.edges:
        if edge.source != source:
            continue
        condition = edge.attributes.get("condition")
        if condition is None:
            fallthrough.append(edge.destination)
            continue
        if all(_clause_holds(clause, output) for clause in condition.split("&&")):
            matching.append(edge.destination)
    assert len(matching) <= 1, (source, output, matching)
    assert len(fallthrough) == 1, (source, fallthrough)
    return matching[0] if matching else fallthrough[0]


def _catch_all_exclusions(*, graph: DotGraph, source: str) -> tuple[str, set[str]]:
    """The destination of `source`'s catch-all label edge and the labels it excludes."""
    found = [
        edge
        for edge in graph.edges
        if edge.source == source
        and (edge.attributes.get("condition") or "").startswith("preferred_label &&")
    ]
    assert len(found) == 1, (source, found)
    clauses = [clause.strip() for clause in found[0].attributes["condition"].split("&&")]
    assert clauses[0] == "preferred_label", clauses
    excluded = {clause.removeprefix("preferred_label != ") for clause in clauses[1:]}
    assert all(clause.startswith("preferred_label != ") for clause in clauses[1:]), clauses
    return found[0].destination, excluded


def _agent_nodes_with_label_edges(graph: DotGraph) -> dict[str, str | None]:
    """Each agent node that some `preferred_label=` edge leaves, with its output_schema."""
    sources = {
        edge.source
        for edge in graph.edges
        if (edge.attributes.get("condition") or "").startswith("preferred_label=")
    }
    return {
        name: graph.nodes[name].get("output_schema")
        for name in sorted(sources)
        if "prompt" in graph.nodes[name]
    }


# --- the port reproduces the recorded engine outcomes ----------------------------


def test_the_port_reproduces_the_recorded_schema_contract_outcome() -> None:
    """Under the v0.333.0 red schema the engine recorded `structured` and no label."""
    output = _engine_output(output_schema=_V0_333_0_RED_SCHEMA, text=_ST4OBS_RED_TEXTS[0])

    assert set(output) == _ST4OBS_RED_1_OUTPUT_KEYS
    assert output["structured"] == _ST4OBS_RED_1_STRUCTURED
    assert "preferred_label" not in output


def test_the_port_reproduces_the_recorded_no_schema_review_outcome() -> None:
    """With no schema the engine recorded `preferred_label` and no `structured`."""
    output = _engine_output(output_schema=None, text=_REVIEW_TEXT_TAIL)

    assert set(output) == _REVIEW_OUTPUT_KEYS
    assert output["preferred_label"] == "approve"


@pytest.mark.parametrize(
    ("output_schema", "text", "expected"),
    [
        (
            "routing",
            "No object here.",
            {"contract_miss": "no JSON object in the response carries a routing field"},
        ),
        (
            _V0_333_0_RED_SCHEMA,
            "No object here.",
            {"contract_miss": "no JSON object in the response"},
        ),
        (
            _V0_333_0_RED_SCHEMA,
            '{"definition_of_done_complete":"yes"}',
            {"contract_miss": "the last JSON object does not satisfy the schema"},
        ),
    ],
)
def test_a_contract_miss_is_a_repair_turn_not_a_route(
    output_schema: str, text: str, expected: dict[str, str]
) -> None:
    """Each contract miss the engine repairs is reported as such, so no edge can read it."""
    assert _engine_output(output_schema=output_schema, text=text) == expected


@pytest.mark.parametrize(
    ("text", "label", "outcome"),
    [
        ('{"preferred_next_label": "[F] fix"}', "fix", "succeeded"),
        ('{"preferred_next_label": "a) approve"}', "approve", "succeeded"),
        ('{"preferred_next_label": "r - recapture"}', "recapture", "succeeded"),
        ('{"preferred_next_label": "approve", "outcome": "succeeded"}', "approve", "succeeded"),
        # A nested object, a quoted brace and an escaped quote inside the directive.
        (
            'x {"preferred_next_label": "fix", "context_updates": {"a": "}", "b": "\\"q"}}',
            "fix",
            "succeeded",
        ),
        # An unclosed prose brace before the directive costs only itself.
        ('see { the brace {"preferred_next_label": "fix"}', "fix", "succeeded"),
        # A malformed routing object is skipped; the well-formed one after it wins.
        ('{"preferred_next_label": } {"preferred_next_label": "fix"}', "fix", "succeeded"),
    ],
)
def test_the_directive_parse_matches_the_engines_object_scan(
    text: str, label: str, outcome: str
) -> None:
    """Accelerators are stripped and the object scan survives nesting, strings and stray braces."""
    output = _engine_output(output_schema=None, text=text)

    assert output["preferred_label"] == label
    assert output["outcome"] == outcome


def test_a_glued_label_is_still_the_directive() -> None:
    """The engine scans objects, not lines: a label glued to prose is parsed either way."""
    for text in _ST4OBS_RED_TEXTS:
        directive = _directive(text)
        assert directive is not None
        assert directive["preferred_next_label"] == "seeded-open-red"


# --- the defect: the committed red node must route the recorded messages --------


@pytest.mark.parametrize("attempt", [1, 2, 3])
def test_the_recorded_seeded_open_red_endings_route_to_green_admission(attempt: int) -> None:
    """Each recorded st4obs red ending reaches `green_admission` through the committed node."""
    graph = _graph(_IMPLEMENT)
    output = _engine_output(
        output_schema=graph.nodes["red"].get("output_schema"),
        text=_ST4OBS_RED_TEXTS[attempt - 1],
    )

    assert _destination(graph=graph, source="red", output=output) == "green_admission", output


@pytest.mark.parametrize(
    ("node", "text", "destination"),
    [
        (
            "red",
            'No test to write.\n\n{"preferred_next_label": "already-satisfied"}',
            "already_satisfied_route",
        ),
        ("red", "## red\nRed test file: tests/x.py\n", "commit_red"),
        (
            "red",
            '{"outcome": "failed", "failure_reason": "Definition of Done amendment for x"}',
            "implement_amendment_route",
        ),
        ("green", 'The Red is wrong.{"preferred_next_label":"test-wrong"}', "test_wrong_reset"),
        ("red", _M5CPNL_RED_2_TEXT, "red_needs_human_route"),
        (
            "green",
            'The fix needs a workflow edit.{"preferred_next_label":"needs-human"}',
            "green_needs_human_route",
        ),
        ("red", _EQTYYR_RED_2_TAIL, "red_unknown_label_route"),
        (
            "green",
            'Done.{"definition_of_done_complete":true,"preferred_next_label":"complete"}',
            "green_unknown_label_route",
        ),
        ("green", 'Done.{"definition_of_done_complete":true}', "implement_completion"),
        (
            "green",
            'Blocked.{"outcome":"failed","failure_reason":"Definition of Done amendment for x"}',
            "green_amendment_route",
        ),
    ],
)
def test_every_red_and_green_ending_selects_its_edge(
    node: str, text: str, destination: str
) -> None:
    """Every ending the red and green prompts direct selects the edge the graph draws for it."""
    graph = _graph(_IMPLEMENT)
    output = _engine_output(output_schema=graph.nodes[node].get("output_schema"), text=text)

    assert _destination(graph=graph, source=node, output=output) == destination, output


# --- fleet scope: no routed agent node declares a schema the engine never routes on


def test_no_agent_node_with_a_routed_label_declares_a_json_schema() -> None:
    """In every committed graph a `preferred_label=` edge leaves a node whose contract sets it."""
    dead: list[tuple[str, str, str]] = []
    for relative, graph in _every_graph():
        dead.extend(
            (relative, node, schema)
            for node, schema in _agent_nodes_with_label_edges(graph).items()
            if schema is not None and schema != "routing"
        )

    assert dead == []


def test_the_implement_graph_still_routes_the_red_and_green_labels() -> None:
    """The guard above has subjects: red and green keep their routed labels."""
    graph = _graph(_IMPLEMENT)

    assert set(_agent_nodes_with_label_edges(graph)) >= {"red", "green"}


@pytest.mark.parametrize(
    ("node", "route", "known"),
    [
        (
            "red",
            "red_unknown_label_route",
            {"seeded-open-red", "seeded-red-passes", "already-satisfied", "needs-human"},
        ),
        ("green", "green_unknown_label_route", {"test-wrong", "needs-human"}),
    ],
)
def test_the_catch_all_edge_excludes_exactly_the_routed_labels(
    node: str, route: str, known: set[str]
) -> None:
    """Every other label is refused: the catch-all excludes each routed label and no other."""
    graph = _graph(_IMPLEMENT)
    destination, excluded = _catch_all_exclusions(graph=graph, source=node)
    routed = {
        edge.attributes["condition"].removeprefix("preferred_label=")
        for edge in graph.edges
        if edge.source == node
        and (edge.attributes.get("condition") or "").startswith("preferred_label=")
    }

    assert destination == route
    assert excluded == routed == known


def test_the_red_and_green_prompts_direct_each_routed_label() -> None:
    """Each routed label is one the prompt tells the agent to emit as `preferred_next_label`."""
    red = (_PROMPTS / "red.md").read_text(encoding="utf-8")
    green = (_PROMPTS / "green.md").read_text(encoding="utf-8")

    assert '{"preferred_next_label": "seeded-open-red"}' in red
    assert '{"preferred_next_label": "seeded-red-passes"}' in red
    assert '{"preferred_next_label": "already-satisfied"}' in red
    assert '{"preferred_next_label": "test-wrong"}' in green
    assert '{"preferred_next_label": "needs-human"}' in red
    assert '{"preferred_next_label": "needs-human"}' in green


# --- the completion gate reads a context key the green contract still writes -----


def test_the_completion_gate_reads_the_green_response_text(tmp_path: Path) -> None:
    """`implement_completion` reads the green turn's recorded text, where the field lives.

    Without a JSON-Schema contract nothing writes `context.output.green`, so the
    gate's stdin is the full `response.green` text; the gate already reads the
    field from it with whitespace deleted, so a Codex-shaped message with the
    field glued to prose still grades complete.
    """
    graph = _graph(_IMPLEMENT)
    assert graph.nodes["implement_completion"]["stdin_source"] == "context.response.green"

    checkout = tmp_path / "checkout"
    _ = subprocess.run(("git", "init", "--quiet", str(checkout)), check=True)
    text = (
        "Warning: Skill descriptions were shortened to fit the skills context budget.\n\n"
        'Every assertion holds on the tree.{"definition_of_done_complete":true}'
    )
    result = subprocess.run(
        ("sh", "-c", graph.nodes["implement_completion"]["script"]),
        check=False,
        cwd=checkout,
        input=text,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line]
    assert json.loads(lines[-1]) == {"preferred_next_label": "complete"}, result.stderr
