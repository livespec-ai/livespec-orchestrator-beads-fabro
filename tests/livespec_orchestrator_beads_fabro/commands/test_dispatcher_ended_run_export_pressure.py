"""The disk-pressure reading the ended-run export waits on (bd-ib-cvilnl).

Every figure is reached through the module's named constants, so the thresholds
stay operator-tunable code constants and no test pins what they are.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import NamedTuple

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_ended_run_export import (
    EXPORT_CEILING_BYTES,
    EXPORT_FREE_SPACE_MULTIPLE,
    EXPORT_RETENTION_SECONDS,
    MIN_FREE_BYTES,
    MIN_FREE_FRACTION,
    disk_pressure,
)


class _Usage(NamedTuple):
    total: int
    used: int
    free: int


def _threshold(*, total: int) -> int:
    return max(int(total * MIN_FREE_FRACTION), MIN_FREE_BYTES)


def _disk(monkeypatch: pytest.MonkeyPatch, *, total: int, free: int) -> list[Path]:
    seen: list[Path] = []

    def usage(path: Path) -> _Usage:
        seen.append(Path(path))
        return _Usage(total, total - free, free)

    monkeypatch.setattr(shutil, "disk_usage", usage)
    return seen


def test_the_free_space_floor_is_a_multiple_of_the_per_export_ceiling() -> None:
    assert MIN_FREE_BYTES == EXPORT_CEILING_BYTES * EXPORT_FREE_SPACE_MULTIPLE
    assert EXPORT_RETENTION_SECONDS > 0


def test_free_space_one_byte_under_the_floor_is_pressure_on_a_small_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    total = 10 * MIN_FREE_BYTES
    _ = _disk(monkeypatch, total=total, free=_threshold(total=total) - 1)

    pressure = disk_pressure(repo=tmp_path)

    assert pressure is not None
    assert (pressure.free_bytes, pressure.total_bytes) == (_threshold(total=total) - 1, total)
    assert (pressure.min_free_fraction, pressure.min_free_bytes) == (
        MIN_FREE_FRACTION,
        MIN_FREE_BYTES,
    )


def test_free_space_at_the_floor_is_not_pressure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    total = 10 * MIN_FREE_BYTES
    _ = _disk(monkeypatch, total=total, free=_threshold(total=total))

    assert disk_pressure(repo=tmp_path) is None


def test_the_fraction_governs_on_a_filesystem_large_enough_that_it_exceeds_the_byte_floor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    total = int(MIN_FREE_BYTES / MIN_FREE_FRACTION) * 10
    assert _threshold(total=total) > MIN_FREE_BYTES
    _ = _disk(monkeypatch, total=total, free=_threshold(total=total) - 1)

    assert disk_pressure(repo=tmp_path) is not None


def test_the_reading_is_taken_on_the_nearest_existing_ancestor_of_the_export_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = _disk(monkeypatch, total=10 * MIN_FREE_BYTES, free=10 * MIN_FREE_BYTES)

    assert disk_pressure(repo=tmp_path) is None
    assert seen == [tmp_path]


def test_an_unreadable_filesystem_is_not_pressure_so_the_export_is_attempted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_path: Path) -> _Usage:
        raise OSError("statvfs refused")

    monkeypatch.setattr(shutil, "disk_usage", refuse)

    assert disk_pressure(repo=tmp_path) is None
