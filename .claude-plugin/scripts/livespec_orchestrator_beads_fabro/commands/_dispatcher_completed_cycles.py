"""Derive one dispatch's distinct verified Red-Green pairs from provenance."""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_commits import (
    GREEN_TRAILER_KEY,
    RED_TRAILER_KEY,
    commit_trailers,
)

__all__: list[str] = [
    "UNOBSERVED_COMMITS_UNREADABLE",
    "UNOBSERVED_NO_DISPATCH_ID",
    "UNOBSERVED_NO_PULL_REQUEST",
    "UNOBSERVED_SERIES_NOT_IDENTIFIED",
    "VerifiedPairCount",
    "observed_pair_count",
    "unobserved_pair_count",
    "verified_pair_ids",
]

UNOBSERVED_NO_PULL_REQUEST = "no-pull-request"
UNOBSERVED_NO_DISPATCH_ID = "no-dispatch-id"
UNOBSERVED_COMMITS_UNREADABLE = "commits-unreadable"
UNOBSERVED_SERIES_NOT_IDENTIFIED = "series-not-identified"

_RED_TEST_CHECKSUM_TRAILER_KEY = "TDD-Red-Test-File-Checksum"


@dataclass(frozen=True, kw_only=True)
class VerifiedPairCount:
    """An observed count, or the reason the dispatch series was unreadable."""

    count: int | None
    unobserved_reason: str | None


def verified_pair_ids(*, messages: tuple[str, ...]) -> tuple[str, ...]:
    """Return each distinct complete pair in an already-selected dispatch series.

    A completed cycle carries both replay trailer sets.  Its Red checksum and
    capture instant identify the underlying Red across duplicate observations;
    a legacy Red without a checksum falls back to the complete message.
    """
    found: dict[str, None] = {}
    for message in messages:
        trailers = commit_trailers(message=message)
        red_at = trailers.get(RED_TRAILER_KEY)
        if red_at is None or GREEN_TRAILER_KEY not in trailers:
            continue
        checksum = trailers.get(_RED_TEST_CHECKSUM_TRAILER_KEY)
        identity = f"{checksum}@{red_at}" if checksum is not None else f"message:{message}"
        found[identity] = None
    return tuple(found)


def observed_pair_count(*, messages: tuple[str, ...]) -> VerifiedPairCount:
    """Count a readable series, including a readable series with zero pairs."""
    return VerifiedPairCount(
        count=len(verified_pair_ids(messages=messages)), unobserved_reason=None
    )


def unobserved_pair_count(*, reason: str) -> VerifiedPairCount:
    """Record why a series could not be read without manufacturing a zero."""
    return VerifiedPairCount(count=None, unobserved_reason=reason)
