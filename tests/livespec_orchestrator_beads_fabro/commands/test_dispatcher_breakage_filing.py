"""Ledger-side coverage for the scheduled-workflow breakage pass."""

# ruff: noqa: SLF001

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands import _dispatcher_breakage_filing as filing
from livespec_orchestrator_beads_fabro.commands import _dispatcher_breakage_pass as passed
from livespec_orchestrator_beads_fabro.errors import ConnectionPrefixMissingError
from livespec_orchestrator_beads_fabro.types import StoreConfig
from returns.io import IOFailure, IOSuccess


def _config() -> StoreConfig:
    return StoreConfig(
        tenant="breakage", prefix="bd-ib", server_user="breakage", database="breakage", bd_path="bd"
    )


@dataclass
class _Client:
    records: list[dict[str, object]] = field(default_factory=list)
    updates: list[dict[str, object]] = field(default_factory=list)
    fail_update: bool = False

    def list_issues(self) -> list[dict[str, object]]:
        return self.records

    def update_issue(self, **kwargs: object) -> None:
        if self.fail_update:
            raise OSError("unreachable")
        self.updates.append(kwargs)


def _context(*, client: _Client | None = None) -> filing.FilingContext:
    return filing.FilingContext(config=_config(), client=client, existing={})


def _file_job(**kwargs: object) -> tuple[str | None, str | None]:
    return filing.file_job(
        context=kwargs["context"],  # type: ignore[arg-type]
        workflow="nightly.yml",
        job=kwargs.get("job", {"name": "tests", "steps": []}),  # type: ignore[arg-type]
        url="https://run",
        head_sha="abc",
        tests=(),
        breakage_key="nightly.yml:tests:abc",
        capture=kwargs.get("capture", lambda **_: IOSuccess("ready")),  # type: ignore[arg-type]
    )


def test_context_indexes_closed_records_and_reports_ledger_errors(
    monkeypatch, tmp_path: Path
) -> None:
    client = _Client(
        records=[
            {"id": "closed", "metadata": {"breakage_key": "nightly.yml:tests:abc"}},
            {"id": 3, "metadata": {"breakage_key": "ignored"}},
            {"id": "ignored", "metadata": "bad"},
        ]
    )
    monkeypatch.setattr(filing, "make_beads_client", lambda **_: client)
    context, problem = filing.context(repo=tmp_path, resolve_config=lambda **_: _config())
    assert problem is None
    assert context is not None
    assert context.existing == {"nightly.yml:tests:abc": "closed"}

    assert filing.context(
        repo=tmp_path,
        resolve_config=lambda **_: (_ for _ in ()).throw(ConnectionPrefixMissingError()),
    ) == (None, None)
    context, problem = filing.context(
        repo=tmp_path, resolve_config=lambda **_: (_ for _ in ()).throw(OSError("no tenant"))
    )
    assert context is None
    assert problem == "ledger: no tenant"
    context, problem = filing.context(repo=tmp_path, resolve_config=lambda **_: object())
    assert problem is None
    assert context is not None
    assert context.client is None
    client.records = []
    monkeypatch.setattr(client, "list_issues", lambda: (_ for _ in ()).throw(OSError("down")))
    context, problem = filing.context(repo=tmp_path, resolve_config=lambda **_: _config())
    assert context is None
    assert problem == "ledger dedupe: down"


def test_file_job_stamps_key_and_names_failed_step(monkeypatch) -> None:
    client = _Client()
    monkeypatch.setattr(filing, "new_work_item_id", lambda **_: "bd-ib-new")
    monkeypatch.setattr(filing, "utc_now_iso", lambda: "now")
    captured: list[object] = []
    item_id, problem = _file_job(
        context=_context(client=client),
        job={"name": "tests", "steps": [{"name": "unit", "conclusion": "failure"}]},
        capture=lambda **kwargs: captured.append(kwargs["item"]) or IOSuccess("ready"),
    )
    assert (item_id, problem) == ("bd-ib-new", None)
    assert client.updates == [
        {
            "issue_id": "bd-ib-new",
            "add_labels": ["breakage:nightly.yml"],
            "metadata": {"breakage_key": "nightly.yml:tests:abc"},
        }
    ]
    assert "failing step: unit" in captured[0].description


def test_file_job_refuses_bad_input_template_capture_and_annotation(monkeypatch) -> None:
    assert _file_job(context=_context(), job={}) == (None, "failed job has no name")
    monkeypatch.setattr(filing, "minijinja_openers_in_text", lambda **_: True)
    assert _file_job(context=_context())[1] == (
        "unfiled nightly.yml:tests:abc: description contains a template opener"
    )
    monkeypatch.setattr(filing, "minijinja_openers_in_text", lambda **_: False)
    assert _file_job(context=_context(), capture=lambda **_: IOFailure("no"))[1] == (
        "unfiled nightly.yml:tests:abc: capture work item was not routed"
    )
    client = _Client(fail_update=True)
    assert _file_job(context=_context(client=client))[1] == (
        "unfiled nightly.yml:tests:abc: record breakage key: unreachable"
    )
    assert (
        filing._failed_step(job={"steps": ["bad", {"name": "passed", "conclusion": "success"}]})
        == "unnamed failing step"
    )
    assert filing._failed_step(job={"steps": [{"name": None, "conclusion": "failure"}]}) == (
        "unnamed failing step"
    )
    assert filing._string(value=3) == "3"
    assert filing._string(value=None) == ""


