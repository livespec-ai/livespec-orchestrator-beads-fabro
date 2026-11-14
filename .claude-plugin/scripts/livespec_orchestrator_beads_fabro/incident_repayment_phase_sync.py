"""Keep an incident repayment's chain in step with ordinary admission.

An incident repayment item reaches its factory run through ordinary admission:
an approval moves it `pending-approval` -> `ready`, and the Dispatcher's claim
moves it `ready` -> `active`. The incident chain pairs each of those states
with a repayment phase (`repayment-ready`, `repayment-active`); when nothing
records them, the chain stays at `repayment-admission` while the item moves
on, and `bind-repayment-acceptance` can never bind the merged repayment PR
(bd-ib-wz6bsa, measured on livespec-57r6qo).

`sync_repayment_phase` records whichever phase the item's lifecycle state now
pairs with, through the same writers every repayment step uses:
`advance_repayment` for `repayment-ready` (the item rests `ready`, so ordinary
admission approved it), and `recover_repayment_phases` once the item rests
`active` or later under a factory claim. It answers `None` for an item with no
incident authority and for any chain that is not between `repayment-admission`
and `repayment-ready`, so ordinary work pays one comment read and nothing else.
The repository the chain is keyed by is read from the item's own genesis
record; the reader then revalidates that record against its fenced root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro._incident_authority_payload import (
    GENESIS_MARKER,
    HEAD_HINT_KEY,
    decode_record,
)
from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro._incident_phases import REPAYMENT_PHASES
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.effects._incident_authority_reader import (
    read_incident_head,
)
from livespec_orchestrator_beads_fabro.effects._incident_genesis_fence import (
    FENCED_GENESIS_KEYS,
)
from livespec_orchestrator_beads_fabro.errors import (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)
from livespec_orchestrator_beads_fabro.incident_normal_repayment import (
    RepaymentEntry,
    advance_repayment,
)
from livespec_orchestrator_beads_fabro.incident_repayment_recovery import (
    RECOVERABLE_STATUSES,
    recover_repayment_phases,
)

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient

__all__: list[str] = ["genesis_repository", "repayment_in_play", "sync_repayment_phase"]

_GENESIS_KEYS = frozenset(("schema", "repository", "item_id", "root_token_id"))
_ADMISSION, _READY = REPAYMENT_PHASES[:2]


def genesis_repository(*, client: BeadsClient, item_id: str) -> str | None:
    """The repository the item's genesis record names, or None for an item with none."""
    for comment in client.list_comments(issue_id=item_id):
        text = comment.get("text")
        if not isinstance(text, str) or not text.startswith(GENESIS_MARKER):
            continue
        record = decode_record(
            text=text, marker=GENESIS_MARKER, keys=_GENESIS_KEYS
        ) or decode_record(text=text, marker=GENESIS_MARKER, keys=FENCED_GENESIS_KEYS)
        repository = None if record is None else record.get("repository")
        if isinstance(repository, str) and repository:
            return repository
    return None


_RECORD_READ_ERRORS = (
    BeadsCommandError,
    BeadsConnectionError,
    BeadsCredentialMissingError,
    BeadsMappingError,
    BeadsTenantMissingError,
)


def repayment_in_play(*, client: BeadsClient, item_id: str) -> bool:
    """Whether admission owes this item the phase sync: False only for a read record with no hint.

    Every incident transition writes the item's `incident_authority_head` hint, so a
    record that was read and carries none has no chain to keep in step. A hint is
    where a current read starts, never authority, so a record carrying one owes
    the full sync, and so does a record the tenant could not serve: the sync then
    refuses by name instead of letting a repayment run unbound.
    """
    record = attempt(
        action=lambda: client.show_issue(issue_id=item_id), exceptions=_RECORD_READ_ERRORS
    )
    if isinstance(record, AttemptFailure):
        return True
    metadata = record.get("metadata")
    return isinstance(metadata, dict) and bool(
        cast("dict[str, object]", metadata).get(HEAD_HINT_KEY)
    )


def sync_repayment_phase(
    *, client: BeadsClient, item_id: str
) -> RepaymentEntry | AuthorityRefusal | None:
    """Record the phase the item's lifecycle state pairs with, or None when none is owed."""
    repository = genesis_repository(client=client, item_id=item_id)
    if repository is None:
        return None
    head = read_incident_head(client=client, repository=repository, item_id=item_id)
    if isinstance(head, AuthorityRefusal):
        return head
    phase = head.attempt.phase
    if phase not in (_ADMISSION, _READY):
        return None
    status = client.show_issue(issue_id=item_id).get("status")
    if status == "ready" and phase == _ADMISSION:
        return advance_repayment(client=client, reading=head, phase=_READY, admission_complete=True)
    if status in RECOVERABLE_STATUSES:
        return recover_repayment_phases(client=client, reading=head)
    return None
