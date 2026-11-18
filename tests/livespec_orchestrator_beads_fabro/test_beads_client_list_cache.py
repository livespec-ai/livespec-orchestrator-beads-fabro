"""The per-host shared cache of the full-ledger `bd list` dump (bd-ib-ayxi2l).

Ten detached dispatcher loops each ran the full dump on every pass, saturating
the host-to-ledger link. `list_issues_cached` lets concurrent readers and
successive passes share ONE dump inside a short TTL. The cache is opt-in per
read: `list_issues` (every claim-taking and dispatch-decision read) never
touches it, and any write through the client invalidates it.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro._beads_client import ShellBeadsClient
from livespec_orchestrator_beads_fabro.types import StoreConfig


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="livespec-impl-beads",
        prefix="li",
        server_user="livespec-impl-beads",
        database="livespec-impl-beads",
        bd_path="bd",
        fake=False,
    )


def _client(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[ShellBeadsClient, list[list[str]]]:
    monkeypatch.setenv("LIVESPEC_BD_LIST_CACHE_DIR", str(tmp_path / "cache"))
    client = ShellBeadsClient(config=_config())
    calls: list[list[str]] = []

    def fake_invoke(*, argv: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='[{"id": "li-a"}]', stderr="")

    monkeypatch.setattr(client, "_invoke", fake_invoke)
    return client, calls


def _list_calls(*, calls: list[list[str]]) -> int:
    return sum(1 for argv in calls if "list" in argv)


def test_two_cached_readers_inside_the_ttl_share_one_dump(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first, calls = _client(monkeypatch=monkeypatch, tmp_path=tmp_path)
    second = ShellBeadsClient(config=_config())
    monkeypatch.setattr(second, "_invoke", first._invoke)  # noqa: SLF001

    assert first.list_issues_cached() == [{"id": "li-a"}]
    assert second.list_issues_cached() == [{"id": "li-a"}]

    assert _list_calls(calls=calls) == 1


def test_a_write_between_two_cached_reads_forces_a_second_dump(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, calls = _client(monkeypatch=monkeypatch, tmp_path=tmp_path)

    _ = client.list_issues_cached()
    client.close_issue(issue_id="li-a", reason=None)
    _ = client.list_issues_cached()

    assert _list_calls(calls=calls) == 2


def test_a_claim_or_decision_read_always_dumps_directly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, calls = _client(monkeypatch=monkeypatch, tmp_path=tmp_path)

    _ = client.list_issues_cached()
    _ = client.list_issues()
    _ = client.list_issues()

    assert _list_calls(calls=calls) == 3


def test_a_cache_entry_older_than_the_ttl_falls_through_to_a_direct_dump(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client, calls = _client(monkeypatch=monkeypatch, tmp_path=tmp_path)
    clock = [1000.0]
    monkeypatch.setattr(
        "livespec_orchestrator_beads_fabro._beads_list_cache.time.time", lambda: clock[0]
    )

    _ = client.list_issues_cached()
    clock[0] += 16.0
    _ = client.list_issues_cached()

    assert _list_calls(calls=calls) == 2