def test_pass_reports_filing_errors_and_prior_closed_job(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    module = passed
    outcome = {"id": 1, "head_sha": "abc", "conclusion": "failure", "html_url": "https://run"}
    job = {"id": 2, "name": "tests", "conclusion": "failure"}
    monkeypatch.setattr(module.forge, "failed_jobs", lambda **_: [job])
    monkeypatch.setattr(module.forge, "job_log", lambda **_: "FAILED tests/test_one.py")
    context = _context()
    context.existing["nightly.yml:tests:abc"] = "closed"
    monkeypatch.setattr(module.filing, "context", lambda **_: (context, None))
    assert (
        module._emit_outcome(
            workflow="nightly.yml", outcome=outcome, repo=tmp_path, runner=object()
        )
        is False
    )
    assert "already-filed closed" in capsys.readouterr().out

    monkeypatch.setattr(module.filing, "context", lambda **_: (None, "ledger: no"))
    assert (
        module._emit_outcome(
            workflow="nightly.yml", outcome=outcome, repo=tmp_path, runner=object()
        )
        is True
    )
    assert "unreadable ledger: no" in capsys.readouterr().out
    assert module.breakage_key(workflow="nightly.yml", job_name="tests", head_sha="abc") == (
        "nightly.yml:tests:abc"
    )


def test_pass_covers_filing_terminal_paths_and_registration(
    monkeypatch, tmp_path: Path, capsys
) -> None:
    parser_names: list[str] = []
    handlers: dict[str, object] = {}
    passed.register_breakage_pass(
        add_parser=lambda name: parser_names.append(name) or argparse.ArgumentParser(),
        handlers=handlers,  # type: ignore[arg-type]
    )
    assert parser_names == ["breakage-pass"]
    assert handlers["breakage-pass"] is passed.run_breakage_pass_command

    outcome = {"id": 1, "head_sha": "abc", "conclusion": "failure", "html_url": "https://run"}
    monkeypatch.setattr(passed.filing, "context", lambda **_: (_context(), None))
    monkeypatch.setattr(passed.forge, "job_log", lambda **_: "FAILED tests/test_one.py")
    monkeypatch.setattr(passed.forge, "failed_jobs", lambda **_: [{"id": None, "name": "tests"}])
    assert passed._emit_outcome(
        workflow="nightly.yml", outcome=outcome, repo=tmp_path, runner=object()
    )
    assert "unreadable failed job" in capsys.readouterr().out

    monkeypatch.setattr(passed.forge, "failed_jobs", lambda **_: [{"id": 1, "name": "tests"}])
    monkeypatch.setattr(passed.forge, "job_log", lambda **_: None)
    assert passed._emit_outcome(
        workflow="nightly.yml", outcome=outcome, repo=tmp_path, runner=object()
    )
    assert "unreadable job log for tests" in capsys.readouterr().out

    monkeypatch.setattr(passed.forge, "job_log", lambda **_: "FAILED tests/test_one.py")
    monkeypatch.setattr(passed.filing, "file_job", lambda **_: (None, "capture refused"))
    assert passed._emit_outcome(
        workflow="nightly.yml", outcome=outcome, repo=tmp_path, runner=object()
    )
    assert "unreadable capture refused" in capsys.readouterr().out

    monkeypatch.setattr(passed.filing, "file_job", lambda **_: (None, None))
    assert not passed._emit_outcome(
        workflow="nightly.yml", outcome=outcome, repo=tmp_path, runner=object()
    )
    assert capsys.readouterr().out == ""

    monkeypatch.setattr(
        passed.forge,
        "failed_jobs",
        lambda **_: [{"id": 1, "name": "first"}, {"id": 2, "name": "second"}],
    )
    monkeypatch.setattr(passed.filing, "file_job", lambda **kwargs: (kwargs["job"]["name"], None))
    assert not passed._emit_outcome(
        workflow="nightly.yml", outcome=outcome, repo=tmp_path, runner=object()
    )
    assert "filed first, second" in capsys.readouterr().out


def test_file_job_stamps_key_even_when_capture_fails_after_creating_the_item(
    monkeypatch,
) -> None:
    monkeypatch.setattr(filing, "new_work_item_id", lambda **_: "bd-ib-new")
    stamp = {
        "issue_id": "bd-ib-new",
        "add_labels": ["breakage:nightly.yml"],
        "metadata": {"breakage_key": "nightly.yml:tests:abc"},
    }

    unrouted = _Client()
    assert _file_job(context=_context(client=unrouted), capture=lambda **_: IOFailure("no")) == (
        None,
        "unfiled nightly.yml:tests:abc: capture work item was not routed",
    )
    assert unrouted.updates == [stamp]

    def _raise(**_: object) -> IOSuccess[str]:
        raise OSError("annotation write failed")

    raised = _Client()
    assert _file_job(context=_context(client=raised), capture=_raise) == (
        None,
        "unfiled nightly.yml:tests:abc: capture work item: annotation write failed",
    )
    assert raised.updates == [stamp]

    both = _Client(fail_update=True)
    assert _file_job(context=_context(client=both), capture=lambda **_: IOFailure("no")) == (
        None,
        "unfiled nightly.yml:tests:abc: capture work item was not routed;"
        " record breakage key: unreachable",
    )
