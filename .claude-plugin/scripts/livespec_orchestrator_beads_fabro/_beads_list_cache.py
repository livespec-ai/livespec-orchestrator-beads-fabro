"""Per-host shared cache of the full-ledger `bd list` dump (bd-ib-ayxi2l).

Every detached dispatcher loop ran `bd list --status all --limit 0 --json` on
every pass; ten loops saturated the host-to-ledger link. Readers that opt in
share ONE dump per tenant inside a short TTL. The cache lives in a flock-guarded
file under a per-user directory, so concurrent processes share it.

Safety rules, each enforced here or at the single call site:

- the cache is opt-in: `ShellBeadsClient.list_issues` never reads it, so every
  claim-taking and dispatch-decision read stays a direct dump;
- `invalidate` removes the entry, and the client calls it after ANY write;
- an entry older than `TTL_SECONDS`, an unreadable entry, or a lock not taken
  within `LOCK_WAIT_SECONDS` all fall through to a direct dump.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any, cast

__all__: list[str] = [
    "CACHE_DIR_ENV",
    "LOCK_WAIT_SECONDS",
    "TTL_SECONDS",
    "invalidate",
    "read_through",
    "time",
]

CACHE_DIR_ENV = "LIVESPEC_BD_LIST_CACHE_DIR"
TTL_SECONDS = 15.0
LOCK_WAIT_SECONDS = 3.0
_LOCK_POLL_SECONDS = 0.05


def _cache_dir() -> Path:
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / f"livespec-bd-list-cache-{os.getuid()}"


def _entry_path(*, tenant_key: str) -> Path:
    digest = hashlib.sha256(tenant_key.encode("utf-8")).hexdigest()[:24]
    return _cache_dir() / f"{digest}.json"


def invalidate(*, tenant_key: str) -> None:
    """Drop the tenant's cached dump; a missing entry is already invalid."""
    with suppress(OSError):
        _entry_path(tenant_key=tenant_key).unlink()


def _fresh_entry(*, path: Path) -> list[dict[str, Any]] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        stored_at = float(payload["stored_at"])
        records = payload["records"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    age = time.time() - stored_at
    if not isinstance(records, list) or age < 0 or age > TTL_SECONDS:
        return None
    return cast("list[dict[str, Any]]", records)


def _take_lock(*, descriptor: int) -> bool:
    deadline = time.monotonic() + LOCK_WAIT_SECONDS
    while True:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(_LOCK_POLL_SECONDS)
        else:
            return True


def read_through(
    *, tenant_key: str, dump: Callable[[], list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Return the shared dump, running `dump` only when no fresh entry exists."""
    path = _entry_path(tenant_key=tenant_key)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path.with_suffix(".lock"), os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return dump()
    try:
        if not _take_lock(descriptor=descriptor):
            return dump()
        cached = _fresh_entry(path=path)
        if cached is not None:
            return cached
        records = dump()
        staging = path.with_suffix(f".{os.getpid()}.tmp")
        with suppress(OSError):
            _ = staging.write_text(
                json.dumps({"stored_at": time.time(), "records": records}), encoding="utf-8"
            )
            _ = staging.replace(path)
        return records
    finally:
        os.close(descriptor)
