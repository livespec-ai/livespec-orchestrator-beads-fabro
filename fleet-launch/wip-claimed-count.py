#!/usr/bin/env python3
# PROVISIONAL / EXPERIMENTAL — part of fleet-launch/, a stopgap whose first-class
# replacements are the livespec console application and the committed launch-loop
# tool bd-ib-jr6w7v (see fleet-launch/README.md).
"""The repository WIP claim count the launcher's WIP gate compares against wip_cap.

Usage: wip-claimed-count.py <plugin-root> <repo-path> <inflight-dir> <this-item>
                            [--cache-dir <dir>] [--ttl <seconds>] [--ids]

Prints one JSON object:

    {"counted_claims": N, "in_flight_addition": K, "wip_cap": C, "cache": "<hit|miss|disabled>"}

``counted_claims`` is the installed plugin build's OWN side-effect-free admission
accounting (``claimed_active_projection``: active AND a live dispatch lock in any
tenant checkout, or an unreadable journal), so the launcher's gate cannot diverge
from the Dispatcher's capacity count. It never writes the journal.
``in_flight_addition`` is this repository's launches already past the FIFO (a
fleet in-flight marker whose launcher process is alive) whose item is not yet
``active``, excluding ``<this-item>``'s own marker; it is recomputed on every call
from the cached statuses, never cached. ``wip_cap`` is the repository's configured
cap. The gate compares ``counted_claims + in_flight_addition`` against the cap.

THE EXPENSIVE PART IS SHARED. The ledger read and the projection are computed
once per ``--ttl`` seconds per repository, under an exclusive lock, into
``<cache-dir>/wip-claimed-cache.<repo>.json`` (the count, every item's status and
the time of the read), beside a ``.statuses`` text sidecar (one ``<item> <status>``
line per item) that a launcher can read without spawning Python. A caller that
finds another caller computing reuses a slightly older read rather than
recomputing. A TTL of 0 disables the cache. A failed computation prints nothing,
writes no cache file and exits non-zero, so the launcher does not hold on it.

With ``--ids`` the accounting's id sets are printed after the JSON, one labelled
line each, and the cache is bypassed. Run it UNDER the tenant's credential wrapper.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sys
import time
from pathlib import Path

__all__: list[str] = ["main"]

USAGE_ERROR = 2
MIN_ARGC = 5
STALE_FACTOR = 6


def _parse(*, argv: list[str]) -> dict[str, object] | None:
    if len(argv) < MIN_ARGC:
        return None
    options: dict[str, object] = {
        "plugin": argv[1],
        "repo": Path(argv[2]),
        "inflight": Path(argv[3]),
        "me": argv[4],
        "cache_dir": Path(argv[2]) / "tmp",
        "ttl": 25,
        "ids": False,
    }
    rest = argv[5:]
    while rest:
        flag = rest.pop(0)
        if flag == "--ids":
            options["ids"] = True
        elif flag == "--cache-dir" and rest:
            options["cache_dir"] = Path(rest.pop(0))
        elif flag == "--ttl" and rest:
            options["ttl"] = int(rest.pop(0))
        else:
            return None
    return options


def _read_cache(*, path: Path, max_age: float) -> dict[str, object] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - float(data["ts"]) <= max_age:
            return data
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def _compute(*, plugin: str, repo: Path) -> tuple[object, list[object], int]:
    sys.path.insert(0, f"{plugin}/scripts/bin")
    from _bootstrap import bootstrap

    bootstrap()
    from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
    from livespec_orchestrator_beads_fabro.commands._dispatcher_claim_reclaim import (
        claimed_active_projection,
    )
    from livespec_orchestrator_beads_fabro.commands._dispatcher_io import JournalFile
    from livespec_orchestrator_beads_fabro.commands._dispatcher_valves import (
        DEFAULT_WIP_CAP,
        resolve_wip_cap,
    )
    from livespec_orchestrator_beads_fabro.store import read_work_items
    from returns.unsafe import unsafe_perform_io

    items = list(read_work_items(path=resolve_store_config(cwd=repo, work_items_arg=None)))
    accounting = claimed_active_projection(
        repo=repo,
        items=items,
        journal=JournalFile(path=repo / "tmp" / "fabro-dispatch-journal.jsonl"),
    )
    cap = unsafe_perform_io(resolve_wip_cap(cwd=repo).value_or(DEFAULT_WIP_CAP))
    return accounting, items, int(cap)


def _write_cache(*, path: Path, payload: dict[str, object], statuses: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)
    sidecar = path.with_name(f"{path.name}.statuses")
    tmp = sidecar.with_name(f"{sidecar.name}.{os.getpid()}.tmp")
    tmp.write_text("".join(f"{k} {v}\n" for k, v in sorted(statuses.items())), encoding="utf-8")
    tmp.replace(sidecar)


def _statuses_of(*, cached: dict[str, object]) -> dict[str, str]:
    raw = cached.get("st")
    if not isinstance(raw, dict):
        message = "the WIP cache carries no status map"
        raise TypeError(message)
    return {str(k): str(v) for k, v in raw.items()}  # type: ignore[union-attr]


def _shared_read(
    *, cache_path: Path, ttl: int, plugin: str, repo: Path
) -> tuple[dict[str, object], str, object, list[object]]:
    """The cached read, computed once per TTL under the per-repository lock."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with Path(f"{cache_path}.lock").open("w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            got = True
        except OSError:
            got = False
        cached: dict[str, object] | None = None
        if not got:
            # Another caller is computing: reuse a slightly older read if there is one,
            # otherwise wait for the computing caller.
            cached = _read_cache(path=cache_path, max_age=ttl * STALE_FACTOR)
            if cached is None:
                fcntl.flock(lock, fcntl.LOCK_EX)
                cached = _read_cache(path=cache_path, max_age=ttl * STALE_FACTOR)
        if cached is not None:
            return cached, "hit", None, []
        accounting, items, cap = _compute(plugin=plugin, repo=repo)
        statuses = {str(i.id): str(i.status) for i in items}  # type: ignore[attr-defined]
        cached = {
            "ts": time.time(),
            "active_count": accounting.active_count,  # type: ignore[attr-defined]
            "wip_cap": cap,
            "st": statuses,
        }
        _write_cache(path=cache_path, payload=cached, statuses=statuses)
        return cached, "miss", accounting, items


