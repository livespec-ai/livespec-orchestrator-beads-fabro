"""Regression coverage for fleet-launch host-capture build lookup."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_MODULE_PATH = _REPO_ROOT / "fleet-launch" / "_capture_evidence.py"
_MODULE_NAME = "fleet_launch_capture_evidence_under_test"


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


def test_installed_build_matches_a_symlinked_repository_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = _module()
    repository = tmp_path / "projects" / "orchestrator"
    repository.mkdir(parents=True)
    symlink = tmp_path / "workspace" / "orchestrator"
    symlink.parent.mkdir()
    symlink.symlink_to(repository, target_is_directory=True)
    registry = tmp_path / "installed_plugins.json"
    registry.write_text(
        json.dumps(
            {
                "plugins": {
                    evidence.PLUGIN_KEY: [
                        {"version": "symlinked-build", "projectPath": str(repository)}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(evidence, "PLUGIN_REGISTRY", registry)

    assert evidence.installed_build(repo=symlink) == "symlinked-build"


def test_installed_build_names_lookup_inputs_when_repository_is_unregistered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence = _module()
    repository = tmp_path / "repository"
    repository.mkdir()
    registry = tmp_path / "installed_plugins.json"
    registry.write_text(
        json.dumps(
            {
                "plugins": {
                    evidence.PLUGIN_KEY: [
                        {"version": "missing-project-path"},
                        {"version": "other", "projectPath": str(tmp_path)},
                    ]
                }
            },
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(evidence, "PLUGIN_REGISTRY", registry)

    with pytest.raises(evidence.RefusedError) as raised:
        evidence.installed_build(repo=repository)

    assert str(repository) in str(raised.value)
    assert str(registry) in str(raised.value)
    assert evidence.PLUGIN_KEY in str(raised.value)


def test_sh_returns_a_stripped_command_stdout(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = _module()
    called: dict[str, object] = {}

    def fake_run(*_args: object, **kwargs: object) -> object:
        called["argv"] = list(_args[0])
        called.update(kwargs)
        return type("Result", (), {"stdout": " output\n"})()

    monkeypatch.setattr(evidence.subprocess, "run", fake_run)

    assert evidence.sh(argv=["tool", "argument"], cwd=tmp_path) == "output"
    assert called == {
        "argv": ["tool", "argument"],
        "cwd": tmp_path,
        "capture_output": True,
        "text": True,
        "check": False,
    }


def test_resolve_server_reads_the_default_factory_and_registry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = _module()
    (tmp_path / ".livespec.jsonc").write_text('{"default_factory": "petri"}', encoding="utf-8")
    registry = tmp_path / "factories.json"
    registry.write_text(json.dumps({"petri": {"server": "http://factory"}}), encoding="utf-8")
    monkeypatch.setattr(evidence, "REGISTRY", registry)
    monkeypatch.setattr(evidence, "PETRI_CLIENT", "fabro")

    assert evidence.resolve_server(repo=tmp_path) == ("petri", "http://factory", "fabro")


def test_resolve_server_refuses_missing_factory_or_registry_entry(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = _module()
    registry = tmp_path / "factories.json"
    registry.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(evidence, "REGISTRY", registry)

    (tmp_path / ".livespec.jsonc").write_text("{}", encoding="utf-8")
    with pytest.raises(evidence.RefusedError, match="no dispatcher.default_factory"):
        evidence.resolve_server(repo=tmp_path)

    (tmp_path / ".livespec.jsonc").write_text('{"default_factory": "petri"}', encoding="utf-8")
    with pytest.raises(evidence.RefusedError, match="petri does not resolve"):
        evidence.resolve_server(repo=tmp_path)


def test_release_containment_reports_a_remote_release_tag(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = _module()
    responses = iter(("", "v1.2.3", "deadbeef\trefs/tags/v1.2.3", "release-commit"))
    monkeypatch.setattr(evidence, "sh", lambda **_kwargs: next(responses))

    assert evidence.release_containment(
        repo=tmp_path, slug="owner/repository", merge="merge-commit", head_arg="unused"
    ) == (
        "v1.2.3",
        "release-commit",
        "first release tag: v1.2.3 -> release-commit; on origin: deadbeef",
    )


def test_release_containment_refuses_a_tag_absent_from_the_remote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = _module()
    responses = iter(("", "v1.2.3", ""))
    monkeypatch.setattr(evidence, "sh", lambda **_kwargs: next(responses))

    with pytest.raises(evidence.RefusedError, match="tag v1.2.3 is not on the forge remote"):
        evidence.release_containment(
            repo=tmp_path, slug="owner/repository", merge="merge-commit", head_arg="unused"
        )


def test_release_containment_refuses_a_missing_exercised_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = _module()
    responses = iter(("", ""))
    monkeypatch.setattr(evidence, "sh", lambda **_kwargs: next(responses))

    with pytest.raises(evidence.RefusedError, match="pass the exercised master head"):
        evidence.release_containment(
            repo=tmp_path, slug="owner/repository", merge="merge-commit", head_arg=""
        )


def test_release_containment_reports_an_exercised_default_branch_head(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = _module()
    responses = iter(("", "", "exercised-commit", "origin/master"))
    monkeypatch.setattr(evidence, "sh", lambda **_kwargs: next(responses))
    monkeypatch.setattr(
        evidence.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": 0})(),
    )

    assert evidence.release_containment(
        repo=tmp_path,
        slug="owner/repository",
        merge="merge-commit",
        head_arg="exercised-head",
    ) == (
        "none",
        "exercised-commit",
        "no release tag contains it (none cut for this change); exercised origin/master commit "
        "exercised-commit; merge-base --is-ancestor merge-commit exercised-co: exit 0",
    )


@pytest.mark.parametrize(
    ("ancestry_status", "branches", "message"),
    [
        (1, "", "exercised head exercised-commit does not contain merge merge-commit"),
        (0, "origin/other", "exercised head exercised-commit is not on origin/master"),
    ],
)
def test_release_containment_refuses_invalid_exercised_heads(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    ancestry_status: int,
    branches: str,
    message: str,
) -> None:
    evidence = _module()
    responses = iter(("", "", "exercised-commit", branches))
    monkeypatch.setattr(evidence, "sh", lambda **_kwargs: next(responses))
    monkeypatch.setattr(
        evidence.subprocess,
        "run",
        lambda *_args, **_kwargs: type("Result", (), {"returncode": ancestry_status})(),
    )

    with pytest.raises(evidence.RefusedError, match=message):
        evidence.release_containment(
            repo=tmp_path,
            slug="owner/repository",
            merge="merge-commit",
            head_arg="exercised-head",
        )


def test_journal_rows_selects_the_last_matching_dispatch_rows(tmp_path: Path) -> None:
    evidence = _module()
    journal = tmp_path / evidence.JOURNAL
    journal.parent.mkdir()
    journal.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                {"dispatch_id": "other", "stage": "dispatch-id", "dispatch_factory": "petri"},
                {"dispatch_id": "wanted", "stage": "ignored", "dispatch_factory": "petri"},
                {
                    "dispatch_id": "wanted",
                    "stage": "dispatch-id",
                    "dispatch_factory": "petri",
                    "invoker": "launcher",
                },
                {
                    "dispatch_id": "wanted",
                    "stage": "dispatch-run-stamp",
                    "dispatch_factory": "petri",
                    "dispatch_factory_server": "http://factory",
                    "extra": "omitted",
                },
            )
        ),
        encoding="utf-8",
    )

    assert evidence.journal_rows(repo=tmp_path, dispatched="wanted", server="http://factory") == [
        {
            "stage": "dispatch-id",
            "dispatch_id": "wanted",
            "dispatch_factory": "petri",
            "invoker": "launcher",
        },
        {
            "stage": "dispatch-run-stamp",
            "dispatch_id": "wanted",
            "dispatch_factory": "petri",
            "dispatch_factory_server": "http://factory",
        },
    ]


@pytest.mark.parametrize(
    ("rows", "server"),
    [
        ([], "http://factory"),
        ([{"stage": "dispatch-run-stamp", "dispatch_factory_server": "other"}], "http://factory"),
    ],
)
def test_journal_rows_refuses_missing_or_mismatched_stamp(
    tmp_path: Path, rows: list[dict[str, str]], server: str
) -> None:
    evidence = _module()
    journal = tmp_path / evidence.JOURNAL
    journal.parent.mkdir()
    for row in rows:
        row["dispatch_id"] = "wanted"
        row["dispatch_factory"] = "petri"
    journal.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    with pytest.raises(evidence.RefusedError, match="no dispatch-run-stamp row"):
        evidence.journal_rows(repo=tmp_path, dispatched="wanted", server=server)


def test_launcher_log_returns_empty_when_no_gate_is_found(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = _module()
    monkeypatch.delenv("LAUNCHER_LOG", raising=False)
    monkeypatch.setattr(evidence, "sh", lambda **_kwargs: "")

    assert evidence.launcher_log(dispatched="bd-ib-zvskul") == ""


@pytest.mark.parametrize(("gate", "expected_calls"), [("/tmp/gate.log", 1), ("", 2)])
def test_launcher_log_reads_the_selected_gate(
    monkeypatch: pytest.MonkeyPatch, gate: str, expected_calls: int
) -> None:
    evidence = _module()
    calls: list[list[str]] = []

    def fake_sh(*, argv: list[str], **_kwargs: object) -> str:
        calls.append(argv)
        return "captured log" if gate or len(calls) > 1 else "/tmp/discovered.log"

    if gate:
        monkeypatch.setenv("LAUNCHER_LOG", gate)
    else:
        monkeypatch.delenv("LAUNCHER_LOG", raising=False)
    monkeypatch.setattr(evidence, "sh", fake_sh)

    assert evidence.launcher_log(dispatched="bd-ib-zvskul") == "captured log"
    assert len(calls) == expected_calls
    assert calls[-1][0:2] == ["bash", "-c"]


def test_first_host_captured_assertion_returns_the_first_bullet(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    evidence = _module()
    monkeypatch.setattr(
        evidence,
        "sh",
        lambda **_kwargs: json.dumps(
            [
                {
                    "description": "before\n### Host-captured\nintro\n- first assertion\n- second assertion"
                }
            ]
        ),
    )

    assert (
        evidence.first_host_captured_assertion(repo=tmp_path, item="bd-ib-zvskul")
        == "first assertion"
    )
