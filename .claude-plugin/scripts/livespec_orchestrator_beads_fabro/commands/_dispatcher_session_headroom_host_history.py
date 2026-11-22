"""The host-shared history that lets fresh checkouts project session headroom.

The dispatch journal remains the first source for a drain-rate baseline: it is
the audit trail for the checkout doing the dispatch.  A host can have several
such checkouts, though, and a newly created one has no useful prior until its
second assessment.  This small, per-user JSONL history carries the same
non-secret assessment facts across those checkouts, keyed only by the opaque
credential identity.

Malformed *lines* are tolerated just as they are in the dispatch journal -- a
concurrent append can expose a torn tail.  A history which cannot be opened or
is not a regular file is different: that is an unavailable projection input and
is returned explicitly so the caller can journal the reason while failing open.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._acp_session_headroom import (
    SessionHeadroomReading,
)
from livespec_orchestrator_beads_fabro.commands._acp_session_headroom_drain import (
    SessionHeadroomBaseline,
    SessionHeadroomPriorReading,
    baseline_assessment,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_paths import state_root

__all__: list[str] = [
    "HOST_HISTORY_UNREADABLE_REASON",
    "HostSessionHeadroomHistory",
    "append_host_session_headroom_history",
    "host_session_headroom_baseline",
    "host_session_headroom_history_path",
]

HOST_HISTORY_UNREADABLE_REASON = "host-history-unreadable"
_HISTORY_DIRECTORY = "livespec-orchestrator-beads-fabro"
_HISTORY_FILENAME = "session-headroom-history.jsonl"


@dataclass(frozen=True, kw_only=True)
class HostSessionHeadroomHistory:
    """One host-history lookup's baseline or its explicit read failure."""

    baseline: SessionHeadroomBaseline | None
    unavailable_reason: str | None = None


def host_session_headroom_history_path() -> Path:
    """The one per-user, host-shared history location."""
    return state_root() / _HISTORY_DIRECTORY / _HISTORY_FILENAME


def append_host_session_headroom_history(
    *, assessments: tuple[SessionHeadroomReading, ...], repo: Path | None = None
) -> None:
    """Append every journaled assessment to the host history.

    This deliberately tolerates an unavailable history.  Admission has already
    made its decision by the time it journals, and a later inability to extend
    the optional cross-checkout baseline must not turn a fail-open projection
    into a dispatch failure.  The next assessment will report the same
    unavailability explicitly when it tries to read this file.
    """
    if not assessments:
        return
    path = host_session_headroom_history_path()
    checkout = None if repo is None else str(repo.resolve())
    repository = None if repo is None else repo.name
    lines = tuple(
        json.dumps(
            {
                "credential_identity": reading.credential_identity,
                "utilization_percent": reading.utilization_percent,
                "observed_at": reading.observed_at,
                "five_hour_drain_percent_per_hour": reading.five_hour_drain_percent_per_hour,
                "repository": repository,
                "checkout": checkout,
            },
            sort_keys=True,
        ).encode("utf-8")
        + b"\n"
        for reading in assessments
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            for line in lines:
                _ = os.write(descriptor, line)
        finally:
            os.close(descriptor)
    except OSError:
        return


def host_session_headroom_baseline(
    *, credential_identity: str, now_iso: str
) -> HostSessionHeadroomHistory:
    """Read the host fallback for one credential, without treating absence as error."""
    path = host_session_headroom_history_path()
    try:
        status = path.stat()
    except FileNotFoundError:
        return HostSessionHeadroomHistory(baseline=None)
    except OSError:
        return HostSessionHeadroomHistory(
            baseline=_unavailable_baseline(), unavailable_reason=HOST_HISTORY_UNREADABLE_REASON
        )
    try:
        if not stat.S_ISREG(status.st_mode):
            return HostSessionHeadroomHistory(
                baseline=_unavailable_baseline(), unavailable_reason=HOST_HISTORY_UNREADABLE_REASON
            )
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return HostSessionHeadroomHistory(
            baseline=_unavailable_baseline(), unavailable_reason=HOST_HISTORY_UNREADABLE_REASON
        )
    records = _records(text=text)
    reading_pair = baseline_assessment(
        priors=_reading_priors(records=records, credential_identity=credential_identity),
        now_iso=now_iso,
    )
    if reading_pair is not None:
        return HostSessionHeadroomHistory(baseline=reading_pair)
    carried = _carried_drain_baseline(
        records=records, credential_identity=credential_identity, now_iso=now_iso
    )
    return HostSessionHeadroomHistory(baseline=carried)


def _records(*, text: str) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    for line in text.splitlines():
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(cast("dict[str, object]", parsed))
    return tuple(records)


def _reading_priors(
    *, records: tuple[dict[str, object], ...], credential_identity: str
) -> tuple[SessionHeadroomPriorReading, ...]:
    priors: list[SessionHeadroomPriorReading] = []
    for record in records:
        prior = _prior(record=record, credential_identity=credential_identity)
        if prior is not None:
            priors.append(prior)
    return tuple(priors)


def _prior(
    *, record: dict[str, object], credential_identity: str
) -> SessionHeadroomPriorReading | None:
    if record.get("credential_identity") != credential_identity:
        return None
    utilization = record.get("utilization_percent")
    observed_at = record.get("observed_at")
    if isinstance(utilization, bool) or not isinstance(utilization, int | float):
        return None
    if not isinstance(observed_at, str):
        return None
    return SessionHeadroomPriorReading(
        utilization_percent=float(utilization), observed_at=observed_at
    )


def _carried_drain_baseline(
    *, records: tuple[dict[str, object], ...], credential_identity: str, now_iso: str
) -> SessionHeadroomBaseline | None:
    carried: list[tuple[SessionHeadroomPriorReading, float]] = []
    for record in records:
        if record.get("credential_identity") != credential_identity:
            continue
        observed_at = record.get("observed_at")
        rate = record.get("five_hour_drain_percent_per_hour")
        if not isinstance(observed_at, str):
            continue
        if isinstance(rate, bool) or not isinstance(rate, int | float) or rate <= 0:
            continue
        carried.append(
            (
                SessionHeadroomPriorReading(utilization_percent=0.0, observed_at=observed_at),
                float(rate),
            )
        )
    if not carried:
        return None
    candidates = baseline_assessment(
        priors=tuple(prior for prior, _rate in carried), now_iso=now_iso
    )
    if candidates is None:
        return None
    rate = next(rate for prior, rate in carried if prior.observed_at == candidates.observed_at)
    return SessionHeadroomBaseline(
        utilization_percent=candidates.utilization_percent,
        observed_at=candidates.observed_at,
        elapsed_hours=candidates.elapsed_hours,
        carried_drain_percent_per_hour=rate,
    )


def _unavailable_baseline() -> SessionHeadroomBaseline:
    """A marker consumed by the projection without inventing a drain rate."""
    return SessionHeadroomBaseline(
        utilization_percent=0.0,
        observed_at="",
        elapsed_hours=0.0,
        unavailable_reason=HOST_HISTORY_UNREADABLE_REASON,
    )
