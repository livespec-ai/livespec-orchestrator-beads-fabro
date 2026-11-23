"""Whether a recorded repository name and a caller's name are the same repository.

A chain published before the owner swap names `thewoolleyman/<repo>`; the same
repository is addressed today as `livespec-ai/<repo>`. A transfer keeps the forge's
stable numeric id, so two names that differ only in their owner are one repository
exactly when the forge resolves both to the same id. Any unreadable id, and any
difference in the repository part of the name, is a refusal: the check fails closed.
"""

from __future__ import annotations

import subprocess

__all__: list[str] = ["resolve_repository_id", "same_repository"]


def resolve_repository_id(*, repository: str) -> str | None:
    """The forge's stable id for `repository`, or None when it cannot be read."""
    try:
        completed = subprocess.run(  # noqa: S603  # pragma: no cover
            ["gh", "api", f"repos/{repository}", "--jq", ".id"],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):  # pragma: no cover
        return None
    stable = completed.stdout.strip()  # pragma: no cover
    return stable if completed.returncode == 0 and stable.isdigit() else None  # pragma: no cover


def same_repository(*, recorded: str, caller: str) -> bool:
    """Equal names are one repository; owner-differing names must share a stable id."""
    if recorded == caller:
        return True
    if recorded.rsplit("/", 1)[-1] != caller.rsplit("/", 1)[-1]:
        return False
    recorded_id = resolve_repository_id(repository=recorded)
    return recorded_id is not None and recorded_id == resolve_repository_id(repository=caller)
