"""Command nodes of the implement-work-item workflow hold a credential only by contract (bd-ib-sgnfom).

`SPECIFICATION/contracts.md` section "Publication is mechanically confined to
the scripted publication stages" (Scenario 202) says the publication-capable
credentials are available only to the command stages `publish_draft`,
`pr_refresh` and `pr`, and to the preserving steps it names (`needs_human` and
the commit-settle steps that preserve a run's work). Every other command node
MUST hold none.

WHY THE WITHDRAWAL IS WRITTEN INTO EACH NODE'S SCRIPT. The run's credentials
ride the environment table of the run's environment, which reaches every node:
a command node has no environment of its own (measured on factory runs
01M7ZNN9F2DD and 01M7ZTRPE4SA, where removing the table's inputs starved the
publication and preservation steps, and keeping them left every node holding
them). So the per-node boundary is the node's own script, whose first statement
unsets every credential variable the overlay projects before any other command
of the node runs, repository hooks included.

THE NODES ARE DERIVED FROM THE GRAPH, not listed, so a command node added later
is withdrawn by default: a node that is neither a named holder nor a named
reader must carry the withdrawal. The two named sets are asserted exactly, so
moving a node between them is a visible change to this file.

THE READERS NO LONGER HOLD THE INPUTS (bd-ib-zf2kdh, INTERIM). The setup chain, `janitor`,
`proof_grade`, `pr_refresh_head`, `verify_pr`, `recapture_route` and `non_converged` read the forge
(`git fetch`, `git ls-remote`, `gh pr list`, `gh pr view`) through the refreshing `gh` wrapper. Each
now carries the same withdrawal as every other non-holder, and the wrapper mints their READ-ONLY
token from an owner-only inputs file the wrapper-install step wrote in the bundle root, a
coordinator ruling under R301 (2026-11-23) because the workflow launches no credential daemon yet.
`bd-ib-w64kr3` removes that file under the run-level daemon.

THE EXECUTION CASES RUN THE GRAPH'S OWN FIRST STATEMENT under real bash with the
real credential names in the environment and read the environment the next
command sees; none of them substitutes a fake.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    refreshing_gh_env_lines,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_secret_channel import (
    GITHUB_CREDENTIAL_ENV,
)

_GRAPH = (
    Path(__file__).resolve().parents[2]
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)

# Command nodes whose own contract is publication or preservation of the run's work.
_HOLDERS = frozenset(
    {
        "publish_draft",
        "pr_refresh",
        "pr",
        "needs_human",
        "fix_commit_settle",
        "review_fix_commit_settle",
    }
)
# Reader nodes are withdrawn like every other non-holder (bd-ib-zf2kdh, INTERIM); none is named.
_READERS: frozenset[str] = frozenset()
_CREDENTIAL_NAMES = frozenset(
    {
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "GITHUB_APP_ID",
        "GITHUB_PRIVATE_KEY",
        "GITHUB_APP_INSTALLATION_ID",
        "LIVESPEC_PUSH_TOKEN",
    }
)
_NODE_BLOCK = re.compile(r"^(\s{0,4})(\w+) \[\n(.*?)^\1\]\n", re.DOTALL | re.MULTILINE)
_SCRIPT = re.compile(r'^\s*script="(.+)"$', re.MULTILINE)


def _command_scripts() -> dict[str, str]:
    """Every command node's script text, as the shell receives it."""
    text = _GRAPH.read_text(encoding="utf-8")
    scripts: dict[str, str] = {}
    for block in _NODE_BLOCK.finditer(text):
        name, body = block.group(2), block.group(3)
        if "shape=parallelogram" not in body:
            continue
        script = _SCRIPT.search(body)
        if script is not None:
            scripts[name] = script.group(1).replace('\\"', '"').replace("\\\\", "\\")
    return scripts


def _first_statement(*, script: str) -> str:
    return script.split("; ", 1)[0] + ";"


def _withdrawn(*, scripts: dict[str, str]) -> dict[str, str]:
    return {name: s for name, s in scripts.items() if name not in _HOLDERS | _READERS}


def _credential_environment() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _CREDENTIAL_NAMES}
    env.update({name: f"secret-{name}" for name in _CREDENTIAL_NAMES})
    return env


def test_the_graph_names_every_holder_and_reader_it_derives_from() -> None:
    scripts = _command_scripts()

    assert set(scripts) >= _HOLDERS
    assert set(scripts) >= {f"run_prepare_{index}" for index in range(1, 10) if index != 5}
    assert set(scripts) >= {"setup_failed", "janitor", "proof_grade", "pr_refresh_head"}
    assert set(scripts) >= {"verify_pr", "recapture_route", "non_converged"}
    # run_prepare_5 writes a heredoc, which the one-line script reader skips; read its text.
    assert (
        'script="' + _first_statement(script=next(iter(_withdrawn(scripts=scripts).values())))
        in _GRAPH.read_text(encoding="utf-8").split("run_prepare_5 [", 1)[1].split("]\n", 1)[0]
    )
    assert len(_withdrawn(scripts=scripts)) >= 30


@pytest.mark.parametrize("node", sorted(_withdrawn(scripts=_command_scripts())))
def test_a_withdrawn_command_node_sees_no_credential_after_its_first_statement(node: str) -> None:
    script = _command_scripts()[node]

    result = subprocess.run(
        ["bash", "-c", f"{_first_statement(script=script)} env"],
        env=_credential_environment(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    seen = {line.split("=", 1)[0] for line in result.stdout.splitlines() if "=" in line}
    assert not seen & _CREDENTIAL_NAMES, f"{node} still holds {sorted(seen & _CREDENTIAL_NAMES)}"


@pytest.mark.parametrize("node", sorted(_HOLDERS))
def test_a_publication_or_preservation_node_withdraws_nothing(node: str) -> None:
    script = _command_scripts()[node]

    assert not script.startswith("unset ")
    assert "unset GITHUB_TOKEN GH_TOKEN" not in script


def test_the_withdrawal_names_every_credential_the_overlay_projects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_PRIVATE_KEY", "k")
    monkeypatch.setenv("GITHUB_APP_INSTALLATION_ID", "2")
    monkeypatch.setenv("GITHUB_API_URL", "https://api.github.com")
    projected = {line.split(" = ", 1)[0] for line in refreshing_gh_env_lines().splitlines()}
    projected.add(GITHUB_CREDENTIAL_ENV)
    projected -= {"GITHUB_API_URL"}
    withdrawn = _withdrawn(scripts=_command_scripts())
    statement = _first_statement(script=next(iter(withdrawn.values())))
    named = set(re.findall(r"\b[A-Z][A-Z_]+\b", statement))

    assert projected <= named
    assert named == _CREDENTIAL_NAMES


def test_every_withdrawn_node_carries_the_one_same_first_statement() -> None:
    withdrawn = _withdrawn(scripts=_command_scripts())
    statements = {_first_statement(script=script) for script in withdrawn.values()}

    assert len(statements) == 1
