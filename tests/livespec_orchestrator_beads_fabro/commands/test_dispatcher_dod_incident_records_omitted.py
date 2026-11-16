"""The incident chain's own ledger records are receipts, not operator brief.

`SPECIFICATION/scenarios.md` Scenario 239 ("Every taking of the
Definition-of-Done judgement grades one subject by one rubric"): the subject
carries every operator rider and no receipt. An expedited incident writes its
own machine records onto the canonical item (`livespec-incident-entry-v1`,
`livespec-incident-authority-v1`, `livespec-incident-local-gates-v1`,
`livespec-incident-pr-run-record-v1`). Carried as riders, eleven local-gates
records alone put bd-ib-r4xzme's repayment subject past the dod-preflight input
bound (bd-ib-ikmfr4), so every incident repayment refused on input size.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _dispatcher_dod_judgement as judgement
from livespec_orchestrator_beads_fabro.commands import _dispatcher_goal as goal
from livespec_orchestrator_beads_fabro.store import WorkItemComment
from livespec_orchestrator_beads_fabro.types import WorkItem

_PAYLOAD = '{"attempt":{"attempt_id":"repair-INCIDENT-PAYLOAD"},"schema":1}'
_ENTRY = "livespec-incident-entry-v1\n" + _PAYLOAD
_AUTHORITY = "livespec-incident-authority-v1\n" + _PAYLOAD
_LOCAL_GATES = "livespec-incident-local-gates-v1\n" + _PAYLOAD
_PR_RUN = "livespec-incident-pr-run-record-v1\n" + _PAYLOAD
_RIDER = "Rider: RIDER-BESIDE-INCIDENT narrows the first assertion."


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-ikmfr4",
        type="bug",
        status="pending-approval",
        title="An incident record is not brief",
        description=(
            "## Definition of Done\n\n"
            "- The judgement runs before an item moves to ready.\n\n"
            "References: ## Scenario 174 — The judgement runs before admission\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-15T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


@pytest.mark.parametrize("record", [_ENTRY, _AUTHORITY, _LOCAL_GATES, _PR_RUN])
def test_subject_and_goal_omit_the_incident_record_and_keep_the_rider(
    record: str, tmp_path: Path
) -> None:
    item = _item()
    with_record = (record, _RIDER, record)

    subject = judgement.judgement_subject(item=item, cwd=tmp_path, comments=with_record)
    rendered = goal.render_goal(
        item=item,
        repo=tmp_path,
        branch="feat/bd-ib-ikmfr4",
        comments=tuple(
            WorkItemComment(text=text, author=None, created_at=None) for text in with_record
        ),
    )

    assert "RIDER-BESIDE-INCIDENT" in subject
    assert "RIDER-BESIDE-INCIDENT" in rendered
    assert "INCIDENT-PAYLOAD" not in subject + rendered
    assert judgement.judgement_subject_digest(
        item=item, cwd=tmp_path, comments=with_record
    ) == judgement.judgement_subject_digest(item=item, cwd=tmp_path, comments=(_RIDER,))


def test_eleven_local_gates_records_leave_the_subject_its_rider_sized_length(
    tmp_path: Path,
) -> None:
    item = _item()
    bulky = "livespec-incident-local-gates-v1\n" + "x" * 23_000
    comments = (*(bulky,) * 11, _RIDER)

    subject = judgement.judgement_subject(item=item, cwd=tmp_path, comments=comments)
    rider_only = judgement.judgement_subject(item=item, cwd=tmp_path, comments=(_RIDER,))

    assert len(subject) == len(rider_only)


@pytest.mark.parametrize(
    "prose",
    [
        "livespec-incident-mode looks wrong here: RIDER-NAMING-THE-PREFIX.",
        "Operator note: the livespec-incident-local-gates-v1 record above is stale."
        " RIDER-NAMING-THE-PREFIX",
    ],
)
def test_a_comment_that_only_names_an_incident_marker_stays_a_rider(
    prose: str, tmp_path: Path
) -> None:
    subject = judgement.judgement_subject(item=_item(), cwd=tmp_path, comments=(prose,))

    assert "RIDER-NAMING-THE-PREFIX" in subject
