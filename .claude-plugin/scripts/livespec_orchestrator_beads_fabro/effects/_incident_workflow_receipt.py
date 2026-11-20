"""Workflow receipt transition helpers."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro._incident_authority_types import AuthorityRefusal, IncidentAttempt, IncidentReading


def attested_successor(*, observed: IncidentReading, receipt: object) -> IncidentAttempt | AuthorityRefusal:
    """Temporary Red stub for the receipt successor builder."""
    _ = observed, receipt
    return AuthorityRefusal(code="incident-workflow-attestation-invalid", detail="stub")
