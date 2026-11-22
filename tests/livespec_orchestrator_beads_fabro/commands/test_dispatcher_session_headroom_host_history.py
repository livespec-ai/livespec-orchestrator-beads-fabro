"""The per-user session-headroom history shared by host checkouts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom as headroom
from livespec_orchestrator_beads_fabro.commands import _acp_session_headroom_drain as drain
from livespec_orchestrator_beads_fabro.commands import (
    _acp_session_headroom_projection as projection,
)
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_host_history as history,
)

_NOW = "2026-10-16T12:00:00Z"
_EARLIER = "2026-10-16T11:30:00Z"
_IDENTITY = "cred-1"


@pytest.fixture
def history_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep the host-wide store local to the test that exercises it."""
    path = tmp_path / "state" / "session-headroom-history.jsonl"
    monkeypatch.setattr(history, "host_session_headroom_history_path", lambda: path)
    return path


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "credential_identity": _IDENTITY,
        "utilization_percent": 10.0,
        "observed_at": _EARLIER,
        "five_hour_drain_percent_per_hour": None,
    }
    record.update(overrides)
    return record


def _reading() -> headroom.SessionHeadroomReading:
    return headroom.SessionHeadroomReading(
        credential_identity=_IDENTITY,
        observed_at=_NOW,
        utilization_percent=50.0,
        remaining_percent=50.0,
    )


def test_path_uses_the_shared_dispatcher_state_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

    assert history.host_session_headroom_history_path() == (
        tmp_path / "state" / "livespec-orchestrator-beads-fabro" / "session-headroom-history.jsonl"
    )


def test_append_mirrors_a_journaled_assessment_and_reads_a_pair_baseline(
    history_path: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "checkout"
    repo.mkdir()

    history.append_host_session_headroom_history(assessments=(_reading(),), repo=repo)

    (record,) = [json.loads(line) for line in history_path.read_text().splitlines()]
    assert record == {
        "checkout": str(repo.resolve()),
        "credential_identity": _IDENTITY,
        "five_hour_drain_percent_per_hour": None,
        "observed_at": _NOW,
        "repository": "checkout",
        "utilization_percent": 50.0,
    }
    resolved = history.host_session_headroom_baseline(
        credential_identity=_IDENTITY, now_iso="2026-10-16T12:30:00Z"
    )
    assert resolved.baseline is not None
    assert resolved.baseline.utilization_percent == 50.0


def test_absent_history_and_empty_assessments_hold_no_baseline(history_path: Path) -> None:
    history.append_host_session_headroom_history(assessments=())

    assert not history_path.exists()
    assert (
        history.host_session_headroom_baseline(credential_identity=_IDENTITY, now_iso=_NOW).baseline
        is None
    )


def test_torn_and_invalid_records_are_ignored_without_hiding_a_valid_sibling(
    history_path: Path,
) -> None:
    history_path.parent.mkdir(parents=True)
    _ = history_path.write_text(
        "\n".join(
            (
                "{torn",
                json.dumps([]),
                json.dumps(_record(credential_identity="other")),
                json.dumps(_record(utilization_percent=True)),
                json.dumps(_record(observed_at=1)),
                json.dumps(_record()),
            )
        ),
        encoding="utf-8",
    )

    baseline = history.host_session_headroom_baseline(
        credential_identity=_IDENTITY, now_iso=_NOW
    ).baseline

    assert baseline is not None
    assert baseline.observed_at == _EARLIER


def test_carried_rate_is_used_when_no_reading_pair_baseline_exists(history_path: Path) -> None:
    history_path.parent.mkdir(parents=True)
    _ = history_path.write_text(
        json.dumps(_record(utilization_percent=None, five_hour_drain_percent_per_hour=40.0)),
        encoding="utf-8",
    )

    baseline = history.host_session_headroom_baseline(
        credential_identity=_IDENTITY, now_iso=_NOW
    ).baseline

    assert baseline is not None
    assert baseline.carried_drain_percent_per_hour == 40.0
    rated = drain.reading_with_drain_rate(reading=_reading(), baseline=baseline)
    assert rated.five_hour_drain_percent_per_hour == 40.0


@pytest.mark.parametrize(
    "record",
    [
        (_record(five_hour_drain_percent_per_hour=True),),
        (_record(five_hour_drain_percent_per_hour=0.0),),
        (_record(five_hour_drain_percent_per_hour="40"),),
        (_record(observed_at=None, five_hour_drain_percent_per_hour=40.0),),
    ],
)
def test_invalid_carried_rates_do_not_become_a_baseline(
    history_path: Path, record: dict[str, object]
) -> None:
    history_path.parent.mkdir(parents=True)
    _ = history_path.write_text(json.dumps(record), encoding="utf-8")

    assert (
        history.host_session_headroom_baseline(credential_identity=_IDENTITY, now_iso=_NOW).baseline
        is None
    )


def test_a_directory_history_is_an_explicit_unavailable_projection_input(
    history_path: Path,
) -> None:
    history_path.mkdir(parents=True)

    resolved = history.host_session_headroom_baseline(credential_identity=_IDENTITY, now_iso=_NOW)

    assert resolved.unavailable_reason == history.HOST_HISTORY_UNREADABLE_REASON
    assert resolved.baseline is not None
    assert resolved.baseline.unavailable_reason == history.HOST_HISTORY_UNREADABLE_REASON
    history.append_host_session_headroom_history(assessments=(_reading(),))
    assert (
        drain.reading_with_drain_rate(reading=_reading(), baseline=resolved.baseline) == _reading()
    )
    unavailable = projection.session_headroom_projection(
        reading=_reading(), baseline=resolved.baseline, floor_percent=20, horizon_minutes=180
    )
    assert unavailable.reason == history.HOST_HISTORY_UNREADABLE_REASON


def test_an_unreadable_history_is_reported_and_an_unwritable_append_is_tolerated(
    history_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    history_path.parent.mkdir(parents=True)
    _ = history_path.write_text(json.dumps(_record()), encoding="utf-8")
    monkeypatch.setattr(
        Path, "read_text", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError())
    )

    resolved = history.host_session_headroom_baseline(credential_identity=_IDENTITY, now_iso=_NOW)

    assert resolved.unavailable_reason == history.HOST_HISTORY_UNREADABLE_REASON
    history.append_host_session_headroom_history(assessments=(_reading(),))


def test_a_stat_failure_is_an_unreadable_history(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "stat", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError()))

    resolved = history.host_session_headroom_baseline(credential_identity=_IDENTITY, now_iso=_NOW)

    assert resolved.unavailable_reason == history.HOST_HISTORY_UNREADABLE_REASON


def test_carried_history_ignores_other_credentials_and_entries_outside_the_window(
    history_path: Path,
) -> None:
    records = (
        _record(credential_identity="other", five_hour_drain_percent_per_hour=40.0),
        _record(observed_at="2026-10-16T10:00:00Z", five_hour_drain_percent_per_hour=40.0),
        _record(observed_at=None, five_hour_drain_percent_per_hour=40.0),
    )

    history_path.parent.mkdir(parents=True)
    _ = history_path.write_text("\n".join(json.dumps(record) for record in records))

    assert (
        history.host_session_headroom_baseline(credential_identity=_IDENTITY, now_iso=_NOW).baseline
        is None
    )
