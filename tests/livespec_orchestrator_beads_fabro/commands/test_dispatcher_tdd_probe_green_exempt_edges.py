"""Fail-soft edge coverage for Green-exempt commit evidence."""

# ruff: noqa: SLF001

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe"


def _module() -> ModuleType:
    return importlib.import_module(_MODULE_NAME)


@dataclass
class _Runner:
    """Return scripted command responses in their invocation order."""

    responses: list[CommandResult] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> CommandResult:
        assert argv
        assert cwd == Path("/repo")
        assert timeout_seconds > 0
        assert env is None
        return self.responses.pop(0)


def _result(*, stdout: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(exit_code=exit_code, stdout=stdout, stderr="")


def test_commit_payload_preserves_only_usable_messages_and_object_ids() -> None:
    module = _module()

    commits = module._commits_from_payload(
        stdout=json.dumps(
            {
                "commits": [
                    "not an object",
                    {"messageHeadline": 3, "messageBody": "ignored"},
                    {"messageHeadline": "kept without oid", "messageBody": 4, "oid": ""},
                    {"messageHeadline": "kept", "messageBody": "body", "oid": "abc123"},
                ]
            }
        )
    )

    assert commits is not None
    assert [(commit.message, commit.oid) for commit in commits] == [
        ("kept without oid\n\n", None),
        ("kept\n\nbody", "abc123"),
    ]


def test_repository_and_changed_file_evidence_fail_soft() -> None:
    module = _module()

    for response in (
        _result(exit_code=1),
        _result(stdout="not json"),
        _result(stdout="[]"),
        _result(stdout='{"nameWithOwner": ""}'),
    ):
        assert module._repository_name(repo=Path("/repo"), runner=_Runner([response])) is None

    for payload in (
        "not json",
        "[]",
        "{}",
        '{"files": ["not an object", {"filename": 3}, {"filename": "tests/unit.py"}]}',
        '{"files": [{"filename": "implementation.py"}]}',
    ):
        assert module._has_only_non_python_implementation(stdout=payload) is False


def _files_payload(*filenames: str) -> str:
    return json.dumps({"files": [{"filename": name} for name in filenames]})


def test_only_the_hooks_non_python_implementation_shapes_are_green_exempt() -> None:
    module = _module()

    for exempt in (
        ("ansible/tasks/main.yml", "tests/test_role.py"),
        ("config/settings.yaml",),
        ("scripts/run.sh",),
        ("tasks.just",),
        ("justfile",),
        ("sub/Justfile",),
        (".claude-plugin/.fabro/workflows/x/workflow.fabro",),
        ("README.md", "ansible/tasks/main.yml"),
    ):
        assert module._has_only_non_python_implementation(stdout=_files_payload(*exempt)) is True

    for refused in (
        ("README.md",),
        ("docs/guide.md", "tests/test_role.py"),
        ("data/fixture.json",),
        ("notes.txt", "data/table.csv"),
        ("ansible/tasks/main.yml", "src/module.py"),
    ):
        assert module._has_only_non_python_implementation(stdout=_files_payload(*refused)) is False


def test_green_exempt_lookup_requires_a_red_only_commit_and_usable_file_evidence() -> None:
    module = _module()
    red_only = module._Commit(message="fix: x\n\nTDD-Red-Captured-At: now", oid="abc123")

    assert (
        module._green_exempt_oids(
            repo=Path("/repo"),
            commits=(module._Commit(message="chore: no red", oid="abc123"),),
            runner=_Runner(),
        )
        == frozenset()
    )
    assert (
        module._green_exempt_oids(
            repo=Path("/repo"),
            commits=(red_only,),
            runner=_Runner([_result(exit_code=1)]),
        )
        == frozenset()
    )
    assert (
        module._green_exempt_oids(
            repo=Path("/repo"),
            commits=(red_only,),
            runner=_Runner(
                [_result(stdout='{"nameWithOwner": "owner/repo"}'), _result(exit_code=1)]
            ),
        )
        == frozenset()
    )
