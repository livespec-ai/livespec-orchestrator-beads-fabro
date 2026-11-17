"""Publication-time TDD lineage validation (bd-ib-tqnvj7)."""

from __future__ import annotations

import hashlib
import importlib
import stat
import subprocess
from pathlib import Path


def _git(*, repo: Path, argv: list[str]) -> str:
    """Run one fixture git command and return its standard output."""
    completed = subprocess.run(
        ["git", *argv],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _commit(*, repo: Path, message: str, name: str, text: str) -> str:
    """Commit one fixture change with the supplied evidence message."""
    _ = (repo / name).write_text(text, encoding="utf-8")
    _git(repo=repo, argv=["add", name])
    _git(repo=repo, argv=["commit", "-m", message])
    return _git(repo=repo, argv=["rev-parse", "HEAD"])


def _repository(*, tmp_path: Path) -> tuple[Path, str]:
    """Build a rebased Green commit retaining a Red recorded on another parent."""
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo=repo, argv=["init", "-b", "master"])
    _git(repo=repo, argv=["config", "user.name", "Lineage Test"])
    _git(repo=repo, argv=["config", "user.email", "lineage@example.invalid"])
    base = _commit(repo=repo, message="base", name="base.txt", text="base\n")
    _git(repo=repo, argv=["switch", "-c", "work"])
    red = _commit(
        repo=repo,
        message=(
            "feat: original Green\n\n"
            "TDD-Red-Test: tests/test_widget.py\n"
            "TDD-Red-Test-File-Checksum: sha256:unused\n"
            "TDD-Green-Verified-At: 2026-11-11T00:00:00Z\n"
            f"TDD-Green-Parent-Reflog: {base}\n"
        ),
        name="widget.py",
        text="def widget() -> int:\n    return 1\n",
    )
    _git(repo=repo, argv=["switch", "master"])
    _ = _commit(repo=repo, message="base moved", name="moved.txt", text="moved\n")
    _git(repo=repo, argv=["cherry-pick", red])
    return repo, _git(repo=repo, argv=["merge-base", "HEAD", "master"])


