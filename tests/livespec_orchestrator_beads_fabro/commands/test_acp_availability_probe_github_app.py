"""The GitHub App one confirmation turn authenticates its checkout as.

`SPECIFICATION/scenarios.md` "A shared server serves a run under the target's
per-run selected App" says a factory run authenticates as the App its factory
entry names, by secret name, and "An unresolvable per-run App selection ..."
says it never falls back to the server's global App. A confirmation turn is a
minimal factory run, so it carries the SAME `[run.integrations.github.app]`
selection a dispatch run does.

MEASURED 2026-11-17 (bd-ib-55wrbx): a probe that carried none made the server
resolve the repository's token through its machine-wide App, which does not
cover a repository the factory's own App serves, so every probe of that
repository died at environment acquisition and the admission refusal read
"no candidate remains" for every Claude-only node.

THE EXPECTATION IS READ THROUGH THE DISPATCH PATH'S OWN RENDERER
(`github_app_table`) and its own grade (`factory_github_app_refusal`) rather
than transcribed, so the probe and a dispatch cannot select different Apps for
one factory and still pass.
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_PACKAGE = "livespec_orchestrator_beads_fabro.commands"
_RUN_ID = "01M5PROBEAPP00000000000000"
_NOW = "2026-11-17T09:15:00Z"
_SERVER = "https://gmktec.example.ts.net:32276"
_APP = {"app_id_secret": "ORG_GITHUB_APP_ID", "private_key_secret": "/org/github/bot/private-key"}


def _config(**entry: Any) -> str:
    """One repository config declaring the `petri` factory with `entry`'s keys."""
    return json.dumps(
        {
            "livespec-orchestrator-beads-fabro": {
                "dispatcher": {
                    "default_factory": "petri",
                    "factories": {"petri": {"server": _SERVER, **entry}},
                }
            }
        }
    )


@dataclass(kw_only=True)
class _Command:
    exit_code: int
    stdout: str
    stderr: str = ""


@dataclass(kw_only=True)
class _Engine:
    """A fabro runner that records every argv and the manifest each launch read."""

    calls: list[list[str]] = field(default_factory=list)
    manifests: list[str] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: dict[str, str] | None = None,
    ) -> _Command:
        self.calls.append(list(argv))
        _ = (cwd, timeout_seconds, env)
        if "--version" in argv:
            return _Command(exit_code=0, stdout="fabro 0.254.0 (8869e88 2026-10-01)\n")
        if "inspect" in argv or "events" in argv:
            return _Command(exit_code=0, stdout="[]")
        if "run" in argv:
            self.manifests.append(Path(argv[argv.index("run") + 1]).read_text(encoding="utf-8"))
        return _Command(exit_code=0, stdout=f"Run: {_RUN_ID}\n")


def _candidate() -> Any:
    schema = importlib.import_module(f"{_PACKAGE}._acp_candidate_schema")
    adapters = importlib.import_module(f"{_PACKAGE}._acp_node_adapters")
    return schema.AcpCandidate(
        adapter=adapters.AcpAdapter(command="claude-code-acp"),
        identity=schema.AcpCandidateIdentity(
            display_name="Claude Opus 5",
            candidate_key="claude-opus-5-high",
            availability_key="anthropic",
        ),
    )


def _probe(*, tmp_path: Path, config: str, engine: _Engine) -> Any:
    _ = (tmp_path / ".livespec.jsonc").write_text(config, encoding="utf-8")
    runner = importlib.import_module(f"{_PACKAGE}._acp_availability_probe_run")
    return runner.run_availability_probe(
        repo=tmp_path,
        candidate=_candidate(),
        builtin=True,
        work_item_id="bd-ib-55wrbx",
        observation_ids=(),
        now_iso=_NOW,
        timeout_seconds=120,
        runner=engine,
    )


def _dispatch_path_table(*, repo: Path) -> str:
    """What the DISPATCH path renders for this repository's factory."""
    config = importlib.import_module(f"{_PACKAGE}._config")
    app = importlib.import_module(f"{_PACKAGE}._factory_github_app")
    factory = config.resolve_fabro_factory(cwd=repo)
    return app.github_app_table(github_app=factory.github_app)


def test_the_turn_selects_the_factorys_github_app_by_secret_name(tmp_path: Path) -> None:
    """The probe's manifest carries the dispatch path's own App selection."""
    engine = _Engine()

    result = _probe(tmp_path=tmp_path, config=_config(github_app=_APP), engine=engine)

    assert not isinstance(result, str), result
    (manifest,) = engine.manifests
    assert "[run.integrations.github.app]" in manifest, manifest
    assert f'app_id_secret = "{_APP["app_id_secret"]}"' in manifest, manifest
    assert f'private_key_secret = "{_APP["private_key_secret"]}"' in manifest, manifest
    assert _dispatch_path_table(repo=tmp_path) in manifest, manifest


def test_a_factory_declaring_no_github_app_renders_the_manifest_it_always_did(
    tmp_path: Path,
) -> None:
    """The control: an undeclared App adds nothing, so every other factory is unchanged."""
    engine = _Engine()
    probe = importlib.import_module(f"{_PACKAGE}._acp_availability_probe")

    result = _probe(tmp_path=tmp_path, config=_config(), engine=engine)

    assert not isinstance(result, str), result
    (manifest,) = engine.manifests
    assert "run.integrations" not in manifest, manifest
    assert manifest.startswith(probe.AVAILABILITY_PROBE_MANIFEST), manifest
    assert _dispatch_path_table(repo=tmp_path) == ""


def test_a_malformed_github_app_refuses_before_any_launch(tmp_path: Path) -> None:
    """The dispatch path's own refusal, naming the key, spends no run."""
    engine = _Engine()

    result = _probe(
        tmp_path=tmp_path,
        config=_config(github_app={"app_id_secret": "ORG_GITHUB_APP_ID"}),
        engine=engine,
    )

    assert isinstance(result, str), result
    assert "dispatcher.factories.petri.github_app" in result, result
    assert engine.manifests == [], engine.calls
