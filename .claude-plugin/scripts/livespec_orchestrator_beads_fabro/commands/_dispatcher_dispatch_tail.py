"""Everything one single-item dispatch does AFTER its outcome is known.

Split out of `_dispatcher_run_commands` when the ratified `resume --item` surface
became the second caller. That clause requires a resume to "journal exactly as a
dispatch does -- including the fail-closed cost-gate record, under the hand-picked
posture", and its outcome to map "to the Dispatcher exit codes as a
`dispatch --item` outcome does". Both are properties of this sequence, so the
sequence is shared rather than copied: a copy makes "both paths journal the same"
a claim about two sequences that can drift, and it requires every future
post-verdict stage to be wired twice. It is the post-verdict half of the argument
`_dispatcher_pre_dispatch_wall` makes for the pre-dispatch half.

THE ORDER IS LOAD-BEARING. The verdict is computed BEFORE the alarm, the cost
gate, the self-update, the reflection and the out-of-band reflector, and is
immutable by all five (loop-reflection-gate best-practices section 6). Those five
are fail-open by design -- a probe error is journaled and swallowed rather than
raised -- so a tail that computed the verdict afterwards would let a best-effort
notification change a dispatch verdict. In the green case both orderings return
the same code, which is why `test_dispatcher_dispatch_tail` pins the ORDER as a
recorded call sequence rather than only the returned code.

THE JOURNAL PATH IS RESOLVED ONCE AND PASSED TWICE. `append_run_turn_checks` and
`reflect` both write beside the dispatch journal, and two resolutions of one path
is how they would come to write beside different ones.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_command_common import (
    alarm_on_terminal_failure,
    dispatch_exit_code,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cost_gate import (
    cost_gate_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import DispatchOutcome
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_ledger_close import emit_outcomes
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import (
    journal_path,
    run_turn_sink_path,
    spans_path,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_post_verdict import (
    reflector_oob_after_verdict,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_reflection import reflect
from livespec_orchestrator_beads_fabro.commands._dispatcher_reconcile_merged import (
    run_reconcile_merged_command,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_guard import (
    append_run_turn_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_run_turn_sink import RunTurnSink
from livespec_orchestrator_beads_fabro.commands._dispatcher_self_update import (
    post_verdict_runner,
    self_update_after_verdict,
)

__all__: list[str] = [
    "dispatch_tail_exit",
]


def dispatch_tail_exit(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> int:
    """Emit, grade, and run every fail-open post-verdict stage; return the verdict."""
    outcomes = [outcome]
    emit_outcomes(outcomes=outcomes, as_json=args.as_json)
    # Verdict computed BEFORE the fail-open reflection + notification stages;
    # immutable by both (loop-reflection-gate best-practices section 6 / 0jxs
    # operability gate). The alarm is strictly best-effort.
    exit_code = dispatch_exit_code(outcomes=outcomes)
    alarm_on_terminal_failure(
        outcomes=outcomes,
        include_loop_summary=False,
        journal=journal,
    )
    cost_gate_after_verdict(
        args=args,
        repo=repo,
        outcomes=outcomes,
        journal=journal,
        runner=post_verdict_runner(runner=None),
    )
    self_update_after_verdict(
        repo=repo,
        outcomes=outcomes,
        journal=journal,
        runner=post_verdict_runner(runner=None),
    )
    dispatch_journal_path = journal_path(args=args, repo=repo)
    append_run_turn_checks(
        outcomes=(outcome,),
        journal=journal,
        journal_path=dispatch_journal_path,
        repo=repo,
        sink=RunTurnSink(path=run_turn_sink_path(args=args, repo=repo)),
    )
    reflect(
        outcomes=outcomes,
        journal=journal,
        journal_path=dispatch_journal_path,
        spans_path=spans_path(args=args, repo=repo),
    )
    reflector_oob_after_verdict(args=args, repo=repo, journal=journal)
    if (
        getattr(args, "resume_proof_only", False)
        and outcome.status == "green"
        and outcome.stage == "done"
    ):
        reconcile_proof_only_acceptance(args=args, repo=repo, outcome=outcome, journal=journal)
    return exit_code


def reconcile_proof_only_acceptance(
    *,
    args: argparse.Namespace,
    repo: Path,
    outcome: DispatchOutcome,
    journal: JournalFile,
) -> None:
    """Re-run acceptance after a completed proof-only arm has published its record.

    The arm's proof stages have ended before this tail reaches the call, so the
    re-accept arm reads the newly published `proof_verify` record through the
    ordinary acceptance reader and writes its pointer from that same read.  The
    originating dispatch lock is still held while its tail runs, which is why
    this internal, serialized invocation carries `force` rather than being
    refused as though it were an unrelated operator recovery.
    """
    reconcile_args = argparse.Namespace(
        repo=str(repo),
        item=outcome.work_item_id,
        janitor=None,
        journal=str(journal.path),
        invoker=getattr(args, "invoker", None),
        force=True,
        regrade=False,
        as_json=getattr(args, "as_json", False),
        pr=outcome.pr_number,
        proof_only_reaccept=True,
    )
    _ = run_reconcile_merged_command(args=reconcile_args)
