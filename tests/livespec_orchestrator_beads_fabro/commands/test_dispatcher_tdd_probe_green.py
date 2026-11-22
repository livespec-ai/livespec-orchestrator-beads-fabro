"""Green-only coverage for the commit-file evidence reader."""

# ruff: noqa: SLF001

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

_MODULE_NAME = "livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe"
_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_tdd_probe.py"
)


def _module() -> ModuleType:
    """Import the module under test, asserting it exists first."""
    assert _MODULE_PATH.is_file(), f"{_MODULE_PATH} does not exist yet"
    return importlib.import_module(_MODULE_NAME)


def test_commit_payload_reader_keeps_oids_and_rejects_invalid_container_shapes() -> None:
    """Only object/list commit payloads can supply per-commit file evidence."""
    module = _module()

    assert module._commits_from_payload(stdout="not json") is None
    assert module._commits_from_payload(stdout="[]") is None
    assert module._commits_from_payload(stdout='{"commits": {}}') is None

    commits = module._commits_from_payload(
        stdout=json.dumps(
            {
                "commits": [
                    {"messageHeadline": "good", "messageBody": "body", "oid": "abc123"},
                    {"messageHeadline": "no oid", "messageBody": None, "oid": ""},
                    {"messageHeadline": 7, "oid": "ignored"},
                    "ignored",
                ]
            }
        )
    )

    assert commits is not None
    assert [(commit.message, commit.oid) for commit in commits] == [
        ("good\n\nbody", "abc123"),
        ("no oid\n\n", None),
    ]
