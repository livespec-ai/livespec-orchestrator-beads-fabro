"""Temporary Red-phase import stub for the delivery classification tests."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

MergedPullRequestLookup = Callable[[Path, str], int | None]


def merged_pull_request_number(*, repo: Path, branch: str) -> int | None:
    """Return the sentinel value until the Green implementation is staged."""
    del repo, branch
    return None


def delivered_merged_pull_request(
    *,
    repo: Path,
    work_item_ref: str,
    returncode: int,
    stderr: str,
    lookup: MergedPullRequestLookup | None,
) -> int | None:
    """Support imports while deliberately leaving delivered runs unclassified."""
    del repo, work_item_ref, returncode, stderr, lookup
    return None
