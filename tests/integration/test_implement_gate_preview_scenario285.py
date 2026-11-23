"""Scenario 285 — an implement turn previews its prospective commit gate safely."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

from tests.prepare_step_support import env_of, steps_in

_ROOT = Path(__file__).parents[2]
_MODULE_PATH = (
    _ROOT
    / ".claude-plugin"
    / "scripts"
    / "livespec_orchestrator_beads_fabro"
    / "commands"
    / "_dispatcher_gate_preview_program.py"
)
_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_gate_preview_program"
_FAILED_TARGET = "check-keyword-only-args"


def _run(
    *, repo: Path, env: dict[str, str], argv: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Run one real repository command for the preview journey."""
    return subprocess.run(argv, cwd=repo, env=env, check=check, capture_output=True, text=True)


def _git(*, repo: Path, env: dict[str, str], argv: list[str]) -> str:
    """Run git successfully and return its standard output."""
    return _run(repo=repo, env=env, argv=["git", *argv]).stdout.strip()


def _environment(*, home: Path, plugins: Path) -> dict[str, str]:
    """Give the materialized program a clean, stable Git environment."""
    inherited = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("GIT_") and name != "COVERAGE_PROCESS_START"
    }
    return {
        **inherited,
        "HOME": str(home),
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": "Scenario Author",
        "GIT_AUTHOR_EMAIL": "author@example.invalid",
        "GIT_COMMITTER_NAME": "Scenario Author",
        "GIT_COMMITTER_EMAIL": "author@example.invalid",
        "LIVESPEC_SANDBOX_CLAUDE_PLUGINS_ROOT": str(plugins),
        "LIVESPEC_CHECK_SKIP": _FAILED_TARGET,
    }


def _preview_repository(*, tmp_path: Path, preview: Any) -> tuple[Path, Path, dict[str, str]]:
    """Build the real sandbox-shaped repository and materialize its preview program."""
    plugins = tmp_path / "plugins"
    repo = tmp_path / "repository"
    home = tmp_path / "home"
    repo.mkdir()
    home.mkdir()
    env = _environment(home=home, plugins=plugins)
    _ = _run(repo=repo, env=env, argv=["git", "init", "--quiet"])
    _ = (repo / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(repo=repo, env=env, argv=["add", "tracked.py"])
    _git(repo=repo, env=env, argv=["commit", "--quiet", "-m", "chore: baseline"])
    _ = (repo / "tracked.py").write_text("VALUE = 2\n", encoding="utf-8")
    _ = (repo / "created.py").write_text("VALUE = 3\n", encoding="utf-8")
    hook = repo / ".git" / "hooks" / "pre-commit"
    _ = hook.write_text(
        "#!/bin/sh\n"
        'if test -n "${LIVESPEC_CHECK_SKIP+x}"; then\n'
        "  printf 'preview inherited LIVESPEC_CHECK_SKIP\\n' >&2\n"
        "  exit 9\n"
        "fi\n"
        "for path in tracked.py created.py; do\n"
        '  git diff --cached --name-only | grep -qx "$path" || exit 8\n'
        "done\n"
        f"printf 'Failed targets (1):\\n  - {_FAILED_TARGET}\\n'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    steps = [
        step for step in steps_in(block=preview.gate_preview_prepare_steps_block()) if step.env
    ]
    assert len(steps) == 1
    materialized = _run(
        repo=repo,
        env=env_of(step=steps[0], base=env),
        argv=["sh", "-c", steps[0].script],
        check=False,
    )
    assert materialized.returncode == 0, materialized.stderr
    runner = plugins / preview.GATE_PREVIEW_PROGRAM_FILENAME
    return repo, runner, env


def test_gate_preview_runs_the_hook_against_a_disposable_staged_tree_and_unsets_skips(
    tmp_path: Path,
) -> None:
    """The inherited skip cannot hide a refusing target or mutate the real commit state."""
    assert _MODULE_PATH.is_file(), f"missing Dispatcher gate-preview program at {_MODULE_PATH}"
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    before_head = _git(repo=repo, env=env, argv=["rev-parse", "HEAD"])
    before_index = _git(repo=repo, env=env, argv=["hash-object", "--no-filters", ".git/index"])
    before_history = _git(repo=repo, env=env, argv=["log", "--format=%H"])

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    report = cast("dict[str, Any]", json.loads(completed.stdout.splitlines()[-1]))
    assert completed.returncode == 1
    assert report == {
        "failed_targets": [_FAILED_TARGET],
        "preview_ran": True,
        "status": 1,
        "unset_variables": ["LIVESPEC_CHECK_SKIP"],
    }
    assert env["LIVESPEC_CHECK_SKIP"] == _FAILED_TARGET
    assert _git(repo=repo, env=env, argv=["rev-parse", "HEAD"]) == before_head
    assert (
        _git(repo=repo, env=env, argv=["hash-object", "--no-filters", ".git/index"]) == before_index
    )
    assert _git(repo=repo, env=env, argv=["log", "--format=%H"]) == before_history
    assert _git(repo=repo, env=env, argv=["diff", "--cached", "--name-only"]) == ""
    assert (
        json.loads(
            (repo / ".git" / "livespec-implement-gate-preview-green-result.json").read_text(
                encoding="utf-8"
            )
        )
        == report
    )


def test_gate_preview_records_the_hook_output_tail_when_no_failed_target_summary_exists(
    tmp_path: Path,
) -> None:
    """An unstructured hook refusal retains its own diagnostic for Green's refusal."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'running staged-file pre-check'\n"
        "printf '%s\\n' 'type pre-check rejected created.py' >&2\n"
        "exit 23\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    report = cast("dict[str, Any]", json.loads(completed.stdout.splitlines()[-1]))
    assert completed.returncode == 23
    assert report["failed_targets"] == []
    assert report.get("output_tail", "").endswith("type pre-check rejected created.py\n")


def test_gate_preview_records_an_empty_output_tail_when_the_failing_hook_wrote_nothing(
    tmp_path: Path,
) -> None:
    """A silent non-zero hook still records an output tail, so the refusal can say so."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 23\n", encoding="utf-8")
    hook.chmod(0o755)

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    report = cast("dict[str, Any]", json.loads(completed.stdout.splitlines()[-1]))
    assert completed.returncode == 23
    assert report["failed_targets"] == []
    assert report["output_tail"] == ""


