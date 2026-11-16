"""The mechanical commit-refusal budget's resolution and graph render (bd-ib-pyeiky).

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch" -> "A
purely mechanical commit refusal has its own re-entry budget": the two
stage-wide keys resolve with a default of 2 re-entries when the target list is
declared and 0 when it is not, and the materialized workflow's visit bound for
each re-entered node is one visit plus its ordinary re-entries plus the
resolved mechanical re-entries, so changing the key needs no workflow edit.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_implement_mechanical import (
    MECHANICAL_REENTRIES_KEY,
    MECHANICAL_REENTRY_NODES,
    MECHANICAL_TARGETS_KEY,
    NO_MECHANICAL_REENTRIES,
    MechanicalReentryPolicy,
    RenderedMechanicalReentries,
    mechanical_reentry_policy_from_block,
    render_mechanical_reentries,
)

_COMMIT_GREEN_SCRIPT = (
    'script="bash livespec-commit-green.sh {{ inputs.implement_mechanical_reentries }} '
    '{{ inputs.implement_mechanical_targets }}"'
)


def _graph(*, nodes: tuple[str, ...]) -> str:
    blocks = [
        f'    {node} [\n        max_visits=4\n        timeout="1800s"\n    ]\n' for node in nodes
    ]
    commit = f"    commit_script [\n        {_COMMIT_GREEN_SCRIPT}\n    ]\n"
    return (
        "digraph G {\n" + "".join(blocks) + commit + "    red [\n        max_visits=4\n    ]\n}\n"
    )


def test_an_absent_implement_block_declares_no_budget() -> None:
    assert mechanical_reentry_policy_from_block(block={}) == NO_MECHANICAL_REENTRIES


def test_a_declared_target_list_defaults_to_two_mechanical_reentries() -> None:
    policy = mechanical_reentry_policy_from_block(
        block={"implement": {"mechanical_targets": ["check-lint", "check-per-file-coverage"]}}
    )

    assert policy == MechanicalReentryPolicy(
        targets=("check-lint", "check-per-file-coverage"), reentries=2
    )


def test_an_explicit_reentry_count_wins_and_no_list_defaults_to_zero() -> None:
    explicit = mechanical_reentry_policy_from_block(
        block={"implement": {"mechanical_targets": ["check-lint"], "mechanical_reentries": 1}}
    )
    unlisted = mechanical_reentry_policy_from_block(block={"implement": {}})

    assert explicit == MechanicalReentryPolicy(targets=("check-lint",), reentries=1)
    assert unlisted == NO_MECHANICAL_REENTRIES


def test_malformed_keys_refuse_naming_the_key() -> None:
    not_object = mechanical_reentry_policy_from_block(block={"implement": ["check-lint"]})
    not_list = mechanical_reentry_policy_from_block(
        block={"implement": {"mechanical_targets": "check-lint"}}
    )
    bad_name = mechanical_reentry_policy_from_block(
        block={"implement": {"mechanical_targets": ["check lint"]}}
    )
    negative = mechanical_reentry_policy_from_block(
        block={"implement": {"mechanical_targets": ["check-lint"], "mechanical_reentries": -1}}
    )
    boolean = mechanical_reentry_policy_from_block(
        block={"implement": {"mechanical_reentries": True}}
    )

    facts = [
        isinstance(not_object, str) and "dispatcher.implement" in not_object,
        isinstance(not_list, str) and MECHANICAL_TARGETS_KEY in not_list,
        isinstance(bad_name, str) and "'check lint'" in bad_name,
        isinstance(negative, str) and MECHANICAL_REENTRIES_KEY in negative,
        isinstance(boolean, str) and MECHANICAL_REENTRIES_KEY in boolean,
    ]
    assert all(facts), facts


def test_rendering_raises_each_green_loop_bound_by_the_mechanical_reentries() -> None:
    rendered = render_mechanical_reentries(
        graph_text=_graph(nodes=MECHANICAL_REENTRY_NODES),
        policy=MechanicalReentryPolicy(targets=("check-lint", "check-format"), reentries=3),
    )

    assert isinstance(rendered, RenderedMechanicalReentries), rendered
    assert rendered.node_visits == dict.fromkeys(MECHANICAL_REENTRY_NODES, 7)
    assert "bash livespec-commit-green.sh 3 check-lint,check-format" in rendered.text
    assert "red [\n        max_visits=4\n" in rendered.text
    assert "{{" not in rendered.text


def test_rendering_no_budget_keeps_the_committed_bounds_and_passes_an_empty_list() -> None:
    rendered = render_mechanical_reentries(
        graph_text=_graph(nodes=MECHANICAL_REENTRY_NODES), policy=NO_MECHANICAL_REENTRIES
    )

    assert isinstance(rendered, RenderedMechanicalReentries), rendered
    assert rendered.node_visits == dict.fromkeys(MECHANICAL_REENTRY_NODES, 4)
    assert "bash livespec-commit-green.sh 0 ''" in rendered.text


def test_a_graph_without_the_mechanical_inputs_comes_back_unchanged() -> None:
    text = "digraph G {\n    green [\n        max_visits=4\n    ]\n}\n"

    rendered = render_mechanical_reentries(
        graph_text=text, policy=MechanicalReentryPolicy(targets=("check-lint",), reentries=2)
    )

    assert rendered == RenderedMechanicalReentries(text=text, node_visits={})


def test_a_loop_node_without_a_visit_bound_refuses_the_render() -> None:
    rendered = render_mechanical_reentries(
        graph_text=_graph(nodes=("green", "commit_green")),
        policy=MechanicalReentryPolicy(targets=("check-lint",), reentries=2),
    )

    assert isinstance(rendered, str)
    assert "green_admission" in rendered
    assert "implement_completion" in rendered
