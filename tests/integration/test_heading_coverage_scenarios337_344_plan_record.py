"""The three completed slices are bound to integration journeys, never TODO rows.

The exercising journeys live beside the production seams they drive.  This
small registry assertion keeps the coverage registry and its generated debt
register honest: a closed implementation item does not become evidence until
the scenario heading names an integration-tier test that exercises it.
"""

from __future__ import annotations

import json
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXPECTED_TESTS = {
    "## Scenario 337 — A merged rework re-dispatch whose merge wait was handed off is completed by reconciliation, and a parked rework stays unsurveyed": (
        "tests.integration.test_reconcile_handed_off_rework_scenario337"
        ".test_scenario337_reconciles_merged_handoffs_holds_open_ones_and_skips_parked_reworks"
    ),
    "## Scenario 344 — An item classified bug whose asked-for behaviour the spec does not state waits for ratification, and classify-tier re-judges a changed item": (
        "tests.integration.test_spec_change_tier_scenario344"
        ".test_scenario344_routes_unstated_behaviour_by_classification_and_rejudges_changed_items"
    ),
    "## Scenario: the plan record posting primitive renders a record's artifact paths line": (
        "tests.integration.test_plan_record_artifact_paths_scenario"
        ".test_plan_record_artifact_paths_render_omit_and_refuse_before_posting"
    ),
}


def test_the_completed_scenario_rows_name_their_integration_journeys_and_leave_no_debt() -> None:
    """Closed owners are replaced by executable integration evidence."""
    coverage = json.loads((_REPO_ROOT / "tests" / "heading-coverage.json").read_text())
    debt = json.loads((_REPO_ROOT / "tests" / "heading-coverage-debt.json").read_text())
    rows = {row["heading"]: row["test"] for row in coverage if row["heading"] in _EXPECTED_TESTS}
    debt_headings = {str(row["heading"]) for row in debt if row["heading"] in _EXPECTED_TESTS}

    assert rows == _EXPECTED_TESTS
    assert debt_headings == set()