def test_gate_preview_redacts_credential_shaped_values_from_the_recorded_output_tail(
    tmp_path: Path,
) -> None:
    """A tokenized URL in the hook's output never reaches the durable preview record."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'fatal: unable to access https://x-access-token:s3cr3tvalue@github.com/o/r.git'\n"
        "printf '%s\\n' 'GH_TOKEN=ghp_abcdefghijklmnopqrstuvwxyz0123456789'\n"
        "printf '%s\\n' 'type pre-check rejected created.py' >&2\n"
        "exit 23\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    record = (repo / ".git" / "livespec-implement-gate-preview-green-result.json").read_text(
        encoding="utf-8"
    )
    report = cast("dict[str, Any]", json.loads(record))
    assert completed.returncode == 23
    assert "s3cr3tvalue" not in record
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in record
    assert "[redacted]" in report["output_tail"]
    assert report["output_tail"].endswith("type pre-check rejected created.py\n")


def test_green_preview_uses_the_implement_turns_affected_tests_gate(tmp_path: Path) -> None:
    """A one-module Green preview takes the hook's scoped route, not its full-suite route."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    (repo / "created.py").unlink()
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        'if test "${LIVESPEC_AUTHORING_TURN:-}" = implement; then\n'
        '  test "$(git diff --cached --name-only)" = tracked.py || exit 8\n'
        "  printf '%s\\n' 'affected-tests gate selected the changed modules'\n"
        "  exit 0\n"
        "fi\n"
        "printf '%s\\n' 'full pytest suite would run' >&2\n"
        "exit 9\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "affected-tests gate selected the changed modules" in completed.stdout
    assert "full pytest suite would run" not in completed.stderr


def test_green_preview_exposes_justs_exported_test_parallelism_to_the_hook(
    tmp_path: Path,
) -> None:
    """The preview and the commit gate give worker-sensitive tests one environment."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    (repo / "justfile").write_text('export test_nprocs := "6"\n', encoding="utf-8")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        'test "${test_nprocs:-}" = 6 || exit 23\n'
        "printf '%s\\n' 'hook received the declared test parallelism'\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "hook received the declared test parallelism" in completed.stdout


def test_gate_preview_trusts_its_worktree_before_running_the_hook(tmp_path: Path) -> None:
    """A generated mise config cannot block the prospective commit checks."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    mise = bin_dir / "mise"
    mise.write_text(
        "#!/bin/sh\n" 'test "$1" = trust\n' "touch .mise-trusted\n",
        encoding="utf-8",
    )
    mise.chmod(0o755)
    (repo / ".mise.toml").write_text("[tools]\n", encoding="utf-8")
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        "test -f .mise-trusted || exit 9\n"
        f"printf 'Failed targets (1):\\n  - {_FAILED_TARGET}\\n'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)
    env = {**env, "PATH": f"{bin_dir}:{env['PATH']}"}

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "failed_targets": [_FAILED_TARGET],
        "preview_ran": True,
        "status": 1,
        "unset_variables": ["LIVESPEC_CHECK_SKIP"],
    }


