"""Publishing a budget-exceeded run's committed tree before its cancel.

`SPECIFICATION/contracts.md` section "Dispatcher progress watchdog" -> "The
whole-run wall budget": the preserve-by-reference pointer carries only stage
diff artifacts, which can be empty (78 bytes each) while the run's committed
tree is the only copy of hours of work (measured on bd-ib-yuwftp run
01M6KBH30NJA). So the cancel is released by a published tree, never by the
pointer alone.

THE BASE IS THE RUN'S STAGED COMMIT, read back off the dispatch journal with
`run_base_commit` (the newest `source-checkout-stage` row's `staged_at`), never
this host's head: the sandbox clones origin's head, which on a long drain is a
different commit, and a tree parented elsewhere folds every intervening change
of master into the run's work. A journal that cannot be read, or that names no
staging row, is the `base-commit` step failing -- reported as a failure the
caller HOLDS on, never papered over with a plausible commit.

The port is built as the checkpoint-failed disposition builds it: the factory
server's own HTTP face, because the run's changed files are served only there.
"""

from __future__ import annotations

from dataclasses import dataclass

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_file import JournalFile
from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_tail import (
    journal_tail_records,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_plan import DispatchPlan
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree import publish_run_tree
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_base import (
    run_base_commit,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port import FabroTarget
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    UrllibFabroHttpTransport,
)

__all__: list[str] = ["STEP_BASE_COMMIT", "STEP_FACTORY_SERVER", "BudgetPublisher"]

STEP_BASE_COMMIT = "base-commit"
STEP_FACTORY_SERVER = "factory-server"


@dataclass(frozen=True, kw_only=True)
class BudgetPublisher:
    """Publishes one run's committed tree, or names the step that failed."""

    def publish(
        self,
        *,
        plan: DispatchPlan,
        runner: CommandRunner,
        journal: object,
        run_id: str,
    ) -> PreservedTree | PublishFailure:
        """Read the run's files off its factory and publish them parented on its base."""
        if not isinstance(journal, JournalFile):
            return PublishFailure(
                step=STEP_BASE_COMMIT,
                detail=(
                    "the dispatch journal is not a readable file, so the commit the run's"
                    " sandbox was staged at could not be established"
                ),
            )
        base = run_base_commit(
            records=tuple(
                dict(record) for record in journal_tail_records(journal_path=journal.path)
            ),
            work_item_id=plan.work_item_id,
        )
        if base is None:
            return PublishFailure(
                step=STEP_BASE_COMMIT,
                detail=(
                    f"the dispatch journal holds no staged base commit for {plan.work_item_id},"
                    " so the preservation commit has no parent to name"
                ),
            )
        if plan.fabro_factory_server is None:
            return PublishFailure(
                step=STEP_FACTORY_SERVER,
                detail=(
                    "this dispatch's factory declares no server url to read the run's files from"
                ),
            )
        return publish_run_tree(
            port=FabroHttpPort(
                target=FabroTarget(server_url=plan.fabro_factory_server),
                transport=UrllibFabroHttpTransport(),
            ),
            runner=runner,
            repo=plan.repo,
            work_item_id=plan.work_item_id,
            run_id=run_id,
            base_commit=base,
        )
