"""Committed admission-setting attribution for the human policy valve."""

from __future__ import annotations

from pathlib import Path

from returns.unsafe import unsafe_perform_io

from livespec_orchestrator_beads_fabro.commands._dispatcher_policy_settings import (
    read_dispatcher_config_value,
)

__all__: list[str] = ["committed_admission_setting_note"]


def committed_admission_setting_note(*, repo: Path) -> str:
    """Name the committed admission setting without mistaking its default for one."""
    configured = unsafe_perform_io(
        read_dispatcher_config_value(cwd=repo, key="auto_approve_ready").value_or(None)
    )
    if not isinstance(configured, bool):
        return ""
    return (
        " The committed dispatcher.auto_approve_ready="
        f"{str(configured).lower()} decides the item's admission."
    )
