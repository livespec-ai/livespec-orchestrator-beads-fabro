"""Admission's repayment-phase writes around the factory claim (bd-ib-wz6bsa).

The Dispatcher's admission of a `ready` item is the one path every incident
repayment takes to a factory run, whether an operator's `approve` or an
automatic approval moved it to `ready`. `admit_with_repayment_phase` wraps the
claim (`admit_item`, handed in by `_dispatcher_admission_writes`) so the chain
records `repayment-ready` before the claim is taken and `repayment-active` once
the item rests `active` under it, which is the phase/state pairing the
incident lifecycle in SPECIFICATION/contracts.md requires.

A phase the chain cannot record refuses the dispatch by name rather than
running a repayment the chain could never bind. Before the claim nothing is
written. After it, the item rests `active` under this dispatch's stamp with no
run, which the stranded-claim release returns to `ready`; the next admission
then records the phase it pairs with.

An item with no repayment in play is admitted exactly as before, after one
record read and no comment read. Every incident transition writes the item's
`incident_authority_head` hint, so an item whose record carries none has no
chain to keep in step and is claimed without the sync. A hint is where a
current read starts, never authority, so an item that carries one still takes
the full sync, and a record the tenant cannot serve does too: the sync then
refuses by name rather than letting a repayment run unbound.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal
from livespec_orchestrator_beads_fabro.incident_repayment_phase_sync import (
    repayment_in_play,
    sync_repayment_phase,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from livespec_orchestrator_beads_fabro._beads_client import BeadsClient
    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["PHASE_UNRECORDED", "admit_with_repayment_phase"]

PHASE_UNRECORDED = "incident-repayment-phase-unrecorded"


def _unrecorded(*, item_id: str, refusal: AuthorityRefusal) -> str:
    return (
        f"{PHASE_UNRECORDED}: work-item {item_id} carries incident authority, and the chain "
        f"refused the repayment phase its lifecycle state pairs with ({refusal.code}: "
        f"{refusal.detail}); no factory run was started.\n"
    )


def admit_with_repayment_phase(
    *,
    config: StoreConfig,
    item_id: str,
    client: BeadsClient | None = None,
    admit: Callable[..., str | None],
    claim: Mapping[str, object] | None = None,
) -> str | None:
    """Claim one admitted item, recording the repayment phase on each side of the claim."""
    tenant = client if client is not None else make_beads_client(config=config)
    if not repayment_in_play(client=tenant, item_id=item_id):
        return admit(config=config, item_id=item_id, **(claim or {}))
    before = sync_repayment_phase(client=tenant, item_id=item_id)
    if isinstance(before, AuthorityRefusal):
        return _unrecorded(item_id=item_id, refusal=before)
    refusal = admit(config=config, item_id=item_id, **(claim or {}))
    if refusal is not None:
        return refusal
    after = sync_repayment_phase(client=tenant, item_id=item_id)
    return (
        _unrecorded(item_id=item_id, refusal=after) if isinstance(after, AuthorityRefusal) else None
    )
