"""The compact field reader shared by Definition-of-Done judgement receipts."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_governing_record import (
    GOVERNING_EVIDENCE_FIELD,
    GOVERNING_HEADING_FIELD,
    GOVERNING_NAMED_CLAUSE_FIELD,
    GOVERNING_SELECTED_CLAUSE_FIELD,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_input_record import (
    BOUND_ENDED_CANDIDATE_FIELD,
)

FIELD_SEPARATOR = ": "
REPEATED_FIELDS = frozenset(
    {
        "finding",
        GOVERNING_HEADING_FIELD,
        GOVERNING_EVIDENCE_FIELD,
        GOVERNING_SELECTED_CLAUSE_FIELD,
        GOVERNING_NAMED_CLAUSE_FIELD,
        BOUND_ENDED_CANDIDATE_FIELD,
    }
)


def fields_of(*, body: str) -> dict[str, str]:
    """Return non-repeated receipt fields, with the final occurrence winning."""
    fields: dict[str, str] = {}
    for raw in body.splitlines():
        key, separator, value = raw.strip().partition(FIELD_SEPARATOR)
        if separator and key not in REPEATED_FIELDS:
            fields[key] = value
    return fields


def repeated(*, body: str, key: str) -> tuple[str, ...]:
    """Return every value the receipt recorded for one repeated key."""
    prefix = f"{key}{FIELD_SEPARATOR}"
    return tuple(
        raw.strip()[len(prefix) :] for raw in body.splitlines() if raw.strip().startswith(prefix)
    )
