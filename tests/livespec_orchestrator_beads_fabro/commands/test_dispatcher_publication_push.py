"""The materialized exact-object leased push used by scripted refresh.

The program's whole contract is that ONE push happens and that it carries an
explicit lease against a named object, so the cases below EXECUTE it against a
real local bare remote rather than reading its text. A text assertion cannot
tell `--force-with-lease=<ref>:<sha>` from `--force-with-lease=<ref>:` — and
that second form is accepted by git and means "the ref does not exist", so it
does not fail, it silently becomes a much weaker assertion.
"""

from __future__ import annotations

import hashlib
import stat
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_fetch import (
    default_helper_roots,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_registry import PLUGINS_ROOT
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_push import (
    PUBLICATION_PUSH_PROGRAM_FILENAME,
    publication_push_program_path_expansion,
    publication_push_program_source,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_lineage_gate import (
    tdd_lineage_gate_program_source,
)

from tests.prepare_step_support import plugins_helper

_BRANCH = "feat/publication-push"


def test_the_helper_fetch_lands_the_single_safe_push_recipe() -> None:
    """One push, one lease, no bypass, and the fetch writes exactly those bytes, owner-only.

    The push program is a fetched helper program: the registry composes its
    bytes and mode, and the helper-fetch step lands it below the plugins root the
    publish node's expansion resolves.
    """
    source = publication_push_program_source()
    path = publication_push_program_path_expansion()
    helper = plugins_helper(path=PUBLICATION_PUSH_PROGRAM_FILENAME)

    assert source.startswith("#!/bin/sh\nset -eu\n")
    assert source.count("git push") == 1
    assert '--force-with-lease="refs/heads/$branch:$expected"' in source
    assert 'origin "HEAD:refs/heads/$branch"' in source
    assert "--no-verify" not in source
    assert path == f"{default_helper_roots()[PLUGINS_ROOT]}/{PUBLICATION_PUSH_PROGRAM_FILENAME}"
    assert helper.compose() == source.encode("utf-8")
    assert helper.mode == 0o700


def test_the_exact_head_push_refuses_unearned_tdd_lineage_before_pushing() -> None:
    """A refresh cannot publish evidence whose recorded parent it rewrote."""
    source = publication_push_program_source()

    assert "livespec_validate_tdd_lineage" in source
    assert "TDD-Green-Parent-Reflog" in source
    assert "TDD-Red-Test-File-Checksum" in source
    assert tdd_lineage_gate_program_source().startswith("#!/usr/bin/env python3\n")


def _git(*, repo: Path, argv: list[str]) -> subprocess.CompletedProcess[str]:
    """One fixture git command, raising its own captured stderr on failure.

    `check=True` rather than a hand-rolled branch: every call here is fixture
    setup that must succeed, so a tolerated-failure arm would be a branch no
    case takes — which this tier's per-file coverage gate reads exactly as it
    reads a never-taken branch in the product.
    """
    return subprocess.run(["git", *argv], cwd=repo, check=True, text=True, capture_output=True)


def _program(*, root: Path) -> Path:
    path = root / PUBLICATION_PUSH_PROGRAM_FILENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(publication_push_program_source(), encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _repository(*, root: Path) -> tuple[Path, Path, str]:
    """A clone on the publish branch, its bare origin, and the published head."""
    root.mkdir(parents=True)
    remote = root / "remote.git"
    work = root / "work"
    _git(repo=root, argv=["init", "--bare", str(remote)])
    _git(repo=root, argv=["init", "-b", "master", str(work)])
    _git(repo=work, argv=["config", "user.name", "Publication Push Test"])
    _git(repo=work, argv=["config", "user.email", "push@example.com"])
    _ = (work / "base.txt").write_text("base\n", encoding="utf-8")
    _git(repo=work, argv=["add", "base.txt"])
    _git(repo=work, argv=["commit", "-m", "base"])
    _git(repo=work, argv=["remote", "add", "origin", str(remote)])
    _git(repo=work, argv=["switch", "-c", _BRANCH])
    _git(repo=work, argv=["push", "-u", "origin", _BRANCH])
    published = _git(repo=work, argv=["rev-parse", "HEAD"]).stdout.strip()
    return work, remote, published


def _remote_head(*, remote: Path) -> str:
    listed = _git(
        repo=remote.parent, argv=["ls-remote", "--heads", str(remote), f"refs/heads/{_BRANCH}"]
    )
    return listed.stdout.split()[0] if listed.stdout.strip() else ""


def _rewritten(*, work: Path) -> str:
    """This clone's HEAD after a rewrite origin does not carry."""
    _ = (work / "next.txt").write_text("next\n", encoding="utf-8")
    _git(repo=work, argv=["add", "next.txt"])
    _git(repo=work, argv=["commit", "--amend", "--no-edit"])
    return _git(repo=work, argv=["rev-parse", "HEAD"]).stdout.strip()


def _tdd_commit(*, work: Path, checksum: str | None) -> str:
    """Add a commit carrying the requested Red evidence to the publish branch."""
    test_path = "tests/test_widget.py"
    contents = b"def test_widget() -> None:\n    assert True\n"
    path = work / test_path
    path.parent.mkdir(parents=True)
    _ = path.write_bytes(contents)
    recorded = checksum or f"sha256:{hashlib.sha256(contents).hexdigest()}"
    _git(repo=work, argv=["add", test_path])
    _git(
        repo=work,
        argv=[
            "commit",
            "-m",
            "feat: evidence fixture\n\n"
            f"TDD-Red-Test: {test_path}\n"
            f"TDD-Red-Test-File-Checksum: {recorded}\n",
        ],
    )
    return _git(repo=work, argv=["rev-parse", "HEAD"]).stdout.strip()


def test_a_rewrite_against_the_recorded_object_lands(tmp_path: Path) -> None:
    """The success path, executed: the ref moves to this clone's HEAD."""
    work, remote, published = _repository(root=tmp_path / "match")
    program = _program(root=tmp_path / "plugins")
    rewritten = _rewritten(work=work)

    completed = subprocess.run(
        [str(program), _BRANCH, published],
        cwd=work,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert rewritten != published
    assert _remote_head(remote=remote) == rewritten


def test_a_rewrite_against_a_stale_object_is_rejected_and_moves_nothing(tmp_path: Path) -> None:
    """The lease is real: a wrong expected object leaves origin exactly as it was.

    This is the case a text assertion cannot reach. The clone genuinely CAN push
    — the success case above proves it against the same fixture shape — so a
    rejection here is the lease acting rather than a broken fixture.
    """
    work, remote, published = _repository(root=tmp_path / "stale")
    program = _program(root=tmp_path / "plugins")
    _ = _rewritten(work=work)

    completed = subprocess.run(
        [str(program), _BRANCH, "0" * 40],
        cwd=work,
        check=False,
        text=True,
        capture_output=True,
    )

    assert completed.returncode != 0
    assert _remote_head(remote=remote) == published


def test_a_bad_red_checksum_is_refused_before_the_branch_moves(tmp_path: Path) -> None:
    """The refusal names both the offending commit and its recorded test path."""
    work, remote, published = _repository(root=tmp_path / "bad-red-checksum")
    program = _program(root=tmp_path / "plugins")
    commit = _tdd_commit(work=work, checksum="sha256:" + "0" * 64)

    completed = subprocess.run(
        [str(program), _BRANCH, published], cwd=work, check=False, text=True, capture_output=True
    )

    assert completed.returncode != 0
    assert commit in completed.stderr
    assert "tests/test_widget.py" in completed.stderr
    assert _remote_head(remote=remote) == published


def test_a_bad_red_checksum_is_refused_before_a_first_publication(tmp_path: Path) -> None:
    """The unleased first push applies the same lineage refusal as a republish."""
    root = tmp_path / "first-publication"
    work, remote, _ = _repository(root=root)
    _git(repo=work, argv=["push", "origin", f":refs/heads/{_BRANCH}"])
    program = _program(root=tmp_path / "plugins")
    commit = _tdd_commit(work=work, checksum="sha256:" + "0" * 64)

    completed = subprocess.run(
        [str(program), _BRANCH], cwd=work, check=False, text=True, capture_output=True
    )

    assert completed.returncode != 0
    assert commit in completed.stderr
    assert "tests/test_widget.py" in completed.stderr
    assert _remote_head(remote=remote) == ""


def test_a_green_amend_with_its_red_reflog_remains_publishable(tmp_path: Path) -> None:
    """A genuine Green records its Red commit, not the final commit's parent.

    Green is an amend of Red.  Consequently the hook records the old Red SHA
    in ``TDD-Green-Parent-Reflog`` while the amended commit retains Red's
    parent.  That is correctly earned evidence and must remain publishable;
    treating the reflog entry as the final commit's parent would reject every
    ordinary Red-to-Green pair before its branch can publish.
    """
    work, remote, published = _repository(root=tmp_path / "green-amend")
    program = _program(root=tmp_path / "plugins")
    test_path = "tests/test_widget.py"
    test_contents = b"def test_widget() -> None:\n    assert True\n"
    path = work / test_path
    path.parent.mkdir(parents=True)
    _ = path.write_bytes(test_contents)
    checksum = hashlib.sha256(test_contents).hexdigest()
    red_message = (
        "feat: widget\n\n"
        f"TDD-Red-Test: {test_path}\n"
        f"TDD-Red-Test-File-Checksum: sha256:{checksum}\n"
    )
    _git(repo=work, argv=["add", test_path])
    _git(repo=work, argv=["commit", "-m", red_message])
    red = _git(repo=work, argv=["rev-parse", "HEAD"]).stdout.strip()
    _ = (work / "widget.py").write_text("def widget() -> int:\n    return 1\n", encoding="utf-8")
    _git(repo=work, argv=["add", "widget.py"])
    _git(
        repo=work,
        argv=[
            "commit",
            "--amend",
            "-m",
            red_message
            + "TDD-Green-Verified-At: 2026-11-17T00:00:00Z\n"
            + f"TDD-Green-Parent-Reflog: {red}\n",
        ],
    )
    green = _git(repo=work, argv=["rev-parse", "HEAD"]).stdout.strip()

    completed = subprocess.run(
        [str(program), _BRANCH, published], cwd=work, check=False, text=True, capture_output=True
    )

    assert completed.returncode == 0, completed.stderr
    assert _remote_head(remote=remote) == green


def test_an_open_red_on_its_unchanged_parent_is_not_refused(tmp_path: Path) -> None:
    """A seeded open Red, already on origin as the seed tip, stays eligible for its Green push."""
    work, remote, published = _repository(root=tmp_path / "seeded-open-red")
    program = _program(root=tmp_path / "plugins")
    open_red = _tdd_commit(work=work, checksum=None)
    _git(repo=work, argv=["push", "origin", _BRANCH])

    completed = subprocess.run(
        [str(program), _BRANCH, open_red], cwd=work, check=False, text=True, capture_output=True
    )

    assert completed.returncode == 0, completed.stderr
    assert _remote_head(remote=remote) == open_red


def test_a_rebased_green_commit_is_refused_before_the_branch_moves(tmp_path: Path) -> None:
    """The actual push helper checks a Green parent after rebase, before its exec."""
    work, remote, published = _repository(root=tmp_path / "rebased-green")
    program = _program(root=tmp_path / "plugins")
    _ = (work / "widget.py").write_text("def widget() -> int:\n    return 1\n", encoding="utf-8")
    _git(repo=work, argv=["add", "widget.py"])
    _git(
        repo=work,
        argv=[
            "commit",
            "-m",
            "feat: original Green\n\n" f"TDD-Green-Parent-Reflog: {published}\n",
        ],
    )
    _git(repo=work, argv=["switch", "master"])
    _ = (work / "moved.txt").write_text("moved\n", encoding="utf-8")
    _git(repo=work, argv=["add", "moved.txt"])
    _git(repo=work, argv=["commit", "-m", "base moved"])
    _git(repo=work, argv=["switch", _BRANCH])
    _git(repo=work, argv=["rebase", "master"])
    rebased = _git(repo=work, argv=["rev-parse", "HEAD"]).stdout.strip()

    completed = subprocess.run(
        [str(program), _BRANCH, published], cwd=work, check=False, text=True, capture_output=True
    )

    assert completed.returncode != 0
    assert rebased in completed.stderr
    assert "parent" in completed.stderr
    assert _remote_head(remote=remote) == published


_UNUSABLE: tuple[tuple[str, list[str], str], ...] = (
    ("no-arguments", [], "expected <branch> <expected-object>"),
    ("one-argument", [_BRANCH], "expected <branch> <expected-object>"),
    ("three-arguments", [_BRANCH, "a" * 40, "extra"], "expected <branch>"),
    ("empty-branch", ["", "a" * 40], "branch is empty"),
    ("empty-object", [_BRANCH, ""], "not a full lowercase sha"),
    ("short-object", [_BRANCH, "abc123"], "not a full lowercase sha"),
    ("uppercase-object", [_BRANCH, "A" * 40], "not a full lowercase sha"),
    ("non-hex-object", [_BRANCH, "z" * 40], "not a full lowercase sha"),
)


def test_every_unusable_invocation_refuses_before_any_push(tmp_path: Path) -> None:
    """Eight malformed invocations, each refusing with its own stated cause.

    The EMPTY expected object is the one that matters most: git accepts
    `--force-with-lease=<ref>:` as "the ref does not exist", so an unvalidated
    empty value would not fail — it would push under a lease that asserts
    nothing. Origin is asserted unmoved after every arm, which is what shows the
    refusal happened before the exec rather than after a push nobody looked for.

    EIGHT ARMS IN ONE CASE, against ONE repository, deliberately. They are eight
    readings of a single argument-validation contract whose whole claim is that
    the repository is never reached, so a fixture per arm would build eight
    repositories — some sixty real `git` processes — to assert the same unmoved
    ref eight times. This suite runs inside `pr_refresh`'s own gate on a loaded
    box, where that cost is paid against every other test's timing.
    """
    work, remote, published = _repository(root=tmp_path / "invalid")
    program = _program(root=tmp_path / "plugins")

    for name, argv, cause in _UNUSABLE:
        completed = subprocess.run(
            [str(program), *argv], cwd=work, check=False, text=True, capture_output=True
        )

        assert completed.returncode == 2, (name, completed.stdout, completed.stderr)
        assert cause in completed.stderr, (name, completed.stderr)
        assert _remote_head(remote=remote) == published, name
