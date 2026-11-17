"""The fleet owner defaults name `livespec-ai`, with the old owner only as a resolver fallback."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_RESOLVER = _ROOT / ".claude-plugin" / ".pi-plugin" / "lib" / "resolve-plugin-root.sh"
_PLUGIN = "livespec-orchestrator-beads-fabro"
_FORMER_ACCOUNT = "thewoolleyman"


def _make_clone(home: Path, owner: str) -> Path:
    root = home / ".pi" / "agent" / "git" / "github.com" / owner / _PLUGIN / ".claude-plugin"
    (root / "scripts" / "bin").mkdir(parents=True)
    (root / "plugin.json").write_text(json.dumps({"name": _PLUGIN}), encoding="utf-8")
    return root


def _resolve(home: Path, project: Path) -> subprocess.CompletedProcess[str]:
    env = {"PATH": os.environ["PATH"], "HOME": str(home)}
    return subprocess.run(
        ["bash", str(_RESOLVER), str(project)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_resolver_finds_a_clone_made_from_the_new_owner(tmp_path: Path) -> None:
    clone = _make_clone(tmp_path / "home", "livespec-ai")
    (tmp_path / "project").mkdir()
    done = _resolve(tmp_path / "home", tmp_path / "project")
    assert done.stdout.strip() == str(clone)


def test_resolver_still_finds_a_clone_made_from_the_old_owner(tmp_path: Path) -> None:
    clone = _make_clone(tmp_path / "home", "thewoolleyman")
    (tmp_path / "project").mkdir()
    done = _resolve(tmp_path / "home", tmp_path / "project")
    assert done.stdout.strip() == str(clone)


def test_resolver_prefers_the_new_owner_when_both_clones_exist(tmp_path: Path) -> None:
    _make_clone(tmp_path / "home", "thewoolleyman")
    new = _make_clone(tmp_path / "home", "livespec-ai")
    (tmp_path / "project").mkdir()
    done = _resolve(tmp_path / "home", tmp_path / "project")
    assert done.stdout.strip() == str(new)


def test_resolver_install_hint_names_the_new_owner(tmp_path: Path) -> None:
    (tmp_path / "home").mkdir()
    (tmp_path / "project").mkdir()
    done = _resolve(tmp_path / "home", tmp_path / "project")
    assert done.returncode == 1
    assert f"pi install git:github.com/livespec-ai/{_PLUGIN}@release -l" in done.stderr


def test_preserve_default_fleet_list_is_owned_by_livespec_ai() -> None:
    text = (_ROOT / "dev-tooling" / "preserve" / "preserve_runs.sh").read_text(encoding="utf-8")
    assert '"${PRESERVE_OWNER:-livespec-ai}"' in text
    assert f"github.com/{_FORMER_ACCOUNT}" not in text


def test_real_work_dispatch_defaults_to_the_new_owner() -> None:
    text = (_ROOT / "orchestrator-image" / "real-work-dispatch.sh").read_text(encoding="utf-8")
    assert 'DISPATCHER_ORG="${DISPATCHER_ORG:-livespec-ai}"' in text
    assert 'TARGET_ORG="${TARGET_ORG:-$DISPATCHER_ORG}"' in text
    assert "Default: thewoolleyman" not in text