def _in_flight_addition(*, inflight: Path, me: str, statuses: dict[str, str]) -> set[str]:
    pending: set[str] = set()
    if not inflight.is_dir():
        return pending
    for marker in inflight.iterdir():
        try:
            text = marker.read_text(encoding="utf-8")
        except OSError:
            continue
        item = re.search(r"item=(\S+)", text)
        pid = re.search(r"pid=(\d+)", text)
        if item is None or pid is None or item.group(1) == me or item.group(1) not in statuses:
            continue
        try:
            os.kill(int(pid.group(1)), 0)
        except OSError:
            continue
        if statuses[item.group(1)] != "active":
            pending.add(item.group(1))
    return pending


def main(*, argv: list[str]) -> int:
    options = _parse(argv=argv)
    if options is None:
        print(__doc__)
        return USAGE_ERROR
    plugin = str(options["plugin"])
    repo = Path(str(options["repo"]))
    inflight = Path(str(options["inflight"]))
    me = str(options["me"])
    cache_dir = Path(str(options["cache_dir"]))
    ttl = int(str(options["ttl"]))
    show_ids = bool(options["ids"])
    cache_path = cache_dir / f"wip-claimed-cache.{repo.name}.json"
    accounting: object = None
    items: list[object] = []
    source = "disabled"
    cached: dict[str, object] | None = None
    if ttl > 0 and not show_ids:
        cached = _read_cache(path=cache_path, max_age=ttl)
        source = "hit"
        if cached is None:
            cached, source, accounting, items = _shared_read(
                cache_path=cache_path, ttl=ttl, plugin=plugin, repo=repo
            )
    if cached is None:
        accounting, items, cap = _compute(plugin=plugin, repo=repo)
        cached = {
            "active_count": accounting.active_count,  # type: ignore[attr-defined]
            "wip_cap": cap,
            "st": {str(i.id): str(i.status) for i in items},  # type: ignore[attr-defined]
        }
    statuses = _statuses_of(cached=cached)
    pending = _in_flight_addition(inflight=inflight, me=me, statuses=statuses)
    print(
        json.dumps(
            {
                "counted_claims": int(str(cached["active_count"])),
                "in_flight_addition": len(pending),
                "wip_cap": int(str(cached["wip_cap"])),
                "cache": source,
            }
        )
    )
    if show_ids and accounting is not None:
        _print_ids(accounting=accounting, items=items, statuses=statuses, pending=pending)
    return 0


def _print_ids(
    *, accounting: object, items: list[object], statuses: dict[str, str], pending: set[str]
) -> None:
    acct = accounting
    lockless = sorted(
        i.id  # type: ignore[attr-defined]
        for i in items
        if i.status == "active"  # type: ignore[attr-defined]
        and i.id not in acct.live_lock_active_ids  # type: ignore[attr-defined]
        and i.id not in acct.journal_unreadable_active_ids  # type: ignore[attr-defined]
    )
    print("live_lock:", " ".join(acct.live_lock_active_ids))  # type: ignore[attr-defined]
    print("journal_unreadable:", " ".join(acct.journal_unreadable_active_ids))  # type: ignore[attr-defined]
    print("rework_pending (uncounted):", " ".join(acct.rework_pending_active_ids))  # type: ignore[attr-defined]
    print("green_terminal (uncounted):", " ".join(acct.green_terminal_active_ids))  # type: ignore[attr-defined]
    print("lockless_active (uncounted):", " ".join(lockless))
    print("pending_inflight:", " ".join(sorted(pending)))
    print("ledger_active_total:", sum(1 for v in statuses.values() if v == "active"))


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv))
