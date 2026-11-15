"""The implement stage's mechanical commit-refusal re-entry budget (bd-ib-pyeiky).

`SPECIFICATION/contracts.md` section "Self-contained plugin dispatch" -> "A
purely mechanical commit refusal has its own re-entry budget" (v287). A
repository MAY declare `dispatcher.implement.mechanical_targets`, the
commit-hook targets an implement turn can repair mechanically, and
`dispatcher.implement.mechanical_reentries`, which defaults to 2 when the list
is declared and to 0 when it is not. Both keys apply to the implement stage as
a whole.

This module resolves the two keys from the dispatcher block and renders them
into the payload's own copy of the workflow graph:

- The two workflow inputs `implement_mechanical_targets` and
  `implement_mechanical_reentries` that `commit_green`'s script passes to the
  materialized `livespec-commit-green.sh` are written in as literal shell
  words, from the SAME block read the node timeouts come from. The committed
  `workflow.toml` declares both with the no-budget defaults, so an unrendered
  graph still runs with no mechanical re-entry.
- Every node the green re-entry loop visits once per green turn has its
  `max_visits` raised by the resolved re-entries, so the engine's visit bound
  is derived as one visit plus the node's ordinary re-entries plus the
  mechanical ones, and a change to `mechanical_reentries` needs no workflow
  edit. The ordinary bounds stay the committed literals.

`max_visits` is rendered rather than templated for the reason
`_dispatcher_graph_render` gives for `timeout`: a typed attribute templated
from an input renders to a string the engine does not read as a number.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__: list[str] = [
    "DEFAULT_DECLARED_MECHANICAL_REENTRIES",
    "MECHANICAL_REENTRIES_INPUT",
    "MECHANICAL_REENTRIES_KEY",
    "MECHANICAL_REENTRY_NODES",
    "MECHANICAL_TARGETS_INPUT",
    "MECHANICAL_TARGETS_KEY",
    "NO_MECHANICAL_REENTRIES",
    "MechanicalReentryPolicy",
    "RenderedMechanicalReentries",
    "apply_mechanical_reentries",
    "mechanical_reentry_policy_from_block",
    "render_mechanical_reentries",
]

MECHANICAL_TARGETS_KEY = "dispatcher.implement.mechanical_targets"
MECHANICAL_REENTRIES_KEY = "dispatcher.implement.mechanical_reentries"
MECHANICAL_TARGETS_INPUT = "implement_mechanical_targets"
MECHANICAL_REENTRIES_INPUT = "implement_mechanical_reentries"
DEFAULT_DECLARED_MECHANICAL_REENTRIES = 2

# The nodes the split graph visits once per `green` turn. A mechanical
# re-entry is one more `green` turn, so each of them needs one more visit;
# raising `green` alone would let `implement_completion` or `commit_green`
# abort the run at entry on the extra turn.
MECHANICAL_REENTRY_NODES: tuple[str, ...] = (
    "green",
    "green_admission",
    "green_amendment_route",
    "implement_completion",
    "commit_green",
)

_IMPLEMENT_KEY = "implement"
_TARGETS_FIELD = "mechanical_targets"
_REENTRIES_FIELD = "mechanical_reentries"
_TARGET_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")
# Same node-block shape `_dispatcher_graph_render` reads: a bare name at line
# start, then a bracketed body admitting no `]` of its own.
_NODE_BLOCK_RE = re.compile(r"(?ms)^[ \t]*(?P<name>\w+)[ \t]*\[(?P<body>[^\]]*)\]")
_MAX_VISITS_RE = re.compile(r"(?<![\w.])max_visits[ \t]*=[ \t]*(?P<value>\d+)")


@dataclass(frozen=True, kw_only=True)
class MechanicalReentryPolicy:
    """The declared mechanical targets and the stage-wide mechanical re-entries."""

    targets: tuple[str, ...]
    reentries: int


NO_MECHANICAL_REENTRIES = MechanicalReentryPolicy(targets=(), reentries=0)


@dataclass(frozen=True, kw_only=True)
class RenderedMechanicalReentries:
    """A graph carrying the literal mechanical inputs and the raised visit bounds."""

    text: str
    node_visits: Mapping[str, int]


def mechanical_reentry_policy_from_block(
    *, block: Mapping[str, object]
) -> MechanicalReentryPolicy | str:
    """Resolve the two keys from a dispatcher block, or an actionable refusal.

    An absent `implement` block, or one declaring neither key, is no budget.
    A malformed value refuses the dispatch before any run exists, naming the
    key, rather than silently running with no budget the repository asked for.
    """
    raw_implement = block.get(_IMPLEMENT_KEY)
    if raw_implement is None:
        return NO_MECHANICAL_REENTRIES
    if not isinstance(raw_implement, dict):
        return f"dispatcher.implement must be an object, got {raw_implement!r}"
    implement = cast("dict[str, object]", raw_implement)
    targets = _declared_targets(raw=implement.get(_TARGETS_FIELD))
    if isinstance(targets, str):
        return targets
    default = DEFAULT_DECLARED_MECHANICAL_REENTRIES if targets else 0
    reentries = _declared_reentries(raw=implement.get(_REENTRIES_FIELD, default))
    if isinstance(reentries, str):
        return reentries
    return MechanicalReentryPolicy(targets=targets, reentries=reentries)


def _declared_targets(*, raw: object) -> tuple[str, ...] | str:
    """The declared target names, or a refusal naming the key."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        return f"{MECHANICAL_TARGETS_KEY} must be a list of commit-hook target names"
    names = cast("list[object]", raw)
    for name in names:
        if not isinstance(name, str) or _TARGET_NAME_RE.fullmatch(name) is None:
            return (
                f"{MECHANICAL_TARGETS_KEY} names {name!r}, which is not a commit-hook "
                "target name (letters, digits, '.', '_' and '-')"
            )
    return tuple(cast("list[str]", names))


