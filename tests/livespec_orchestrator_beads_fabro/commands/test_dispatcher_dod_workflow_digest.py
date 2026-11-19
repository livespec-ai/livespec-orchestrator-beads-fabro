"""The workflow-graph digest fails closed when the committed graph is unreadable."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_dod_workflow_digest as workflow_digest,
)


@pytest.mark.parametrize("failure", [("manifest",), ("graph",), ("contents",)])
def test_an_unreadable_workflow_input_has_no_reusable_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Each read failure invalidates an older judgement receipt."""
    manifest = tmp_path / "workflow.toml"
    manifest.write_text("[workflow]\n", encoding="utf-8")
    graph = tmp_path / "workflow.fabro"
    if failure == "manifest":
        manifest = tmp_path / "missing.toml"
    elif failure == "contents":
        graph = tmp_path / "missing.fabro"
    monkeypatch.setattr(workflow_digest, "workflow_toml", lambda **_kwargs: manifest)
    monkeypatch.setattr(
        workflow_digest,
        "workflow_graph_path",
        lambda **_kwargs: None if failure == "graph" else graph,
    )

    assert (
        workflow_digest.workflow_graph_digest(repo=tmp_path, item_id="bd-ib-gmukke") == "unreadable"
    )


def test_a_readable_committed_graph_uses_its_bytes_as_the_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The successful arm keys reuse on the graph that will actually execute."""
    manifest = tmp_path / "workflow.toml"
    graph = tmp_path / "workflow.fabro"
    graph_bytes = b"digraph { pre_ticket -> dod_gate }\n"
    manifest.write_text("[workflow]\n", encoding="utf-8")
    graph.write_bytes(graph_bytes)
    monkeypatch.setattr(workflow_digest, "workflow_toml", lambda **_kwargs: manifest)
    monkeypatch.setattr(workflow_digest, "workflow_graph_path", lambda **_kwargs: graph)

    assert (
        workflow_digest.workflow_graph_digest(repo=tmp_path, item_id="bd-ib-gmukke")
        == hashlib.sha256(graph_bytes).hexdigest()
    )
