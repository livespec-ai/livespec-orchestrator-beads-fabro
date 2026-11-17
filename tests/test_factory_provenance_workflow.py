"""Acceptance coverage for the label-sensitive factory-provenance workflow."""

from __future__ import annotations

from pathlib import Path

import yaml

_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_WORKFLOW = _REPOSITORY_ROOT / ".github" / "workflows" / "factory-provenance.yml"


def test_the_separate_factory_provenance_workflow_runs_the_existing_check() -> None:
    """The additive workflow has its own job that executes the provenance target."""
    assert _WORKFLOW.is_file(), f"expected the workflow at {_WORKFLOW}"

    document = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    jobs = document.get("jobs")
    assert isinstance(jobs, dict)
    job = jobs.get("factory-provenance")
    assert isinstance(job, dict)

    steps = job.get("steps")
    assert isinstance(steps, list)
    assert any(
        isinstance(step, dict) and step.get("run") == "just check-factory-provenance"
        for step in steps
    )