def _declared_reentries(*, raw: object) -> int | str:
    """The declared re-entry count, or a refusal naming the key."""
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return f"{MECHANICAL_REENTRIES_KEY} must be a non-negative integer, got {raw!r}"
    return raw


def render_mechanical_reentries(
    *, graph_text: str, policy: MechanicalReentryPolicy
) -> RenderedMechanicalReentries | str:
    """Write the policy into a graph that carries the mechanical inputs.

    A graph that never names `implement_mechanical_reentries` has no mechanical
    route and comes back unchanged. One that does must declare `max_visits` on
    every node of `MECHANICAL_REENTRY_NODES`; a node the rewrite cannot raise
    refuses the dispatch, because a bound left at its committed literal would
    end the run on a re-entry the budget granted.
    """
    if _input_token(name=MECHANICAL_REENTRIES_INPUT) not in graph_text:
        return RenderedMechanicalReentries(text=graph_text, node_visits={})
    text = graph_text.replace(
        _input_token(name=MECHANICAL_TARGETS_INPUT), shlex.quote(",".join(policy.targets))
    ).replace(_input_token(name=MECHANICAL_REENTRIES_INPUT), str(policy.reentries))
    pieces: list[str] = []
    node_visits: dict[str, int] = {}
    cursor = 0
    for match in _NODE_BLOCK_RE.finditer(text):
        name = match.group("name")
        body = match.group("body")
        visits = _MAX_VISITS_RE.search(body)
        if name in MECHANICAL_REENTRY_NODES and visits is not None:
            raised = int(visits.group("value")) + policy.reentries
            node_visits[name] = raised
            body = f"{body[: visits.start()]}max_visits={raised}{body[visits.end() :]}"
        pieces.append(text[cursor : match.start("body")])
        pieces.append(body)
        cursor = match.end("body")
    pieces.append(text[cursor:])
    missing = [node for node in MECHANICAL_REENTRY_NODES if node not in node_visits]
    if missing:
        return (
            "workflow graph is not renderable: the mechanical re-entry budget needs "
            f"a max_visits on {', '.join(missing)}"
        )
    return RenderedMechanicalReentries(text="".join(pieces), node_visits=node_visits)


def _input_token(*, name: str) -> str:
    """The workflow-input token the committed graph spells for `name`."""
    return "{{ inputs." + name + " }}"


def apply_mechanical_reentries(*, graph: Path, block: Mapping[str, object]) -> str | None:
    """Render the dispatcher block's policy into a materialized payload graph in place.

    Returns None once the graph carries the policy, or the refusal the caller
    reports before any run exists: a malformed key, an unreadable graph, or a
    graph whose loop nodes the render cannot raise.
    """
    policy = mechanical_reentry_policy_from_block(block=block)
    if isinstance(policy, str):
        return policy
    text = attempt(action=lambda: graph.read_text(encoding="utf-8"), exceptions=(OSError,))
    if isinstance(text, AttemptFailure):
        return f"workflow payload graph {graph} is unreadable: {text.error}"
    rendered = render_mechanical_reentries(graph_text=text, policy=policy)
    if isinstance(rendered, str):
        return rendered
    _ = graph.write_text(rendered.text, encoding="utf-8")
    return None