def test_gate_preview_reports_not_run_when_trusting_its_worktree_fails(tmp_path: Path) -> None:
    """A setup refusal is not misreported as a hook with no failed targets."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    mise = bin_dir / "mise"
    mise.write_text("#!/bin/sh\nprintf 'untrusted mise config\\n' >&2\nexit 17\n", encoding="utf-8")
    mise.chmod(0o755)
    env = {**env, "PATH": f"{bin_dir}:{env['PATH']}"}

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    assert completed.returncode == 17
    assert "untrusted mise config" in completed.stderr
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "failed_targets": [],
        "preview_ran": False,
        "status": 17,
        "unset_variables": ["LIVESPEC_CHECK_SKIP"],
    }


def test_green_preview_uses_the_pre_checkpoint_base(tmp_path: Path) -> None:
    """A Green checkpoint cannot hide the paths its amend will stage."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    checkpoint_env = env.copy()
    _ = checkpoint_env.pop("LIVESPEC_CHECK_SKIP")
    _git(repo=repo, env=env, argv=["add", "tracked.py", "created.py"])
    _git(
        repo=repo,
        env=checkpoint_env,
        argv=[
            "commit",
            "--quiet",
            "--no-verify",
            "-m",
            "fabro(run): green (success)",
            "-m",
            "Fabro-Run: run",
        ],
    )

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    assert completed.returncode == 1
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "failed_targets": [_FAILED_TARGET],
        "preview_ran": True,
        "status": 1,
        "unset_variables": ["LIVESPEC_CHECK_SKIP"],
    }


def test_green_preview_grades_its_latest_checkpoint_tree(tmp_path: Path) -> None:
    """A Green gate sees the tree that its latest run checkpoint actually carries."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    checkpoint_env = env.copy()
    _ = checkpoint_env.pop("LIVESPEC_CHECK_SKIP")
    _git(repo=repo, env=env, argv=["add", "tracked.py", "created.py"])
    _git(
        repo=repo,
        env=checkpoint_env,
        argv=[
            "commit",
            "--quiet",
            "--no-verify",
            "-m",
            "fabro(run): green (success)",
            "-m",
            "Fabro-Run: run",
        ],
    )
    checkpoint_tree = _git(repo=repo, env=env, argv=["rev-parse", "HEAD^{tree}"])
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        f'if test "$(git write-tree)" != "{checkpoint_tree}"; then\n'
        f"  printf 'Failed targets (1):\\n  - {_FAILED_TARGET}\\n'\n"
        "  exit 1\n"
        "fi\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "failed_targets": [],
        "preview_ran": True,
        "status": 0,
        "unset_variables": ["LIVESPEC_CHECK_SKIP"],
    }


def test_gate_preview_reports_not_run_when_nothing_would_be_staged(tmp_path: Path) -> None:
    """An empty prospective commit is not a clean preview."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    (repo / "tracked.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "created.py").unlink()

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "failed_targets": [],
        "preview_ran": False,
        "status": 2,
        "unset_variables": [],
    }


def test_gate_preview_reports_not_run_when_every_hook_step_skips(tmp_path: Path) -> None:
    """A hook that skips every command does not validate the prospective commit."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n" "printf '01-check-pre-commit (skip) no matching staged files\\n'\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "failed_targets": [],
        "preview_ran": False,
        "status": 0,
        "unset_variables": ["LIVESPEC_CHECK_SKIP"],
    }


def test_gate_preview_does_not_treat_a_body_mention_of_the_run_trailer_as_a_checkpoint(
    tmp_path: Path,
) -> None:
    """Only a trailer line beginning with the run key makes a commit an engine checkpoint."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    checkpoint_env = env.copy()
    _ = checkpoint_env.pop("LIVESPEC_CHECK_SKIP")
    _git(repo=repo, env=env, argv=["add", "tracked.py", "created.py"])
    _git(
        repo=repo,
        env=checkpoint_env,
        argv=[
            "commit",
            "--quiet",
            "--no-verify",
            "-m",
            "fabro(run): green (success)",
            "-m",
            "A sentence that mentions Fabro-Run: run in the middle of a line.",
        ],
    )

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    assert completed.returncode == 2
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "failed_targets": [],
        "preview_ran": False,
        "status": 2,
        "unset_variables": [],
    }


def test_gate_preview_reports_ran_when_one_hook_step_runs_and_another_skips(
    tmp_path: Path,
) -> None:
    """A skipped step beside a step that ran does not discard the gate verdict."""
    preview = importlib.import_module(_MODULE)
    repo, runner, env = _preview_repository(tmp_path=tmp_path, preview=preview)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text(
        "#!/bin/sh\n"
        "printf '01-a (skip) no matching staged files\\n'\n"
        "printf '03-c (skip) no matching staged files\\n'\n"
        "printf '✔️ 02-b (0.00 seconds)\\n'\n",
        encoding="utf-8",
    )
    hook.chmod(0o755)

    completed = _run(
        repo=repo,
        env=env,
        argv=[sys.executable, str(runner), "green"],
        check=False,
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout.splitlines()[-1]) == {
        "failed_targets": [],
        "preview_ran": True,
        "status": 0,
        "unset_variables": ["LIVESPEC_CHECK_SKIP"],
    }
