"""The bypass launcher applies admission's weekly reserve before it probes."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_credential_env as credential_env,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_gate as headroom_gate,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_claude_credential import (
    ClaudeCredentialStatus,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_factory_account_selector import (
    register_admission_slot_chooser,
)

_PLUGIN = "livespec-orchestrator-beads-fabro"
_SLOT = "CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4"


@pytest.fixture(autouse=True)
def _clear_admission_slot_chooser() -> None:
    register_admission_slot_chooser(chooser=None)
    yield
    register_admission_slot_chooser(chooser=None)


def _usable_status() -> ClaudeCredentialStatus:
    return ClaudeCredentialStatus(
        condition="usable",
        present=True,
        usable=True,
        http_status=200,
        error_type=None,
        input_tokens=None,
        output_tokens=None,
        message="usable",
        remedy="none",
    )


@pytest.mark.parametrize(
    ("weekly_floor", "seven_day"),
    [
        (10, headroom.seven_day_reading(utilization=90, status="allowed_warning")),
        (10, headroom.UNOBSERVABLE_SEVEN_DAY),
        (0, headroom.seven_day_reading(utilization=95, status="allowed_warning")),
    ],
    ids=("equal-to-reserve", "weekly-utilization-absent", "reserve-disabled"),
)
def test_a_bypass_launcher_keeps_non_skipped_weekly_reserve_cases(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    weekly_floor: int,
    seven_day: headroom.SevenDayReading,
) -> None:
    """Equality, an absent reading, and a zero reserve all continue to the probe."""
    config = {
        _PLUGIN: {
            "dispatcher": {
                "claude_credential_policy": {"mode": "numbered-slots", "slots": [_SLOT]},
                "session_headroom_weekly_floor_percent": weekly_floor,
            }
        }
    }
    (tmp_path / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv(_SLOT, "token-4")
    real_policy = headroom_gate.session_headroom_policy

    def _policy(**kwargs: Any) -> headroom.SessionHeadroomPolicy:
        def _read(*, token: str | None, observed_at: str) -> headroom.SessionHeadroomReading:
            return headroom.session_headroom_reading(
                credential_identity=f"id-{token}",
                observed_at=observed_at,
                utilization=5,
                seven_day=seven_day,
            )

        return real_policy(read=_read, **kwargs)

    monkeypatch.setattr(headroom_gate, "session_headroom_policy", _policy)
    probes: list[str] = []

    def _probe(*, token: str) -> ClaudeCredentialStatus:
        probes.append(token)
        return _usable_status()

    checked = credential_env.checked_credential_env(repo=tmp_path, probe=_probe)

    assert checked == credential_env.CheckedCredentialEnv(env_name=_SLOT)
    assert probes == ["token-4"]
