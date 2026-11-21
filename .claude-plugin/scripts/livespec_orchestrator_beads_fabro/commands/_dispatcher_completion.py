"""Completion, acceptance, and bounce dispositions for the Dispatcher.

The pre-launch host-only refusal that used to sit alongside these lives in
`_dispatcher_host_only_refusal.py`; it is re-exported here because the
Dispatcher's admission layer selects it from this module.
"""

from __future__ import annotations

from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    NEEDS_ATTENTION_VERDICT,
    NO_CHANGE_NEEDED_VERDICT,
    AcceptancePassResult,
    run_acceptance_pass,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_park import (
    park_in_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_result import (
    AcceptanceDisposition,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_rework import (
    AI_DISPOSITIVE_ACCEPTANCE_POLICIES,
    rework_or_block_failed_acceptance,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_blocked import (
    escalate_needs_human_block,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion_bounce import (
    bounce_non_convergence_to_backlog as _bounce_non_convergence_to_backlog,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion_claims import CompletionClaim
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion_close import (
    close_dispatch_item,
    no_change_needed_reason,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_decision_journal import (
    auto_disposition_journal_record,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    PROOF_MODE_FACTORY_CAPTURED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_effective_criteria import (
    effective_criteria,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_host_only_refusal import (
    host_only_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_incident_closure import (
    incident_acceptance_for,
    incident_decision,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_item_ledger_reads import (
    read_dispatch_labels,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_lifecycle_writes import (
    write_work_item_status_and_reconcile,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import store_config
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import item_sizing_warnings
from livespec_orchestrator_beads_fabro.commands._dispatcher_proof_record import (
    VERDICT_NOT_REPRODUCED,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
    DEFAULT_ACCEPTANCE_POLICY,
    effective_acceptance_policy,
)
from livespec_orchestrator_beads_fabro.io import write_stderr
from livespec_orchestrator_beads_fabro.store import update_work_item_status
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "bounce_non_convergence_to_backlog",
    "complete_and_accept",
    "escalate_needs_human_block",
    "host_only_refusal",
    "warn_item_sizing",
]

_NO_CHANGE_NEEDED_RESOLUTION = "no-longer-applicable"


def complete_and_accept(  # noqa: PLR0911, PLR0915 — one return per disposition the valve ends in, and one per ledger write the claim-token protocol can refuse.
    *,
    repo: Path,
    item: WorkItem,
    outcome: DispatchOutcome,
    journal: JournalFile,
    park_unreproduced_factory_captured: bool = False,
) -> AcceptanceDisposition:
    """Run the post-merge acceptance valve for a green dispatch.

    Replaces the prior straight `ready -> done` close. A green Fabro run has
    already merged on green, so the item `complete`s `active -> acceptance`
    (merged + live), then the AI acceptance pass runs (an L1a deterministic
    read-and-judge confirm — no release with zero verification), then `accept`
    confirms per the effective `acceptance_policy`: `ai-only` transitions
    `acceptance -> done` (the close-in-place carrying `resolution=completed`
    + the merge-evidence `AuditRecord`); `human-only` / `ai-then-human` (the
    default) PARK the item in `acceptance` on the ledger, surfaced for a human
    to give final acceptance from the console. Nothing parks silently — the
    park is journaled and surfaced.

    A NEEDS_ATTENTION verdict short-circuits every disposition branch and parks
    under EVERY `acceptance_policy`, `ai-only` included: the pass could not
    observe what a judgment needs, and absence of evidence disposes of nothing.

    EVERY LEDGER WRITE HERE IS A CLAIM-CHANGING WRITE, made through
    `CompletionClaim`. With `dispatcher.claim_tokens` true the completion and
    each close land only after this valve has won the item's current claim
    token. A refused write has written nothing to the item, so the valve stops
    there and returns the refusal: an acceptance pass run against an item some
    other writer now holds would judge, park or close work it no longer owns.

    RETURNS the disposition so the dispatch RESULT can report it. The parking
    verdict clause governs the result as well as the ledger, and the run terminal
    this is handed says `green` at `done` because the janitor built it before the
    valve ran — so a caller that reported that terminal unchanged would report a
    parked item as a completed close, which is exactly finding F7(b).
    """
    config = store_config(repo=repo)
    claim = CompletionClaim(repo=repo, path=config, item=item, outcome=outcome, journal=journal)
    refused = claim.complete(write=write_work_item_status_and_reconcile)
    if refused is not None:
        return AcceptanceDisposition(verdict=None, closed=False, refusal=refused)
    journal.append(record={"stage": "ledger-complete", "work_item_id": item.id})
    # An unreadable `.livespec.jsonc` falls back to the documented default
    # policy, visibly and here rather than inside the reader.
    # `unsafe_perform_io` is required: `IOResult.value_or` returns
    # `IO[value]`, not the value.
    policy = unsafe_perform_io(
        effective_acceptance_policy(item=item, cwd=repo).value_or(DEFAULT_ACCEPTANCE_POLICY)
    )
    # The item's declared ledger markers carry the change-optional exemption.
    # An unreadable label set is NOT a declaration, so it fails closed to the
    # empty marker set and the pass classifies the item change-implying.
    labels = read_dispatch_labels(repo=repo, item=item)
    # An expedited incident is graded on its cumulative original change plus the
    # current repayment carrier, and closes only once its chain records `closed`.
    incident = incident_acceptance_for(config=config, item_id=item.id, merged_pr=outcome.pr_number)
    acceptance_pass = run_acceptance_pass(
        repo=repo,
        item=item,
        outcome=outcome,
        raw_labels=() if isinstance(labels, str) else labels,
        # The journal is where the proof leg recovers the merging dispatch's
        # identifiers: the dispatch id lives only in the `dispatch-id` record, and
        # the reconcile valve reaches here with an outcome carrying no run id.
        journal_path=journal.path,
        incident=incident.scope,
    )
    journal.append(record=acceptance_pass.journal_record(work_item_id=item.id, policy=policy))
    # The pointer is written BEFORE any disposition branch, because every branch
    # is a possible end state for the item and the pointer is provenance of the
    # merge rather than of the verdict: an item that parks keeps the record its
    # pass read, and one that closes carries the pointer into `done`. A merge the
    # incident chain does not bind as its current carrier gets no pointer, and
    # neither close below may discharge an incident that still owes anything.
    decision = incident_decision(
        repo=repo,
        item=item,
        outcome=outcome,
        proof=acceptance_pass.proof,
        journal=journal,
        incident=incident,
        policy=policy,
    )
    if acceptance_pass.verdict == NEEDS_ATTENTION_VERDICT:
        # A cannot-judge verdict NEVER disposes, under EVERY acceptance_policy
        # including `ai-only`: the delegation `ai-only` grants is the authority
        # to act ON evidence, not the authority to act without it. So this
        # returns before the close / rework branches below — the item is not
        # accepted, not routed to rework, not stamped `rework:pending`, and
        # `acceptance_rework_cap` is not consumed. It parks for the human
        # `accept` / `reject` valves instead.
        park_in_acceptance(
            repo=repo,
            item_id=item.id,
            policy=decision.policy,
            acceptance_pass=acceptance_pass,
            outcome=outcome,
            journal=journal,
        )
        return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=False)
    if park_unreproduced_factory_captured and _proof_only_arm_did_not_reproduce_factory_assertion(
        acceptance_pass=acceptance_pass
    ):
        # A proof-only resume is evidence gathering after the item's merge, not
        # a new implementation attempt.  Its negative factory observation
        # therefore stays in acceptance under every policy: it neither changes
        # the item's status nor spends an acceptance rework attempt or starts a
        # fix stage.
        park_in_acceptance(
            repo=repo,
            item_id=item.id,
            policy=decision.policy,
            acceptance_pass=acceptance_pass,
            outcome=outcome,
            journal=journal,
        )
        return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=False)
    verdict = acceptance_pass.verdict
    if verdict == NO_CHANGE_NEEDED_VERDICT and decision.to_done:
        refused = claim.hold_for_close(intent="close-no-change-needed")
        if refused is not None:
            return AcceptanceDisposition(verdict=verdict, closed=False, refusal=refused)
        close_dispatch_item(
            repo=repo,
            item=item,
            outcome=outcome,
            resolution=_NO_CHANGE_NEEDED_RESOLUTION,
            reason=no_change_needed_reason(outcome=outcome),
            audit_merge=False,
        )
        journal.append(record={"stage": "ledger-accept-no-change-needed", "work_item_id": item.id})
        auto_disposition = auto_disposition_journal_record(
            work_item_id=item.id,
            disposition="ai-auto-no-change-needed",
            governing_settings=("acceptance_mode",),
        )
        auto_disposition["deferred"] = "pre-dispatch staleness detection"
        journal.append(record=auto_disposition)
        return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=True)
    if acceptance_pass.verdict == "FAIL" and policy in AI_DISPOSITIVE_ACCEPTANCE_POLICIES:
        # The merge sha is the dispatch's merge evidence: it is stamped only by
        # the post-merge janitor path off a resolved merged pull request, so its
        # presence is what tells the disposition whether re-implementing this
        # item could publish anything at all.
        rework_or_block_failed_acceptance(
            repo=repo,
            item=item,
            policy=policy,
            merged=outcome.merge_sha is not None,
            journal=journal,
        )
        return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=False)
    # A PASS carrying a PENDING LEG — host or human — rests the item in
    # `acceptance` "under any policy, `ai-only` included", so the legs are read
    # here from the ONE criteria primitive rather than from the pass's verdict:
    # the pass genuinely did PASS — its factory leg is green and the pending
    # assertions are listed as pending — and turning that into a non-PASS verdict
    # would report a healthy run as unjudgeable. For the human leg the host-side
    # wall already refuses `ai-only` before dispatch and this is the second gate,
    # for the item whose policy was edited after it; for the HOST leg this is the
    # ONLY gate, because `ai-only` is deliberately NOT refused for a host-captured
    # item — the host leg is agent-performable, so the item is admitted and rests
    # here instead.
    if (
        decision.to_done
        and acceptance_pass.verdict == "PASS"
        and not _pending_legs(item=item, acceptance_pass=acceptance_pass)
    ):
        refused = claim.hold_for_close(intent="close-completed")
        if refused is not None:
            return AcceptanceDisposition(verdict=verdict, closed=False, refusal=refused)
        close_dispatch_item(
            repo=repo,
            item=item,
            outcome=outcome,
            resolution="completed",
            reason=f"Fabro dispatch landed PR #{outcome.pr_number} ({outcome.detail})",
        )
        journal.append(record={"stage": "ledger-accept", "work_item_id": item.id})
        journal.append(
            record=auto_disposition_journal_record(
                work_item_id=item.id,
                disposition="ai-auto-accept",
                governing_settings=("acceptance_mode",),
            )
        )
        return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=True)
    park_in_acceptance(
        repo=repo,
        item_id=item.id,
        policy=decision.policy,
        acceptance_pass=acceptance_pass,
        outcome=outcome,
        journal=journal,
    )
    return AcceptanceDisposition(verdict=acceptance_pass.verdict, closed=False)


def _proof_only_arm_did_not_reproduce_factory_assertion(
    *, acceptance_pass: AcceptancePassResult
) -> bool:
    """Whether this re-accept read a negative factory result from the proof-only arm."""
    proof = acceptance_pass.proof
    if proof is None or proof.record is None or proof.record.verdict != VERDICT_NOT_REPRODUCED:
        return False
    return any(
        assertion.proof_mode == PROOF_MODE_FACTORY_CAPTURED
        and assertion.check is not None
        and not assertion.check.passed
        for assertion in proof.assertions
    )


def _pending_legs(*, item: WorkItem, acceptance_pass: AcceptancePassResult) -> tuple[str, ...]:
    """The assertions whose pending leg still holds this item in `acceptance`.

    Read off the PASS when it graded a proof leg, and off the item's declared criteria
    only when it did not. That distinction is what makes a host-captured item closeable
    at all: the declared set is a property of the Definition of Done and never retires, so
    reading it would hold such an item in `acceptance` for ever — on a verdict of PASS,
    with a verified host record sitting on its pull request, and with nothing in the
    record saying why. The pass's own set narrows as each leg is discharged: the host leg
    when an independent replay is judged evidence, and never the human leg, which the
    `accept` valve owns.

    The declared fallback is NOT dead: a legacy-source item declares no proof mode, so the
    pass builds no proof leg for it, and its pending set is correctly empty either way.
    Keeping the fallback means a future mode that the pass does not grade still parks.
    """
    if acceptance_pass.proof is None:
        return effective_criteria(item=item).pending_leg_assertions
    return (
        acceptance_pass.proof.pending_host_captured + acceptance_pass.proof.pending_human_attested
    )


def bounce_non_convergence_to_backlog(
    *, repo: Path, item: WorkItem, outcome: DispatchOutcome, journal: JournalFile
) -> None:
    """Bounce through the legacy seam so callers can observe its ledger write."""
    _bounce_non_convergence_to_backlog(
        repo=repo,
        item=item,
        outcome=outcome,
        journal=journal,
        store_config_resolver=store_config,
        status_writer=update_work_item_status,
    )


def warn_item_sizing(*, item: WorkItem, journal: JournalFile) -> None:
    """Emit the warn-only item-sizing heuristics at dispatch/loop-feed time.

    Heavy multi-part items have exceeded one unattended ACP turn (bn4
    shakedown evidence), so the Dispatcher flags suspicious sizes — one
    journal record plus one stderr WARN line per heuristic hit. Never
    blocking: the dispatch proceeds regardless.
    """
    warnings = item_sizing_warnings(item=item)
    if not warnings:
        return
    journal.append(
        record={
            "stage": "sizing-warn",
            "work_item_id": item.id,
            "warnings": list(warnings),
        }
    )
    for warning in warnings:
        _ = write_stderr(text=f"WARN: item-sizing {item.id}: {warning}\n")
