"""A malformed owner override is absent, whichever way the pinned parser reads it.

livespec-dev-tooling v1.212 onward (commit 04997e0fb) makes `parse_manifest`
reject a WHOLE manifest, with `owner-not-string`, when `adopter_owner` or an
adopter's own `owner` is not a string; v1.211.0 accepted it. The gate's
contract (bd-ib-2sdcgk) is that such an override is ignored and the adopter
resolves under the manifest `owner`, so a rejection over one malformed optional
field must not turn Codex full access off. These tests pin that contract under a
parser that behaves like the newer one, so they hold at any livespec-dev-tooling
pin.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_PATH = _REPO_ROOT / ".claude-plugin" / "hooks" / "codex_yolo_gate.py"
_MODULE_NAME = "codex_yolo_gate_malformed_owner_override_under_test"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


class _Rejected:
    """The railway `Failure` shape `derive_fleet_listed` unwraps through `value_or`."""

    def value_or(self, default: object) -> object:
        return default


def _strict_parse_manifest(*, source: str) -> Any:
    """Reject a non-string owner override like livespec-dev-tooling v1.216.0 does."""
    root = json.loads(source)
    overrides = [root.get("adopter_owner")] + [
        entry.get("owner") for entry in root.get("adopters", [])
    ]
    if any(value is not None and not isinstance(value, str) for value in overrides):
        return _Rejected()
    return _real_parse_manifest(source=source)


_real_parse_manifest = hook.parse_manifest


@pytest.fixture(autouse=True)
def strict_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(hook, "parse_manifest", _strict_parse_manifest)


def _manifest(*, adopter_owner: object, per_adopter_owner: object) -> str:
    adopter: dict[str, object] = {"repo": "plain-adopter", "profile": ["baseline"]}
    adopter["posture"] = "pinned"
    if per_adopter_owner is not None:
        adopter["owner"] = per_adopter_owner
    root: dict[str, object] = {"owner": "livespec-ai", "fleet": [], "adopters": [adopter]}
    if adopter_owner is not None:
        root["adopter_owner"] = adopter_owner
    return json.dumps(root)


def _listed(*, source: str, owner: str) -> bool:
    return hook.derive_fleet_listed(manifest_source=source, owner=owner, repo="plain-adopter")


def test_the_strict_parser_stand_in_rejects_a_non_string_owner() -> None:
    source = _manifest(adopter_owner=7, per_adopter_owner=None)

    assert _strict_parse_manifest(source=source).value_or("rejected") == "rejected"


def test_a_non_string_adopter_owner_is_ignored_not_read_as_not_listed() -> None:
    source = _manifest(adopter_owner=7, per_adopter_owner=None)

    assert _listed(source=source, owner="livespec-ai") is True


def test_a_non_string_per_adopter_owner_is_ignored_not_read_as_not_listed() -> None:
    source = _manifest(adopter_owner=None, per_adopter_owner=["not", "a", "string"])

    assert _listed(source=source, owner="livespec-ai") is True


def test_a_valid_per_adopter_owner_still_wins_beside_a_malformed_adopter_owner() -> None:
    source = _manifest(adopter_owner=7, per_adopter_owner="thewoolleyman")

    assert _listed(source=source, owner="thewoolleyman") is True
    assert _listed(source=source, owner="livespec-ai") is False


def test_a_manifest_rejected_for_another_reason_is_still_not_listed() -> None:
    source = json.dumps({"owner": "livespec-ai", "fleet": "not-a-list", "adopters": []})

    assert _listed(source=source, owner="livespec-ai") is False


@pytest.mark.parametrize(
    "source",
    [
        "[]",
        '{ /* block comment */ "owner": "livespec-ai", "adopters": [] ',
        '{"owner": "livespec-ai", "adopters": 3}',
        '{"owner": "livespec-ai", "adopters": [7]}',
        '{"owner": "livespec-ai", "adopter_owner": "x", "adopters": [{"owner": "y"}]}',
    ],
)
def test_text_without_a_malformed_override_is_returned_for_the_parser_unchanged(
    source: str,
) -> None:
    assert hook._without_malformed_owner_overrides(manifest_source=source) == source  # noqa: SLF001


def test_both_malformed_overrides_are_dropped_and_nothing_else() -> None:
    source = _manifest(adopter_owner=7, per_adopter_owner=["x"])

    cleaned = json.loads(hook._without_malformed_owner_overrides(manifest_source=source))  # noqa: SLF001

    assert cleaned == {
        "owner": "livespec-ai",
        "fleet": [],
        "adopters": [{"repo": "plain-adopter", "profile": ["baseline"], "posture": "pinned"}],
    }
