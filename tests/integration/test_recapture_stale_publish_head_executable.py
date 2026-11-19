"""A stale declared publish head is detected by EXECUTING the recapture route.

Work-item `bd-ib-chonmf`. The proof-capture prompt carries the duty to re-read the
forge head immediately before posting, and a prompt test binds those bytes. A
prompt cannot show that the run stops spending recapture laps on a head review has
already moved past, so this file executes the committed `recapture_route` and
`non_converged` scripts in a throwaway git repository whose `gh` is a stub serving
a canned pull-request comment list.

The scenario is the measured one (run 01M6HRC0N1QAHKNNRBJFFS25XY): the captured
record declares head H1, a `review_fix` commit then moves HEAD to H2 with a
different tree, and review keeps raising "declared publish head differs from
reviewed HEAD".

- (i) The first lap against the stale head is allowed and tells the capture to
  declare the FRESH head; when the recaptured record declares that fresh head (the
  same tree as HEAD) the next lap proceeds and the stale-head record is cleared.
- (ii) When the recapture declares the SAME stale head H1 again, the route does not
  enter `proof_capture` a second time: it exits non-zero, and the terminal names
  the stale-head cause distinctly from an unconverged proof.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._dispatcher_dot_graph import parse_dot_graph
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_state import (
    PUBLICATION_STATE_GIT_PATH,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_GRAPH = (
    _REPO_ROOT
    / ".claude-plugin"
    / ".fabro"
    / "workflows"
    / "implement-work-item"
    / "workflow.fabro"
)
_STALE_CAUSE = "STALE_PUBLISH_HEAD"
_EXHAUSTED_MARKER = "LIVESPEC_RECAPTURE_EXHAUSTED"

_GH_STUB = """#!/usr/bin/env python3
import json, os, re, sys

# Mirrors, in Python, what gh's built-in --jq yields for the route's declared-head
# filter, because the gate's sandboxes carry no jq binary. The filter text itself is
# run with the real jq by the last test in this file wherever jq exists.
if sys.argv[1:3] == ["pr", "list"]:
    print(7)
elif sys.argv[1:3] == ["pr", "view"]:
    comments = json.load(open(os.environ["STUB_COMMENTS"]))["comments"]
    bodies = [
        c["body"] for c in comments
        if "Publish-branch head:" in c["body"] and not c["body"].startswith("Review findings")
    ]
    found = re.search(r"Publish-branch head:[ `]*([0-9a-fA-F]{40})", bodies[-1]) if bodies else None
    if found:
        print(found.group(1))
