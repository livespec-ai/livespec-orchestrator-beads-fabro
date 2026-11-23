"""An in-run `dod_gate` check 4 refusal leaves the item it blocks carrying a spec-change-tier hold.

The work-item state semantics in `SPECIFICATION/contracts.md` make `release-spec-tier`
valid on a blocked item "only while the item carries a spec-change-tier hold". The
hold is not a separate store: `spec_change_hold` derives it from the NEWEST
`livespec-spec-change-tier` record on the item, so an item the in-run `dod_gate`
refused rested blocked with a `tier: none` record and no sanctioned primitive could
give it the record the check 4 internal-ruling exception reads (bd-ib-dfqrc7,
legacy-coordinator-agent R301 ruling a').

THE HOLD IS A RECORD WRITE AT THE STEP THAT BLOCKS THE ITEM, through the one record
writer the pre-dispatch wall already uses (`spec_change_tier_comment`): `tier:
spec-change`, stage `dod-gate`, the item's References heading as the generalization
target, and the refusal quoted in the rationale. Nothing here records `tier: none`:
a gate that auto-recorded the tier its own check refused would be grading itself.
The release stays a human act, valve-validated and attested exactly as the contract
states, and with bd-ib-ib5ows the record a press writes names the heading.

IT WRITES AT MOST ONCE PER STANDING HOLD. An item whose newest record already reads
spec-change tier carries the hold this would write, so a second refusal after a
re-dispatch adds no second comment.

IT FAILS OPEN. A ledger that cannot be read, an item that is gone or an unreadable
specification place no hold and leave the outcome exactly as it was: the item still
rests blocked, as it did before this module, and an outage cannot hold an item for a
proposal nobody can name.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_runtime.spec_stated import SpecStatedVerdict

from livespec_orchestrator_beads_fabro._store_comments import append_work_item_comment
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    reference_line_headings,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_comments import (
    item_comment_bodies,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._fabro_causal_stage import STAGE_FAILURE
from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    FEATURE_CLASS,
    SPEC_CHANGE_TIER,
    SPEC_DIRNAME,
    SpecChangeTierDecision,
    behaviour_digest,
    proposal_topic_for,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    recorded_spec_change_tier,
    spec_change_tier_comment,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification
from livespec_orchestrator_beads_fabro.store import read_work_items

if TYPE_CHECKING:
    from livespec_orchestrator_beads_fabro.commands._dispatcher_engine_types import (
        DispatchOutcome,
        JournalWriter,
    )
    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "DOD_GATE_NODE",
    "STAGE_DOD_GATE",
    "attach_dod_gate_tier_hold",
    "dod_gate_check4_refusal",
    "place_dod_gate_tier_hold",
]

DOD_GATE_NODE = "dod_gate"
STAGE_DOD_GATE = "dod-gate"
JOURNAL_STAGE = "dod-gate-tier-hold"

_CHECK_4 = re.compile(r"\bcheck\s*4\b", re.IGNORECASE)
_NODE_PREFIX = re.compile(r"^\d+-")
_RATIONALE_CEILING = 1200


def dod_gate_check4_refusal(*, outcome: DispatchOutcome) -> str | None:
    """The refusal text when this ending is the `dod_gate` node's check 4 refusal, else `None`.

    An ending counts only when it is a needs-human STAGE FAILURE attributed to the
    `dod_gate` node and the failure's own account names check 4: a refusal at any
    other node, a `dod_gate` finding on another check and an agent-request ending
    are not the class this hold exists for.
    """
    if outcome.needs_human_kind != STAGE_FAILURE or not outcome.needs_human_stages:
        return None
    node = _NODE_PREFIX.sub("", outcome.needs_human_stages[-1].split("@", maxsplit=1)[0].strip())
    if node != DOD_GATE_NODE:
        return None
    for text in (outcome.fabro_failure_cause, outcome.needs_human_reason):
        if text is not None and _CHECK_4.search(text) is not None:
            return text
    return None


def place_dod_gate_tier_hold(
    *,
    outcome: DispatchOutcome,
    item: WorkItem,
    spec_version: str,
    comments: Sequence[str],
    append: Callable[..., None],
) -> bool:
    """Record the spec-change-tier hold a check 4 refusal leaves; whether one was written.

    Nothing is written when the ending is not a `dod_gate` check 4 refusal, when
    the item's References line names no heading to hold against, or when its
    newest record already reads spec-change tier.
    """
    refusal = dod_gate_check4_refusal(outcome=outcome)
    if refusal is None:
        return False
    headings = reference_line_headings(text=item.description)
    if not headings:
        return False
    standing = recorded_spec_change_tier(comments=comments)
    if standing is not None and standing.is_spec_change:
        return False
    decision = SpecChangeTierDecision(
        tier=SPEC_CHANGE_TIER,
        classification=FEATURE_CLASS,
        verdict=SpecStatedVerdict(
            kind="unstated",
            stated_by=(),
            generalization_target=headings[0],
            rationale=_quoted(refusal=refusal),
        ),
        linked_proposal_topic=proposal_topic_for(item=item),
    )
    append(
        body=spec_change_tier_comment(
            item_id=item.id,
            stage=STAGE_DOD_GATE,
            decision=decision,
            spec_version=spec_version,
            digest=behaviour_digest(item=item),
        )
    )
    return True


def attach_dod_gate_tier_hold(
    *, outcome: DispatchOutcome, repo: Path, journal: JournalWriter
) -> DispatchOutcome:
    """Place the hold on the item a check 4 refusal blocked; the outcome is returned unchanged.

    Applied where the ending is attributed, at the same step that blocks the item.
    Every read it needs can fail, and every failure returns the outcome untouched.
    """
    if dod_gate_check4_refusal(outcome=outcome) is None:
        return outcome
    config = store_config(repo=repo)
    read = attempt(
        action=lambda: next(
            (item for item in read_work_items(path=config) if item.id == outcome.work_item_id),
            None,
        ),
        exceptions=(OSError, RuntimeError, ValueError),
    )
    comments = item_comment_bodies(path=config, work_item_id=outcome.work_item_id)
    specification = attempt(
        action=lambda: read_current_specification(spec_root=repo / SPEC_DIRNAME),
        exceptions=(OSError,),
    )
    if (
        isinstance(read, AttemptFailure)
        or read is None
        or comments is None
        or isinstance(specification, AttemptFailure)
    ):
        return outcome
    item = read

    def append(*, body: str) -> None:
        append_work_item_comment(path=config, work_item_id=item.id, body=body)

    placed = place_dod_gate_tier_hold(
        outcome=outcome,
        item=item,
        spec_version=str(specification.version),
        comments=comments,
        append=append,
    )
    if placed:
        journal.append(
            record={
                "work_item_id": item.id,
                "stage": JOURNAL_STAGE,
                "run_id": outcome.fabro_run_id,
                "heading": reference_line_headings(text=item.description)[0],
            }
        )
    return outcome


def _quoted(*, refusal: str) -> str:
    """The refusal on one line, capped: a record field holds a single line."""
    flat = " ".join(refusal.split())
    quoted = f"in-run dod_gate refused on check 4: {flat}"
    return quoted if len(quoted) <= _RATIONALE_CEILING else quoted[: _RATIONALE_CEILING - 1] + "…"
