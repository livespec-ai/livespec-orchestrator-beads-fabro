"""Check named Definition-of-Done settings against a pinned tool's own listing.

The check is deliberately configured by the governed repository.  A tool's
configuration vocabulary is its own authority, and the command below is run at
the version that repository pins rather than inferred from a specification
heading or from the host's installed version.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from livespec_orchestrator_beads_fabro.commands._config import dispatcher_block
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done import (
    definition_of_done,
)
from livespec_orchestrator_beads_fabro.errors import LivespecConfigUnreadableError

if TYPE_CHECKING:
    from pathlib import Path

    from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "NamedSettingCheck",
    "NamedSettingCheckResult",
    "named_setting_checks",
]

_CHECKS_KEY = "definition_of_done_setting_checks"
_SETTING_TOKEN = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")
_NON_SETTING_TOKENS = frozenset({"AND", "MAY", "MUST", "NOT", "OR", "SHALL", "SHOULD"})


@dataclass(frozen=True, kw_only=True)
class NamedSettingCheck:
    """One listing command that could not establish its pinned setting names."""

    tool: str
    version: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class NamedSettingCheckResult:
    """The deterministic setting-screen result for one item."""

    findings: tuple[str, ...] = ()
    unavailable: tuple[NamedSettingCheck, ...] = ()


def named_setting_checks(*, item: WorkItem, cwd: Path) -> NamedSettingCheckResult:
    """Read configured pinned listings and find assertion names they do not define.

    A check that cannot execute is explicitly non-blocking.  Callers that own a
    ledger write receive its reason in ``unavailable`` and record the receipt;
    read-only projections simply preserve the item's existing route.
    """
    section = definition_of_done(description=item.description)
    assertions = tuple(assertion.text for assertion in section.assertions)
    if not assertions:
        return NamedSettingCheckResult()
    candidates = _assertion_setting_candidates(assertions=assertions)
    findings: list[str] = []
    unavailable: list[NamedSettingCheck] = []
    for raw_check in _configured_checks(cwd=cwd):
        check = _check_definition(raw_check=raw_check)
        if check is None:
            continue
        tool, version, command, aliases = check
        selected = _selected_candidates(
            candidates=candidates, aliases=aliases, assertions=assertions
        )
        if not selected:
            continue
        listed, output = _listing(command=command, cwd=cwd)
        if not listed:
            unavailable.append(NamedSettingCheck(tool=tool, version=version, detail=output))
            continue
        names = frozenset(_SETTING_TOKEN.findall(output))
        for setting in selected:
            expected = aliases.get(setting, setting)
            if expected not in names:
                subject = f"work-item {item.id}: the Definition of Done assertion names"
                findings.append(
                    f"{subject} setting {setting!r}, but pinned {tool} {version} does not define it"
                )
    return NamedSettingCheckResult(findings=tuple(findings), unavailable=tuple(unavailable))


def _configured_checks(*, cwd: Path) -> tuple[dict[str, object], ...]:
    # Filing display is advisory and has always remained usable when its
    # dispatcher configuration is unreadable.  A settings screen cannot turn
    # that existing display path into a refusal; without a readable
    # configuration it has no pinned command to run, so it contributes no
    # configured check.
    try:
        raw = dispatcher_block(cwd=cwd).get(_CHECKS_KEY)
    except LivespecConfigUnreadableError:
        return ()
    if not isinstance(raw, list):
        return ()
    entries = cast("list[object]", raw)
    return tuple(cast("dict[str, object]", entry) for entry in entries if isinstance(entry, dict))


def _check_definition(
    *, raw_check: dict[str, object]
) -> tuple[str, str, list[str], dict[str, str]] | None:
    tool = raw_check.get("tool")
    version = raw_check.get("version")
    command = raw_check.get("settings_listing_command")
    if not isinstance(tool, str) or not tool or not isinstance(version, str) or not version:
        return None
    if not isinstance(command, list) or not command:
        return None
    command_parts = cast("list[object]", command)
    if not all(isinstance(part, str) and part for part in command_parts):
        return None
    aliases = _aliases(raw=raw_check.get("setting_aliases"))
    return tool, version, cast("list[str]", command_parts), aliases


def _aliases(*, raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    entries = cast("dict[object, object]", raw)
    return {
        assertion_name.upper(): listed_name
        for assertion_name, listed_name in entries.items()
        if isinstance(assertion_name, str)
        and assertion_name
        and isinstance(listed_name, str)
        and listed_name
    }


def _assertion_setting_candidates(*, assertions: tuple[str, ...]) -> frozenset[str]:
    return frozenset(
        token
        for assertion in assertions
        for token in _SETTING_TOKEN.findall(assertion)
        if token not in _NON_SETTING_TOKENS
    )


def _selected_candidates(
    *, candidates: frozenset[str], aliases: dict[str, str], assertions: tuple[str, ...]
) -> tuple[str, ...]:
    # Aliases let a repository declare, for example, that prose's `pipelining`
    # means Ansible's displayed `ANSIBLE_PIPELINING`; the assertion scanner only
    # needs to recognise the spelling that is actually written in the item.
    named_aliases = {
        assertion_name
        for assertion_name in aliases
        if any(
            re.search(
                rf"(?<![A-Za-z0-9_]){re.escape(assertion_name)}(?![A-Za-z0-9_])",
                text,
                re.IGNORECASE,
            )
            for text in assertions
        )
    }
    return tuple(sorted(candidates | named_aliases))


def _listing(*, command: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        completed = subprocess.run(  # noqa: S603 -- argv is committed repository configuration.
            command,
            cwd=cwd,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if completed.returncode != 0:
        detail = (
            completed.stderr.strip() or completed.stdout.strip() or f"exit {completed.returncode}"
        )
        return False, detail
    return True, completed.stdout
