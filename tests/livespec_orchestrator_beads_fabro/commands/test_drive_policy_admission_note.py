"""Coverage for committed-admission attribution on the policy valve."""

from __future__ import annotations

from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._drive_policy_admission_note import (
    committed_admission_setting_note,
)


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (True, " The committed dispatcher.auto_approve_ready=true decides the item's admission."),
        (False, " The committed dispatcher.auto_approve_ready=false decides the item's admission."),
        (None, ""),
    ],
)
def test_committed_admission_setting_note_names_only_explicit_values(
    tmp_path: Path, *, configured: bool | None, expected: str
) -> None:
    if configured is not None:
        _ = (tmp_path / ".livespec.jsonc").write_text(
            "{"
            '"livespec-orchestrator-beads-fabro": {"dispatcher": {'
            f'"auto_approve_ready": {str(configured).lower()}'
            "}}}",
            encoding="utf-8",
        )

    assert committed_admission_setting_note(repo=tmp_path) == expected
