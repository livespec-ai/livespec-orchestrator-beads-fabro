"""Fall-through and wiring edges of the shared `bd list` dump cache (bd-ib-ayxi2l)."""

from __future__ import annotations

import fcntl
import os
from pathlib import Path
from typing import Any

import pytest
from livespec_orchestrator_beads_fabro import _beads_list_cache as cache
from livespec_orchestrator_beads_fabro._beads_client import FakeBeadsClient
from livespec_orchestrator_beads_fabro.store import read_work_items
from livespec_orchestrator_beads_fabro.types import StoreConfig


@pytest.fixture(autouse=True)
def _cache_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    directory = tmp_path / "cache"
    monkeypatch.setenv(cache.CACHE_DIR_ENV, str(directory))
    return directory


def _counting_dump(*, calls: list[int]) -> Any:
    def dump() -> list[dict[str, Any]]:
        calls.append(1)
        return [{"id": "li-a"}]

    return dump


def test_the_default_cache_directory_is_per_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(cache.CACHE_DIR_ENV)

    assert cache._cache_dir().name == f"livespec-bd-list-cache-{os.getuid()}"  # noqa: SLF001


def test_an_unreadable_entry_falls_through_and_is_rewritten() -> None:
    calls: list[int] = []
    entry = cache._entry_path(tenant_key="t")  # noqa: SLF001
    entry.parent.mkdir(parents=True)
    entry.write_text("not json", encoding="utf-8")

    cache.read_through(tenant_key="t", dump=_counting_dump(calls=calls))
    cache.read_through(tenant_key="t", dump=_counting_dump(calls=calls))

    assert len(calls) == 1


def test_an_entry_from_the_future_is_not_trusted(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(cache.time, "time", lambda: 1000.0)
    cache.read_through(tenant_key="t", dump=_counting_dump(calls=calls))
    monkeypatch.setattr(cache.time, "time", lambda: 900.0)

    cache.read_through(tenant_key="t", dump=_counting_dump(calls=calls))

    assert len(calls) == 2


def test_a_lock_not_taken_in_time_falls_through_to_a_direct_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[int] = []
    monkeypatch.setattr(cache, "LOCK_WAIT_SECONDS", 0.0)
    path = cache._entry_path(tenant_key="t")  # noqa: SLF001
    path.parent.mkdir(parents=True)
    holder = os.open(path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR)
    fcntl.flock(holder, fcntl.LOCK_EX)
    try:
        records = cache.read_through(tenant_key="t", dump=_counting_dump(calls=calls))
        sleeps: list[float] = []
        monkeypatch.setattr(cache, "LOCK_WAIT_SECONDS", 0.2)
        monkeypatch.setattr(cache.time, "sleep", sleeps.append)
        cache.read_through(tenant_key="t", dump=_counting_dump(calls=calls))
    finally:
        os.close(holder)

    assert records == [{"id": "li-a"}]
    assert len(calls) == 2
    assert sleeps


def test_an_unusable_cache_directory_falls_through_to_a_direct_dump(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    monkeypatch.setenv(cache.CACHE_DIR_ENV, str(blocker / "sub"))
    calls: list[int] = []

    cache.read_through(tenant_key="t", dump=_counting_dump(calls=calls))

    assert len(calls) == 1


def test_an_unwritable_entry_still_returns_the_dump(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def refuse(*_args: object, **_kwargs: object) -> int:
        raise OSError("read-only")

    monkeypatch.setattr(Path, "write_text", refuse)

    records = cache.read_through(tenant_key="t", dump=_counting_dump(calls=calls))

    assert records == [{"id": "li-a"}]


def test_invalidating_a_missing_entry_is_a_no_op() -> None:
    cache.invalidate(tenant_key="never-cached")


def test_a_cached_work_item_read_over_the_fake_client_matches_the_direct_read() -> None:
    config = StoreConfig(
        tenant="t", prefix="li", server_user="t", database="t", bd_path="bd", fake=True
    )

    assert list(read_work_items(path=config, cached=True)) == list(read_work_items(path=config))
    assert FakeBeadsClient().list_issues_cached() == []