def test_a_rebased_green_commit_is_refused_before_publication(tmp_path: Path) -> None:
    """A Green record from another parent cannot publish after a history rewrite."""
    source_path = (
        Path(__file__).parents[3]
        / ".claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands"
        / "_dispatcher_tdd_lineage_gate.py"
    )
    assert source_path.is_file()
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_lineage_gate"
    )
    program = tmp_path / "livespec-tdd-lineage-gate.py"
    _ = program.write_text(module.tdd_lineage_gate_program_source(), encoding="utf-8")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    repo, base = _repository(tmp_path=tmp_path)

    completed = subprocess.run(
        [str(program), base],
        cwd=repo,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0
    assert _git(repo=repo, argv=["rev-parse", "HEAD"]) in completed.stderr
    assert "parent" in completed.stderr


_TEST_PATH = "tests/test_widget.py"
_TEST_BYTES = b"def test_widget() -> None:\n    assert True\n"


def _program(*, tmp_path: Path) -> Path:
    """Materialize the standalone validator the push helper embeds."""
    module = importlib.import_module(
        "livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_lineage_gate"
    )
    program = tmp_path / "livespec-tdd-lineage-gate.py"
    _ = program.write_text(module.tdd_lineage_gate_program_source(), encoding="utf-8")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    return program


def _run(*, program: Path, repo: Path) -> subprocess.CompletedProcess[str]:
    """Run the validator with the default published-branch walk."""
    return subprocess.run([str(program)], cwd=repo, check=False, text=True, capture_output=True)


def _published_repo(*, tmp_path: Path) -> Path:
    """A clone whose origin carries the default branch, on a work branch."""
    repo = tmp_path / "repository"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    _git(repo=repo, argv=["init", "-b", "master"])
    _git(repo=repo, argv=["config", "user.name", "Lineage Test"])
    _git(repo=repo, argv=["config", "user.email", "lineage@example.invalid"])
    _git(repo=repo, argv=["config", "livespec.factoryRunId", "this-run"])
    _ = _commit(repo=repo, message="root", name="root.txt", text="root\n")
    _git(repo=repo, argv=["init", "--bare", str(remote)])
    _git(repo=repo, argv=["remote", "add", "origin", str(remote)])
    _git(repo=repo, argv=["push", "origin", "master"])
    _git(repo=repo, argv=["switch", "-c", "work"])
    return repo


def _red(*, repo: Path, run_id: str) -> str:
    """Commit an open Red whose recorded checksum matches its test file."""
    path = repo / _TEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(_TEST_BYTES)
    _git(repo=repo, argv=["add", _TEST_PATH])
    _git(
        repo=repo,
        argv=[
            "commit",
            "-m",
            "feat: open red\n\n"
            f"TDD-Red-Test: {_TEST_PATH}\n"
            f"TDD-Red-Test-File-Checksum: sha256:{hashlib.sha256(_TEST_BYTES).hexdigest()}\n"
            f"Factory-Run-Id: {run_id}",
        ],
    )
    return _git(repo=repo, argv=["rev-parse", "HEAD"])


def _move_master_and_rebase(*, repo: Path) -> str:
    """Advance the default branch on origin, then rebase the work branch onto it."""
    _git(repo=repo, argv=["switch", "master"])
    _ = _commit(repo=repo, message="base moved", name="moved.txt", text="moved\n")
    _git(repo=repo, argv=["push", "origin", "master"])
    _git(repo=repo, argv=["switch", "work"])
    _git(repo=repo, argv=["rebase", "master"])
    return _git(repo=repo, argv=["rev-parse", "HEAD"])


def test_a_published_rebased_green_is_refused_when_a_restored_run_republishes_it(
    tmp_path: Path,
) -> None:
    """The walk covers the whole branch, including commits origin already carries."""
    repo = _published_repo(tmp_path=tmp_path)
    red = _red(repo=repo, run_id="earlier-run")
    _ = (repo / "widget.py").write_text("def widget() -> int:\n    return 1\n", encoding="utf-8")
    _git(repo=repo, argv=["add", "widget.py"])
    message = _git(repo=repo, argv=["log", "-1", "--format=%B"])
    _git(
        repo=repo,
        argv=[
            "commit",
            "--amend",
            "-m",
            message
            + f"\nTDD-Green-Verified-At: 2026-11-11T00:00:00Z\nTDD-Green-Parent-Reflog: {red}",
        ],
    )
    rebased = _move_master_and_rebase(repo=repo)
    _git(repo=repo, argv=["push", "origin", "work"])

    completed = _run(program=_program(tmp_path=tmp_path), repo=repo)

    assert completed.returncode != 0
    assert rebased in completed.stderr
    assert "parent" in completed.stderr


def test_a_rebased_open_red_of_another_run_is_refused_naming_commit_and_test(
    tmp_path: Path,
) -> None:
    """An open Red carried onto a new parent keeps a checksum it never earned there."""
    repo = _published_repo(tmp_path=tmp_path)
    _ = _red(repo=repo, run_id="earlier-run")
    rebased = _move_master_and_rebase(repo=repo)

    completed = _run(program=_program(tmp_path=tmp_path), repo=repo)

    assert completed.returncode != 0
    assert rebased in completed.stderr
    assert _TEST_PATH in completed.stderr


def test_an_open_red_this_run_recorded_is_not_refused(tmp_path: Path) -> None:
    """The run's own commit node earned that Red on the parent it sits on."""
    repo = _published_repo(tmp_path=tmp_path)
    _ = _red(repo=repo, run_id="this-run")

    completed = _run(program=_program(tmp_path=tmp_path), repo=repo)

    assert completed.returncode == 0, completed.stderr


def test_an_open_red_seed_tip_published_unchanged_is_not_refused(tmp_path: Path) -> None:
    """A seed tip origin already carries, unchanged, keeps its original parent."""
    repo = _published_repo(tmp_path=tmp_path)
    _ = _red(repo=repo, run_id="earlier-run")
    _git(repo=repo, argv=["push", "origin", "work"])

    completed = _run(program=_program(tmp_path=tmp_path), repo=repo)

    assert completed.returncode == 0, completed.stderr


def test_a_published_green_whose_red_object_is_gone_is_tolerated_only_when_published(
    tmp_path: Path,
) -> None:
    """A sandbox clone never holds the amended-away Red, so published Greens verify by SHA."""
    repo = _published_repo(tmp_path=tmp_path)
    _ = _commit(
        repo=repo,
        message="feat: green\n\nTDD-Green-Parent-Reflog: " + "a" * 40,
        name="widget.py",
        text="widget\n",
    )
    program = _program(tmp_path=tmp_path)
    unpublished = _run(program=program, repo=repo)
    _git(repo=repo, argv=["push", "origin", "work"])
    published = _run(program=program, repo=repo)

    assert unpublished.returncode != 0
    assert published.returncode == 0, published.stderr
