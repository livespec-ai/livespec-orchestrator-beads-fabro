"""Parse and render the result of one implementation dispatch."""

from __future__ import annotations

from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_merge_wait_handoff import (
    HANDED_OFF_STATUS,
)
from livespec_orchestrator_beads_fabro.effects import JsonParseFailure, parse_json

__all__: list[str] = [
    "dispatch_status",
    "dispatch_summary",
    "goal_template_refusal",
    "parse_dispatcher_json",
]


def dispatch_status(*, returncode: int, parsed: object) -> str:
    """Return the Dispatcher status, falling back to its process outcome."""
    if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
        status = cast("dict[str, object]", parsed[0]).get("status")
        if isinstance(status, str):
            return status
    return "green" if returncode == 0 else "failed"


def dispatch_summary(
    *,
    status: str,
    work_item_ref: str,
    goal_template_refusal_detail: str | None,
    merged_pull_request: int | None,
) -> str:
    """Render the concise drive result summary."""
    if status == "green":
        return f"Dispatcher reported green for {work_item_ref}."
    if status == HANDED_OFF_STATUS:
        return (
            f"Dispatcher handed the merge wait for {work_item_ref} off to reconciliation: "
            "its pull request is armed and its required checks are passing or still running."
        )
    if status == "blocked":
        return f"Dispatcher reported a human-gated blocked run for {work_item_ref}."
    if goal_template_refusal_detail is not None:
        return f"Dispatcher refused at goal-minijinja-preflight: {goal_template_refusal_detail}."
    if merged_pull_request is not None:
        return (
            f"Dispatcher delivered {work_item_ref}: merged pull request #{merged_pull_request} "
            "landed before its final ready-set refusal."
        )
    return f"Dispatcher did not report green for {work_item_ref}."


def goal_template_refusal(*, parsed: object) -> str | None:
    """Extract the safe preflight detail from one Dispatcher JSON outcome."""
    if not isinstance(parsed, list):
        return None
    outcomes = cast("list[object]", parsed)
    if len(outcomes) != 1 or not isinstance(outcomes[0], dict):
        return None
    outcome = cast("dict[str, object]", outcomes[0])
    detail = outcome.get("detail")
    return (
        detail
        if outcome.get("stage") == "goal-minijinja-preflight" and isinstance(detail, str)
        else None
    )


def parse_dispatcher_json(*, text: str) -> object:
    """Return a JSON object or array, treating malformed Dispatcher output as absent."""
    parsed = parse_json(text=text)
    return None if isinstance(parsed, JsonParseFailure) else parsed
