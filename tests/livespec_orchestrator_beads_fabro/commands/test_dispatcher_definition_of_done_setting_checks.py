"""Pinned-tool named-setting checks are deterministic and non-blocking on outages."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_definition_of_done_setting_checks as setting_checks,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_eligibility import (
    pre_dispatch_criteria_refusal,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_definition_of_done_setting_checks import (
    named_setting_checks,
)
from livespec_orchestrator_beads_fabro.commands._dod_unavailable_record import (
    named_setting_check_did_not_run_comment,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

_REFERENCE = "## Effective acceptance criteria"


def _item(*, assertion: str) -> WorkItem:
    return WorkItem(
        id="bd-ib-setting-check",
        type="bug",
        status="pending-approval",
        title="A named setting check",
        description=(
            "## Definition of Done\n\n" f"- {assertion}\n\n" f"References: {_REFERENCE}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-11-19T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="manual",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path, command: list[str], aliases: dict[str, str] | None = None) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    check: dict[str, object] = {
        "tool": "ansible-core",
        "version": "2.21.4",
        "settings_listing_command": command,
    }
    if aliases is not None:
        check["setting_aliases"] = aliases
    config = {
        "livespec-orchestrator-beads-fabro": {
            "dispatcher": {"definition_of_done_setting_checks": [check]}
        }
    }
    _ = (repo / ".livespec.jsonc").write_text(json.dumps(config), encoding="utf-8")
    return repo


def _listing(*, tmp_path: Path, output: str, exit_code: int = 0) -> list[str]:
    script = tmp_path / "settings-listing"
    _ = script.write_text(
        f"#!/bin/sh\nprintf '%s\\n' {output!r}\nexit {exit_code}\n", encoding="utf-8"
    )
    script.chmod(0o755)
    return [str(script)]


def test_aliases_admit_an_ini_key_when_the_pinned_listing_uses_another_name(
    tmp_path: Path,
) -> None:
    command = _listing(tmp_path=tmp_path, output="ANSIBLE_PIPELINING(default) = False")
    repo = _repo(
        tmp_path=tmp_path,
        command=command,
        aliases={"pipelining": "ANSIBLE_PIPELINING"},
    )

    result = named_setting_checks(
        item=_item(assertion="The connection pipelining setting remains enabled."), cwd=repo
    )

    assert result.findings == ()
    assert result.unavailable == ()


def test_an_unavailable_pinned_listing_leaves_the_item_unheld_and_names_why(
    tmp_path: Path,
) -> None:
    command = _listing(tmp_path=tmp_path, output="not installed", exit_code=9)
    repo = _repo(tmp_path=tmp_path, command=command)

    result = named_setting_checks(
        item=_item(assertion="DEFAULT_PIPELINING keeps the target secret off disk."), cwd=repo
    )

    assert result.findings == ()
    assert len(result.unavailable) == 1
    check = result.unavailable[0]
    assert (check.tool, check.version, check.detail) == ("ansible-core", "2.21.4", "not installed")
    receipt = named_setting_check_did_not_run_comment(
        item_id="bd-ib-setting-check",
        stage="pre-admission",
        tool=check.tool,
        version=check.version,
        detail=check.detail,
    )
    assert "named-setting check did not run" in receipt
    assert "ansible-core" in receipt
    assert "2.21.4" in receipt
    assert "not installed" in receipt


def test_the_pre_dispatch_wall_refuses_an_undefined_setting_before_a_factory_run(
    tmp_path: Path,
) -> None:
    command = _listing(tmp_path=tmp_path, output="ANSIBLE_PIPELINING(default) = False")
    repo = _repo(tmp_path=tmp_path, command=command)

    refusal = pre_dispatch_criteria_refusal(
        items=[_item(assertion="DEFAULT_PIPELINING keeps the target secret off disk.")], cwd=repo
    )

    assert refusal is not None
    assert "no factory run was created" in refusal
    assert "DEFAULT_PIPELINING" in refusal
    assert "ansible-core 2.21.4" in refusal


def test_a_check_with_no_named_setting_or_invalid_configuration_does_nothing(
    tmp_path: Path,
) -> None:
    repo = _repo(tmp_path=tmp_path, command=["not-run"])
    _ = (repo / ".livespec.jsonc").write_text(
        json.dumps(
            {
                "livespec-orchestrator-beads-fabro": {
                    "dispatcher": {
                        "definition_of_done_setting_checks": [
                            {"version": "2.21.4", "settings_listing_command": ["not-run"]},
                            {
                                "tool": "ansible-core",
                                "version": "2.21.4",
                                "settings_listing_command": [],
                            },
                            {
                                "tool": "ansible-core",
                                "version": "2.21.4",
                                "settings_listing_command": [""],
                            },
                            {
                                "tool": "ansible-core",
                                "version": "2.21.4",
                                "settings_listing_command": ["not-run"],
                            },
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    result = named_setting_checks(
        item=_item(assertion="The connection setting remains enabled."), cwd=repo
    )

    assert result.findings == ()
    assert result.unavailable == ()


def test_an_unreadable_config_keeps_the_named_setting_screen_non_blocking(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / ".livespec.jsonc").write_text("{ malformed", encoding="utf-8")

    result = named_setting_checks(
        item=_item(assertion="DEFAULT_PIPELINING keeps the target secret off disk."), cwd=repo
    )

    assert result.findings == ()
    assert result.unavailable == ()


@pytest.mark.parametrize(
    "failure",
    [OSError("missing executable"), subprocess.TimeoutExpired(cmd="ansible-config", timeout=30)],
)
def test_an_exception_running_the_pinned_listing_is_recorded_as_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    repo = _repo(tmp_path=tmp_path, command=["ansible-config", "dump"])

    def _raise(*_: object, **__: object) -> object:
        raise failure

    monkeypatch.setattr(setting_checks.subprocess, "run", _raise)

    result = named_setting_checks(
        item=_item(assertion="DEFAULT_PIPELINING keeps the target secret off disk."), cwd=repo
    )

    assert result.findings == ()
    assert result.unavailable == (
        setting_checks.NamedSettingCheck(
            tool="ansible-core", version="2.21.4", detail=str(failure)
        ),
    )
