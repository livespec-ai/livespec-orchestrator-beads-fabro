"""Read the newest spec-change-tier record that still stands for an item.

The Definition-of-Done judgement must apply check 4's internal-ruling exception
from the same current-record rule as the classifier.  It needs that read without
taking a classification or appending a record, so this leaf repeats only the
deterministic reuse inputs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from livespec_orchestrator_beads_fabro.commands._spec_change_tier import (
    SPEC_DIRNAME,
    asked_for_behaviour,
    behaviour_digest,
)
from livespec_orchestrator_beads_fabro.commands._spec_change_tier_record import (
    RecordedSpecChangeTier,
    reusable_spec_change_tier,
)
from livespec_orchestrator_beads_fabro.commands._spec_stated_citation import judged_prompt_ceiling
from livespec_orchestrator_beads_fabro.commands._spec_tree_condensation import (
    PROMPT_CHARACTER_CEILING,
    condensed_spec_tree,
)
from livespec_orchestrator_beads_fabro.effects import AttemptFailure, attempt
from livespec_orchestrator_beads_fabro.spec_reader import read_current_specification

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = ["current_spec_change_tier"]


def current_spec_change_tier(
    *, item: WorkItem, repo: Path, comments: Sequence[str]
) -> RecordedSpecChangeTier | None:
    """Return the newest record reusable against the current behaviour and spec tree."""
    read = attempt(
        action=lambda: read_current_specification(spec_root=repo / SPEC_DIRNAME),
        exceptions=(OSError,),
    )
    if isinstance(read, AttemptFailure) or not read.files:
        return None
    selected_clauses = tuple(
        clause
        for clause in condensed_spec_tree(
            spec_tree=read.files,
            statement=asked_for_behaviour(item=item),
            ceiling=judged_prompt_ceiling(spec_tree=read.files, ceiling=PROMPT_CHARACTER_CEILING),
        ).clauses
        if clause.heading
    )
    return reusable_spec_change_tier(
        comments=comments,
        digest=behaviour_digest(item=item),
        selected_clauses=selected_clauses,
        spec_tree=read.files,
    )
