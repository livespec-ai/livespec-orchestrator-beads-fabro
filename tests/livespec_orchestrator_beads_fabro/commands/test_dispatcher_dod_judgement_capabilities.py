"""Configured capabilities cannot rewrite a host Definition-of-Done rubric.

Scenario 239 requires every taking to grade one subject by one rubric. The
host's configured capability mirror therefore cannot add host-only guidance or
remove the node rubric's own capability instructions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_dod_judgement_run import (
    dod_gate_prompt_path,
    run_dod_judgement,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.types import WorkItem

_HEADING = "## Scenario 174 — The judgement runs before admission"


@dataclass
class _Runner:
    """A CommandRunner double that keeps the prompt each candidate was handed."""

    stdin_text: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
        stdin: int | None = None,
        start_new_session: bool = False,
    ) -> CommandResult:
        _ = (argv, cwd, timeout_seconds, env, start_new_session)
        # The judgement always hands its prompt over on stdin.
        assert stdin is not None
        _ = os.lseek(stdin, 0, os.SEEK_SET)
        self.stdin_text.append(os.read(stdin, 1_000_000).decode("utf-8"))
        return CommandResult(exit_code=0, stdout='{"outcome": "passed"}\n', stderr="")


def _item() -> WorkItem:
    return WorkItem(
        id="bd-ib-ff5ohb",
        type="bug",
        status="ready",
        title="Judge with the configured capability set",
        description=(
            "## Definition of Done\n\n- The judgement runs before admission.\n\n"
            f"References: {_HEADING}\n"
        ),
        origin="freeform",
        gap_id=None,
        rank="a0",
        assignee=None,
        depends_on=(),
        captured_at="2026-10-31T00:00:00Z",
        resolution=None,
        reason=None,
        audit=None,
        superseded_by=None,
        admission_policy="auto",
        acceptance_policy="ai-only",
    )


def _repo(*, tmp_path: Path, capabilities: str | None) -> Path:
    repo = tmp_path / "repo"
    spec = repo / "SPECIFICATION"
    spec.mkdir(parents=True)
    _ = (spec / "scenarios.md").write_text(
        f"# Scenarios\n\n{_HEADING}\n\nThe judgement runs before admission.\n", encoding="utf-8"
    )
    mirror = "" if capabilities is None else f'"sandbox_capabilities": {capabilities},\n      '
    _ = (repo / ".livespec.jsonc").write_text(
        '{\n  "livespec-orchestrator-beads-fabro": {\n    "dispatcher": {\n      '
        f"{mirror}"
        '"acp_nodes": {\n        "dod_gate": {\n          "agent": "claude-acp",\n'
        '          "model": "claude-opus-5",\n          "effort": "high"\n        }\n'
        "      }\n    }\n  }\n}\n",
        encoding="utf-8",
    )
    return repo


def _prompt(*, tmp_path: Path, capabilities: str | None) -> str:
    runner = _Runner()
    _ = run_dod_judgement(
        item=_item(),
        cwd=_repo(tmp_path=tmp_path, capabilities=capabilities),
        runner=runner,
        rubric=dod_gate_prompt_path().read_text(encoding="utf-8"),
    )
    return runner.stdin_text[0].casefold()


def test_configured_capabilities_do_not_change_the_node_rubric(
    tmp_path: Path,
) -> None:
    prompt = _prompt(
        tmp_path=tmp_path, capabilities='["terminal", "headless_browser", "tmux", "herdr"]'
    )

    assert prompt.startswith(dod_gate_prompt_path().read_text(encoding="utf-8").casefold())


def test_an_unconfigured_capability_mirror_does_not_change_the_node_rubric(
    tmp_path: Path,
) -> None:
    prompt = _prompt(tmp_path=tmp_path, capabilities=None)

    assert prompt.startswith(dod_gate_prompt_path().read_text(encoding="utf-8").casefold())