"""


def _script(*, node: str) -> str:
    parsed = parse_dot_graph(text=_GRAPH.read_text(encoding="utf-8"))
    assert not isinstance(parsed, str), parsed
    return parsed.nodes[node]["script"]


def _git(*, repo: Path, args: list[str]) -> str:
    done = subprocess.run(
        ["git", "-c", "user.email=t@example.test", "-c", "user.name=t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


def _commit(*, repo: Path, name: str, text: str) -> str:
    (repo / name).write_text(text, encoding="utf-8")
    _git(repo=repo, args=["add", name])
    _git(repo=repo, args=["commit", "--quiet", "-m", f"change {name}"])
    return _git(repo=repo, args=["rev-parse", "HEAD"])


class _Run:
    """One throwaway repository, its `gh` stub, and the heads H1 (stale) and H2 (HEAD)."""

    def __init__(self, *, tmp_path: Path) -> None:
        self.repo = tmp_path / "clone"
        self.repo.mkdir()
        _git(repo=self.repo, args=["init", "--quiet"])
        self.stale = _commit(repo=self.repo, name="a.txt", text="published\n")
        self.fresh = _commit(repo=self.repo, name="b.txt", text="review_fix commit\n")
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        stub = bin_dir / "gh"
        stub.write_text(_GH_STUB, encoding="utf-8")
        stub.chmod(0o755)
        self._bin = bin_dir
        self._comments = tmp_path / "comments.json"
        self.declare(head=self.stale)

    def declare(self, *, head: str) -> None:
        """Make the newest captured record on the pull request declare `head`."""
        body = f"Proof of Done record\n\nPublish-branch head: {head}\n"
        self._comments.write_text(json.dumps({"comments": [{"body": body}]}), encoding="utf-8")

    def run(self, *, node: str) -> subprocess.CompletedProcess[str]:
        env = {
            **os.environ,
            "PATH": f"{self._bin}:{os.environ['PATH']}",
            "STUB_COMMENTS": str(self._comments),
            "LIVESPEC_PUBLISH_BRANCH": "run-branch",
        }
        return subprocess.run(
            ["sh", "-c", _script(node=node)],
            cwd=self.repo,
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )

    def state(self, *, name: str) -> Path:
        return self.repo / ".git" / PUBLICATION_STATE_GIT_PATH / name


def test_a_stale_declared_head_is_redeclared_as_the_fresh_head_and_then_converges(
    tmp_path: Path,
) -> None:
    """(i) The lap against H1 names H2 as the head to declare; a recapture of H2 converges."""
    run = _Run(tmp_path=tmp_path)

    first = run.run(node="recapture_route")

    assert first.returncode == 0, first.stderr
    assert _STALE_CAUSE in first.stderr, first.stderr
    assert run.stale in first.stderr and run.fresh in first.stderr, first.stderr
    assert run.state(name="livespec-recapture-stale-head").read_text().strip() == run.stale

    run.declare(head=run.fresh)
    second = run.run(node="recapture_route")

    assert second.returncode == 0, second.stderr
    assert _STALE_CAUSE not in second.stderr, second.stderr
    assert not run.state(name="livespec-recapture-stale-head").exists()


def test_a_second_recapture_against_the_same_stale_head_ends_naming_the_stale_cause(
    tmp_path: Path,
) -> None:
    """(ii) A repeat of H1 never re-enters proof_capture; the ending is not 'unconverged'."""
    run = _Run(tmp_path=tmp_path)
    first = run.run(node="recapture_route")
    assert first.returncode == 0, first.stderr

    second = run.run(node="recapture_route")

    assert second.returncode != 0, second.stderr
    assert _STALE_CAUSE in second.stderr, second.stderr
    assert "recapture lap 2 of 2" not in second.stderr, second.stderr

    terminal = run.run(node="non_converged")

    assert terminal.returncode != 0
    last = [line for line in terminal.stderr.splitlines() if _EXHAUSTED_MARKER in line][-1]
    assert _STALE_CAUSE in last, terminal.stderr
    assert run.stale in last and run.fresh in last, last
    assert "recurring proof-record findings" not in terminal.stderr, terminal.stderr


@pytest.mark.skipif(shutil.which("jq") is None, reason="needs the jq binary")
def test_the_routes_declared_head_filter_reads_the_newest_non_review_record(
    tmp_path: Path,
) -> None:
    """The jq text the route hands gh yields the sha of the newest record naming a head."""
    found = re.search(r"--jq '(\[\.comments\[\]\.body.*?\| \.h)'", _script(node="recapture_route"))
    assert found is not None
    sha = "a" * 40
    comments = tmp_path / "comments.json"
    comments.write_text(
        json.dumps(
            {
                "comments": [
                    {"body": f"Publish-branch head: {'b' * 40}\n"},
                    {"body": f"Proof of Done\n\nPublish-branch head: `{sha}`\n"},
                    {"body": f"Review findings\n\nPublish-branch head: {'c' * 40}\n"},
                ]
            }
        ),
        encoding="utf-8",
    )

    done = subprocess.run(
        ["jq", "-r", found.group(1), str(comments)], check=True, capture_output=True, text=True
    )

    assert done.stdout.strip() == sha
