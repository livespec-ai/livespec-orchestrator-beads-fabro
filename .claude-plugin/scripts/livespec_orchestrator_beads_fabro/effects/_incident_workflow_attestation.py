"""Verify the maintainer comment a workflow-scope receipt names, on the forge.

A receipt is a request, never authority: the writer records a workflow scope
only after the forge itself shows a comment that a human maintainer posted and
that states this exact item, operation and path list.  An agent session posts
as a bot App, so it can neither author that comment nor mint a receipt that
passes without it.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: bd-ib-dzbwaq
from __future__ import annotations

from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.effects import parse_json

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import CommandRunner

__all__: list[str] = ["ATTESTATION_MARKER", "attestation_line", "unverified_reason"]

ATTESTATION_MARKER = "livespec-workflow-attestation:"
_HUMAN = "User"
_MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
_TIMEOUT_SECONDS = 60.0


def attestation_line(*, item_id: str, operation_id: str, workflow_paths: tuple[str, ...]) -> str:
    """The one exact line a maintainer comment must carry to attest this scope."""
    return (
        f"{ATTESTATION_MARKER} item={item_id} operation={operation_id} "
        f"paths={','.join(workflow_paths)}"
    )


def unverified_reason(
    *,
    runner: CommandRunner,
    repo: Path,
    repository: str,
    comment_id: int,
    attester_login: str,
    expected_line: str,
) -> str | None:
    """Why the named comment does not attest the scope; None when the forge verifies it."""
    result = runner.run(
        argv=["gh", "api", f"repos/{repository}/issues/comments/{comment_id}"],
        cwd=repo,
        timeout_seconds=_TIMEOUT_SECONDS,
    )
    raw = parse_json(text=result.stdout) if result.exit_code == 0 else None
    comment = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    user, body = comment.get("user"), comment.get("body")
    if not isinstance(user, dict) or not isinstance(body, str):
        return f"comment {comment_id}: the forge returned no readable comment"
    author = cast("dict[str, object]", user)
    if author.get("type") != _HUMAN:
        return f"comment {comment_id}: its author is not a human account"
    if author.get("login") != attester_login:
        return f"comment {comment_id}: not by the named attester {attester_login}"
    if comment.get("author_association") not in _MAINTAINER_ASSOCIATIONS:
        return f"comment {comment_id}: its author is not a maintainer of {repository}"
    if expected_line not in body.splitlines():
        return f"comment {comment_id}: it does not state the exact attestation line"
    return None
