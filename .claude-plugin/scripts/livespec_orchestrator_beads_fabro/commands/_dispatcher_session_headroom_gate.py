"""Resolving ONE admission evaluation's session-headroom policy.

`SPECIFICATION/contracts.md` section "Dispatcher admission, WIP cap, and
post-merge acceptance": "The floor is a committed-only
`dispatcher.session_headroom_floor_percent` (integer from 0 through 100
inclusive, default 20) ... It is NOT declared API-configurable, and is
therefore committed-only"; "The admission horizon is a committed-only
`dispatcher.session_headroom_horizon_minutes` (integer from 0 through 1440
inclusive, default 180)"; and "One assessment per distinct projected credential
per admission evaluation MUST be reused across nodes and candidates sharing
that credential."

BOTH DIALS ARE RESOLVED HERE, ONCE, AND RIDE THE POLICY TOGETHER. The floor
decides on the LEVEL this reading carries and the horizon decides on the
PROJECTION taken from it, so a filter holding one without the other can grade
only half the clause -- and the two are read from one repository at one instant,
which is what keeps a dispatch from being graded against a floor and a horizon
that were never committed together.

THE MEMO LIVES HERE, IN THE POLICY, AND NOT IN THE FILTER. The filter runs once
per NODE against one `PreflightInputs`, so a memo threaded through it would
have to be a caller-owned dictionary every call site remembered to share. A
policy built once per admission evaluation carries the "at most once" guarantee
as a property of the value instead -- and two concurrent evaluations cannot
share one another's reading, because each built its own policy. That is the
same isolation the probe's explicit memo buys, obtained from the value's
lifetime rather than from a convention.

THE CREDENTIAL IS READ AT READ TIME, NOT AT BUILD TIME. The clause asks for the
"exact credential snapshot that the dispatch would project", and the projection
reads the environment, so taking the snapshot when the first candidate actually
needs it is what keeps the two readings of one variable from diverging. It also
means an evaluation that assesses NO covered candidate issues no request at all.

AN UNREADABLE FLOOR RESOLVES TO THE RATIFIED DEFAULT, exactly as the re-probe
cadence does, and that direction is chosen rather than incidental: the default
IS the specification's value, so a malformed dial falls back onto the behaviour
the clause ratifies rather than onto a disabled filter. The refusal is still
available to a caller that wants to report the malformed dial --
`resolve_session_headroom_floor_percent` returns it -- which is why the two are
separate functions.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom import CodexHeadroomReading
from livespec_orchestrator_beads_fabro.commands._acp_codex_headroom_records import (
    codex_headroom_assessment_record,
)
from livespec_orchestrator_beads_fabro.commands._acp_preflight_verdict import AcpPreflightVerdict
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT,
    DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES,
    DEFAULT_SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT,
    SessionHeadroomPolicy,
    SessionHeadroomReading,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    drain_rate_attempted,
    parse_session_headroom_instant,
    reading_with_drain_rate,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_projection import (
    reading_with_projection,
    session_headroom_projection,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_records import (
    central_selection_record,
    session_headroom_assessment_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_headroom_gate import (
    codex_headroom_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_codex_headroom_io import (
    read_projected_codex_headroom,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    admission_central_and_refusal,
    policy_pool_slots,
    register_admission_slot_chooser,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_baseline import (
    session_headroom_baseline,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_io import (
    central_slot_identity,
    read_projected_session_headroom,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_pool import (
    PoolSelection,
    select_pool_slot,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_session_headroom_settings import (
    SESSION_HEADROOM_FLOOR_PERCENT_KEY,
    SESSION_HEADROOM_HORIZON_MINUTES_KEY,
    SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT_KEY,
    resolve_session_headroom_floor_percent,
    resolve_session_headroom_horizon_minutes,
    resolve_session_headroom_weekly_floor_percent,
)

__all__: list[str] = [
    "SESSION_HEADROOM_FLOOR_PERCENT_KEY",
    "SESSION_HEADROOM_HORIZON_MINUTES_KEY",
    "SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT_KEY",
    "journal_session_headroom",
    "resolve_session_headroom_floor_percent",
    "resolve_session_headroom_horizon_minutes",
    "resolve_session_headroom_weekly_floor_percent",
    "session_headroom_policy",
]


class JournalWriter(Protocol):
    def append(self, *, record: dict[str, object]) -> None:
        """Persist one journal record."""
        ...


@dataclass(frozen=True)
class _PoolAssessmentInputs:
    """The shared policy and context used to assess every injected pool slot."""

    floor_percent: int
    weekly_floor_percent: int
    horizon_minutes: int
    journal_path: Path | None
    now_iso: str


def session_headroom_policy(
    *,
    repo: Path,
    now_iso: str,
    journal_path: Path | None,
    register_chooser: bool = True,
    read: Callable[..., SessionHeadroomReading] = read_projected_session_headroom,
    codex_read: Callable[..., CodexHeadroomReading] = read_projected_codex_headroom,
) -> SessionHeadroomPolicy:
    """This evaluation's two dials plus its at-most-once reading of the projection.

    `journal_path` is the history the DRAIN RATE is measured against, and it is
    a required parameter rather than a defaulted one: `None` is the honest
    answer for a caller holding no journal, and a default would let a caller
    that simply forgot to thread it through report no rate for every dispatch
    forever -- a record that reads exactly like a checkout with no history. It
    is PASSED rather than derived from `repo` because `dispatcher.py` accepts a
    `--journal` override, so a re-derived path can name a different file from
    the one this pass appends to.

    The baseline is read INSIDE the memo, so an evaluation that assesses no
    covered candidate touches the journal no more than it spends a request --
    and the PROJECTION is taken there too, which is what makes "The projection
    MUST be computed only from journaled assessments and MUST NOT issue any
    usage request beyond the one bounded reading this clause already requires"
    a property of the memo rather than a second guarantee to maintain.

    THE MEMO IS THE WHOLE INJECTED SLOT POOL, assessed once and ranked, and the
    slot it chooses is registered as the factory credential every other consumer
    resolves, so one slot is chosen per evaluation and used for the dispatch.
    A launcher that bypasses admission passes `register_chooser=False`: it
    reads the pool's assessments to grade the slot ITS path selected, and must
    not install the admission winner in place of that slot.
    """
    floor = unsafe_perform_io(
        resolve_session_headroom_floor_percent(cwd=repo).value_or(
            DEFAULT_SESSION_HEADROOM_FLOOR_PERCENT
        )
    )
    horizon = unsafe_perform_io(
        resolve_session_headroom_horizon_minutes(cwd=repo).value_or(
            DEFAULT_SESSION_HEADROOM_HORIZON_MINUTES
        )
    )
    weekly_floor = unsafe_perform_io(
        resolve_session_headroom_weekly_floor_percent(cwd=repo).value_or(
            DEFAULT_SESSION_HEADROOM_WEEKLY_FLOOR_PERCENT
        )
    )
    # An absent or invalid policy, or no declared slot injected, is the refusal
    # every covered candidate is skipped by, without a reading.
    # Under `central-factory-selection` the record is read ONCE per evaluation and
    # both the refusal and the one-slot pool below follow that single reading.
    central, refusal = admission_central_and_refusal(
        repo=repo,
        environ=os.environ,
        now=parse_session_headroom_instant(text=now_iso) or datetime.now(timezone.utc),
    )
    taken: list[PoolSelection] = []

    def pool_once() -> PoolSelection:
        if not taken:
            taken.append(
                _assessed_pool(
                    # The declared credential policy decides the pool, read when
                    # the pool is; an absent or invalid one assesses no slot.
                    pool=lambda: policy_pool_slots(repo=repo, environ=os.environ, central=central),
                    read=read,
                    inputs=_PoolAssessmentInputs(
                        floor_percent=floor,
                        weekly_floor_percent=weekly_floor,
                        horizon_minutes=horizon,
                        journal_path=journal_path,
                        now_iso=now_iso,
                    ),
                )
            )
        return taken[0]

    if register_chooser:
        register_admission_slot_chooser(chooser=lambda: pool_once().chosen_slot)

    return SessionHeadroomPolicy(
        floor_percent=floor,
        horizon_minutes=horizon,
        read=lambda: pool_once().representative,
        weekly_floor_percent=weekly_floor,
        pool_read=lambda: pool_once().readings,
        credential_refusal=refusal,
        central_selection=central,
        codex_read=codex_headroom_source(
            now_iso=now_iso,
            journal_path=journal_path,
            floor_percent=floor,
            horizon_minutes=horizon,
            read=codex_read,
        ),
    )


def _assessed(
    *,
    reading: SessionHeadroomReading,
    floor_percent: int,
    horizon_minutes: int,
    journal_path: Path | None,
    now_iso: str,
) -> SessionHeadroomReading:
    """This reading, carrying its drain rate and its ONE projection result.

    THE NOT-ATTEMPTED TEST RUNS BEFORE THE JOURNAL READ, and that order is the
    behaviour rather than an optimization. The clause distinguishes a
    `not-projected` reading -- one the floor settled -- from an `unavailable`
    projection that was attempted and found no baseline, and reading the
    history on a reading the floor already settled is what makes the two
    indistinguishable from the outside: both would end at a null rate, one of
    them having spent a file read per admission pass to establish an absence
    nothing was waiting on.

    THE BASELINE IS READ ONCE AND SPENT TWICE, which is why it is bound to a
    local rather than asked for again by the projection. The rate and the
    projection are two readings OF ONE HISTORY, so a second `session_headroom_
    baseline` call would re-read a journal that concurrent passes append to --
    and a rate measured against one baseline while the projection named another
    is a record whose own two halves disagree.

    THE RESULT IS ALWAYS ATTACHED, including on the arm that computes no rate:
    `not-projected` IS a result, and the clause requires exactly one on every
    assessed credential. A reading that left the field null there would make an
    operator's disabled dial indistinguishable from a build that does not
    project at all.
    """
    baseline = (
        session_headroom_baseline(
            journal_path=journal_path,
            credential_identity=reading.credential_identity,
            now_iso=now_iso,
        )
        if drain_rate_attempted(reading=reading, floor_percent=floor_percent)
        else None
    )
    rated = reading_with_drain_rate(reading=reading, baseline=baseline)
    return reading_with_projection(
        reading=rated,
        projection=session_headroom_projection(
            reading=rated,
            baseline=baseline,
            floor_percent=floor_percent,
            horizon_minutes=horizon_minutes,
        ),
    )


def _assessed_pool(
    *,
    pool: Callable[[], tuple[str, ...]],
    read: Callable[..., SessionHeadroomReading],
    inputs: _PoolAssessmentInputs,
) -> PoolSelection:
    """Assess EVERY injected slot once, then rank them for this evaluation.

    A pool with no injected slot at all is one absent-credential reading, which
    the filter grades exactly as it always has. The chosen slot is whatever
    `select_pool_slot` ranks first; the caam-published account plays no part.
    """
    slots = pool()
    if not slots:
        lone = _assessed(
            reading=read(token=None, observed_at=inputs.now_iso),
            floor_percent=inputs.floor_percent,
            horizon_minutes=inputs.horizon_minutes,
            journal_path=inputs.journal_path,
            now_iso=inputs.now_iso,
        )
        return PoolSelection(readings=(lone,), chosen_slot=None, representative=lone)
    return select_pool_slot(
        readings=tuple(
            (
                slot,
                _assessed(
                    reading=read(token=_projected_token(env_name=slot), observed_at=inputs.now_iso),
                    floor_percent=inputs.floor_percent,
                    horizon_minutes=inputs.horizon_minutes,
                    journal_path=inputs.journal_path,
                    now_iso=inputs.now_iso,
                ),
            )
            for slot in slots
        ),
        floor_percent=inputs.floor_percent,
        weekly_floor_percent=inputs.weekly_floor_percent,
    )


def _projected_token(*, env_name: str) -> str | None:
    """The token one injected pool slot would project.

    Each slot is read by its own name; which slot the dispatch then projects is
    decided once, at admission, and every other consumer follows that choice
    through `select_factory_credential` (`bd-ib-nzp5ln`: assessing a different
    account from the one billed gates on someone else's window).
    """
    return os.environ.get(env_name)


def journal_session_headroom(
    *, work_item_id: str, verdict: AcpPreflightVerdict, journal: JournalWriter
) -> None:
    """Record this evaluation's readings against ONE affected work-item.

    TWO things make this a no-op rather than an empty row, and they are
    different conditions. A verdict carrying NO floor was resolved without a
    policy -- wait attention and idle-factory -- so no reading was ever
    attempted and there is nothing to report. A verdict carrying a floor but NO
    assessments assessed no covered candidate, which is every dispatch in a
    repository routed wholly away from Claude; a row per item per pass there
    would be journal noise naming nothing.

    A REPOSITORY DECLARING NO FALLBACK CHAIN IS IN NEITHER CLASS, and used to
    be read as the first one. Its verdict carries the floor and its assessments
    whenever the admission pass supplied a policy, because the headroom clause
    covers "built-in single-candidate nodes without fallback metadata" --
    `_acp_preflight_verdict._no_fallback_graded` is where that path is graded.

    A floor of ZERO is neither of those: the reading is still attempted and
    still journaled, which is why the guard tests the floor for `None` rather
    than for falsity.

    THE CODEX ASSESSMENTS ARE A SECOND ROW UNDER THEIR OWN STAGE, written after
    the Claude one and under the same two conditions: the two providers' rows are
    each read back by their own baseline reader, so neither may be folded into the
    other's assessments.
    """
    floor = verdict.session_headroom_floor_percent
    if floor is None:
        return
    if verdict.central_selection is not None:
        journal.append(
            record=central_selection_record(
                work_item_id=work_item_id,
                selection=verdict.central_selection,
                verdict=verdict,
                slot_identity=central_slot_identity(selection=verdict.central_selection),
            )
        )
    if verdict.headroom_assessments:
        journal.append(
            record=session_headroom_assessment_record(
                work_item_id=work_item_id,
                floor_percent=floor,
                assessments=verdict.headroom_assessments,
                nodes=verdict.nodes,
            )
        )
    if verdict.codex_headroom_assessments:
        journal.append(
            record=codex_headroom_assessment_record(
                work_item_id=work_item_id,
                floor_percent=floor,
                assessments=verdict.codex_headroom_assessments,
            )
        )
