"""Classify the final ready-set refusal that can follow a delivered run."""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.effects import parse_json

__all__: list[str] = ["MergedPullRequestLookup", "delivered_merged_pull_request"]

MergedPullRequestLookup = Callable[[Path, str], int | None]
_READY_SET_REFUSAL_EXIT_CODE = 3


def delivered_merged_pull_request(
    *,
    repo: Path,
    work_item_ref: str,
    returncode: int,
    stderr: str,
    lookup: MergedPullRequestLookup | None,
) -> int | None:
    """Return a merged PR only for the Dispatcher ending that can follow delivery."""
    if (
        returncode != _READY_SET_REFUSAL_EXIT_CODE
        or "requested work-item(s) not in the ready set" not in stderr
    ):
        return None
    branch = f"feat/{work_item_ref}"
    if lookup is not None:
        return lookup(repo, branch)
    return merged_pull_request_number(repo=repo, branch=branch)


def merged_pull_request_number(*, repo: Path, branch: str) -> int | None:
    """Read the newest merged pull request for one canonical publish branch."""
    gh = shutil.which("gh")
    if gh is None:
        return None
    completed = subprocess.run(  # noqa: S603 - argv is constructed without shell.
        [
            gh,
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "merged",
            "--json",
            "number",
            "--limit",
            "20",
        ],
        check=False,
        cwd=repo,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return None
    parsed = parse_json(text=completed.stdout)
    if not isinstance(parsed, list):
        return None
    numbers: list[int] = []
    for row in cast("list[object]", parsed):
        if not isinstance(row, dict):
            continue
        number = cast("dict[str, object]", row).get("number")
        if isinstance(number, int) and number > 0:
            numbers.append(number)
    return max(numbers, default=None)
