"""The planned factory Claude slot pool has one fleet-owned declaration.

The proposal is the design record for bd-ib-mns3md.  It must choose a source
that every dispatcher reads, distinguish the existing central per-admission
selection from the declared pool, reject generated per-repository copies, and
name both the spec-change route and the migration of the committed tuple pin.
"""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_PROPOSAL = _REPO_ROOT / "SPECIFICATION/proposed_changes/fleet-declared-factory-slot-pool.md"


def test_the_slot_pool_single_source_proposal_records_the_required_design() -> None:
    assert _PROPOSAL.is_file(), (
        "bd-ib-mns3md needs a proposed change that records the fleet-owned "
        "factory Claude slot-pool design"
    )

    proposal = _PROPOSAL.read_text(encoding="utf-8")

    for required in (
        "## Candidate designs",
        "fleet-level declaration",
        "central-factory-selection carrying the pool",
        "generated per-repository file",
        "## Chosen design",
        "## Dispatcher policy settings",
        "## Tier and follow-on work",
        "spec-change tier",
        "## Delivery and test migration",
        "all ten repositories",
        "literal-tuple pin test",
    ):
        assert required in proposal
