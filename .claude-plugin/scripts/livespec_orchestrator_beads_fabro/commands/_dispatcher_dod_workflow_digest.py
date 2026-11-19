"""The committed workflow-graph input to a Definition-of-Done taking.

The host screen and the in-run gate both grade the graph that will execute the
item.  A verdict taken before that graph changes is therefore not a verdict on
the current execution plan, even when the item's prose and the DoD prompt have
not changed.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_criteria_wall_variant import (
    criteria_wall_variant,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_overlay import workflow_graph_path
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import workflow_toml
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt

__all__ = ["UNREADABLE_WORKFLOW_GRAPH_DIGEST", "workflow_graph_digest"]

UNREADABLE_WORKFLOW_GRAPH_DIGEST = "unreadable"


def workflow_graph_digest(*, repo: Path, item_id: str, workflow_name: str | None = None) -> str:
    """Digest the graph the pre-ticket screen resolved for this item.

    The unreadable sentinel deliberately cannot compare equal to an old receipt:
    a screen unable to establish the graph must take (or refuse for lack of) a
    fresh judgement rather than bless an unknown graph from a stale record.
    """
    variant = criteria_wall_variant(repo=repo, work_item_id=item_id, workflow_name=workflow_name)
    manifest = workflow_toml(
        args=argparse.Namespace(workflow=None, repo=str(repo)),
        variant_directory=variant.directory,
    )
    committed = attempt(
        action=lambda: manifest.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeDecodeError),
    )
    if isinstance(committed, AttemptFailure):
        return UNREADABLE_WORKFLOW_GRAPH_DIGEST
    graph = workflow_graph_path(committed_text=committed, workflow_dir=manifest.parent)
    if graph is None:
        return UNREADABLE_WORKFLOW_GRAPH_DIGEST
    contents = attempt(action=graph.read_bytes, exceptions=(OSError,))
    if isinstance(contents, AttemptFailure):
        return UNREADABLE_WORKFLOW_GRAPH_DIGEST
    return hashlib.sha256(contents).hexdigest()
