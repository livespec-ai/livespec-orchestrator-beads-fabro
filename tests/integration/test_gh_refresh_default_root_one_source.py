"""Every shipped workflow resolves the gh-refresh bundle from ONE default root.

`DEFAULT_SANDBOX_GH_REFRESH_ROOT` moved from `/workspace/.livespec-gh-refresh` to
`${LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT:-$HOME/.claude/plugins}/livespec-gh-refresh`
(bd-ib-kzgpzm), but the workflow shell kept the old default, so on v0.341.0 and
v0.342.0 every `publish_draft` push() found no helper and refused with
`LIVESPEC_PUSH_AUTH_ABSENT` (bd-ib-2x6orj). Production never sets
`LIVESPEC_SANDBOX_GH_REFRESH_ROOT`, so the default IS the behaviour.

The first test EXECUTES each shipped `livespec_push` helper with the bundle only
at the new root; the second pins every default to the Python constant.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    DEFAULT_SANDBOX_GH_REFRESH_ROOT,
)

WORKFLOWS = (
    Path(".claude-plugin/.fabro/workflows/implement-work-item/workflow.fabro"),
    Path(".fabro/workflows/groom-work-item/workflow.fabro"),
)
_OLD_DEFAULT = "/workspace/.livespec-gh-refresh"
_PUSH_FUNCTION = re.compile(r"livespec_push\(\) \{.*?; \}; ", re.DOTALL)


def _push_nodes() -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for workflow in WORKFLOWS:
        graph = parse_dot_graph(text=workflow.read_text(encoding="utf-8"))
        assert not isinstance(graph, str), graph
        found.extend(
            (workflow, name)
            for name, attrs in graph.nodes.items()
            if "livespec_push()" in attrs.get("script", "")
        )
    return found


def test_the_shipped_workflows_ship_push_helpers_to_execute() -> None:
    assert len(_push_nodes()) >= 4


@pytest.mark.parametrize(("workflow", "node"), _push_nodes())
def test_livespec_push_finds_a_bundle_that_sits_only_at_the_new_default_root(
    workflow: Path, node: str, tmp_path: Path
) -> None:
    graph = parse_dot_graph(text=workflow.read_text(encoding="utf-8"))
    assert not isinstance(graph, str), graph
    function = _PUSH_FUNCTION.search(graph.nodes[node]["script"])
    assert function is not None
    plugins = tmp_path / "plugins"
    sentinel = tmp_path / "pushed"
    helper = plugins / "livespec-gh-refresh" / "bin" / "push_origin"
    helper.parent.mkdir(parents=True)
    _ = helper.write_text(f'#!/bin/sh\necho "$@" > {sentinel}\n', encoding="utf-8")
    helper.chmod(0o700)
    clone = tmp_path / "clone"
    clone.mkdir()
    _ = subprocess.run(["git", "init", "-q"], cwd=clone, check=True)
    _ = subprocess.run(
        ["git", "remote", "add", "origin", "https://example.invalid/origin.git"],
        cwd=clone,
        check=True,
    )

    result = subprocess.run(
        ["bash", "-c", f'{function.group(0)} livespec_push git push origin "refs/heads/x"'],
        cwd=clone,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": str(tmp_path / "home"),
            "GITHUB_APP_ID": "42",
            "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert "LIVESPEC_PUSH_AUTH_ABSENT" not in result.stderr, result.stderr
    assert result.returncode == 0, result.stderr
    assert sentinel.read_text(encoding="utf-8").split() == ["git", "push", "origin", "refs/heads/x"]


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_no_workflow_keeps_the_old_gh_refresh_default(workflow: Path) -> None:
    text = workflow.read_text(encoding="utf-8")

    assert _OLD_DEFAULT not in text
    assert DEFAULT_SANDBOX_GH_REFRESH_ROOT in text
