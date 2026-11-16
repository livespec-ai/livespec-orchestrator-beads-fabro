"""The codex full-access gate fleet-lists an adopter under its RESOLVED owner.

livespec v247 (the fleet membership contract in non-functional-requirements.md)
ratified that an adopter resolves as `<adopter.owner or adopter_owner or
owner>/<repo>`, while a `fleet`-array member resolves under `owner` alone.
Before bd-ib-2sdcgk the gate listed every adopter under the manifest `owner`
only, so once the fleet owner moves to a new organization an adopter still
owned elsewhere would refresh its marker to `fleet_listed: false` and Codex
full access would silently turn off there.

The pinned livespec-dev-tooling `Manifest` may not carry the adopter owner
keys yet, so the gate reads them from the raw manifest itself; these tests
drive the real parser and never spawn subprocesses.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_PATH = _REPO_ROOT / ".claude-plugin" / "hooks" / "codex_yolo_gate.py"
_MODULE_NAME = "codex_yolo_gate_adopter_owner_under_test"


def _load_hook() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _HOOK_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


hook = _load_hook()


def _manifest(*, adopter_owner: str | None, per_adopter_owner: str | None) -> str:
    adopter_owner_line = "" if adopter_owner is None else f'  "adopter_owner": "{adopter_owner}",\n'
    per_adopter_field = "" if per_adopter_owner is None else f', "owner": "{per_adopter_owner}"'
    return (
        "{\n"
        '  "owner": "livespec-ai",\n'
        f"{adopter_owner_line}"
        '  "fleet": [\n'
        '    {"repo": "livespec", "class": "core"}\n'
        "  ],\n"
        '  "adopters": [\n'
        '    {"repo": "plain-adopter", "profile": ["baseline"], "posture": "pinned"},\n'
        '    {"repo": "owned-adopter", "profile": ["baseline"], "posture": "pinned"'
        f"{per_adopter_field}}}\n"
        "  ]\n"
        "}\n"
    )


def _listed(*, source: str, owner: str, repo: str) -> bool:
    return hook.derive_fleet_listed(manifest_source=source, owner=owner, repo=repo)


def test_adopter_is_listed_under_adopter_owner() -> None:
    source = _manifest(adopter_owner="thewoolleyman", per_adopter_owner=None)

    assert _listed(source=source, owner="thewoolleyman", repo="plain-adopter") is True
    assert _listed(source=source, owner="livespec-ai", repo="plain-adopter") is False


def test_per_adopter_owner_overrides_adopter_owner() -> None:
    source = _manifest(adopter_owner="thewoolleyman", per_adopter_owner="mi-homelab")

    assert _listed(source=source, owner="mi-homelab", repo="owned-adopter") is True
    assert _listed(source=source, owner="thewoolleyman", repo="owned-adopter") is False
    assert _listed(source=source, owner="thewoolleyman", repo="plain-adopter") is True


def test_adopter_name_under_a_different_owner_is_not_listed() -> None:
    source = _manifest(adopter_owner="thewoolleyman", per_adopter_owner="mi-homelab")

    assert _listed(source=source, owner="someone-else", repo="owned-adopter") is False
    assert _listed(source=source, owner="someone-else", repo="plain-adopter") is False


def test_fleet_member_is_listed_only_under_the_manifest_owner() -> None:
    source = _manifest(adopter_owner="thewoolleyman", per_adopter_owner="mi-homelab")

    assert _listed(source=source, owner="livespec-ai", repo="livespec") is True
    assert _listed(source=source, owner="thewoolleyman", repo="livespec") is False
    assert _listed(source=source, owner="mi-homelab", repo="livespec") is False


def test_without_owner_overrides_adopters_resolve_under_owner_as_before() -> None:
    source = _manifest(adopter_owner=None, per_adopter_owner=None)

    assert _listed(source=source, owner="livespec-ai", repo="plain-adopter") is True
    assert _listed(source=source, owner="livespec-ai", repo="owned-adopter") is True
    assert _listed(source=source, owner="thewoolleyman", repo="plain-adopter") is False


def test_non_string_owner_overrides_are_ignored() -> None:
    source = (
        "{\n"
        '  "owner": "livespec-ai",\n'
        '  "adopter_owner": 7,\n'
        '  "fleet": [],\n'
        '  "adopters": [\n'
        '    {"repo": "plain-adopter", "profile": ["baseline"], "posture": "pinned",'
        ' "owner": ["not", "a", "string"]}\n'
        "  ]\n"
        "}\n"
    )

    assert _listed(source=source, owner="livespec-ai", repo="plain-adopter") is True


def test_owner_overrides_unreadable_by_the_gate_fall_back_to_owner() -> None:
    """A block comment parses for the core parser but not the gate's raw read.

    The raw read then yields no overrides, and every adopter resolves under
    `owner` exactly as before, rather than crashing the refresh.
    """
    source = (
        "{ /* block comment */\n"
        '  "owner": "livespec-ai",\n'
        '  "adopter_owner": "thewoolleyman",\n'
        '  "fleet": [],\n'
        '  "adopters": [\n'
        '    {"repo": "plain-adopter", "profile": ["baseline"], "posture": "pinned"}\n'
        "  ]\n"
        "}\n"
    )

    assert _listed(source=source, owner="livespec-ai", repo="plain-adopter") is True
    assert _listed(source=source, owner="thewoolleyman", repo="plain-adopter") is False


def test_refresh_writes_true_for_an_adopter_under_adopter_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = tmp_path / "manifest.jsonc"
    _ = manifest.write_text(
        _manifest(adopter_owner="thewoolleyman", per_adopter_owner=None), encoding="utf-8"
    )
    _ = (tmp_path / hook.CONFIG_FILENAME).write_text(
        '{\n  "implementation": {"plugin": "x"}\n}\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(hook, "resolve_owner", lambda **_kwargs: "thewoolleyman")
    monkeypatch.setattr(
        hook,
        "remote_url_for_repo",
        lambda **_kwargs: "https://github.com/thewoolleyman/plain-adopter.git",
    )

    assert hook.main(argv=["refresh", str(manifest)]) == 0

    assert hook.read_marker(repo=tmp_path) is True
