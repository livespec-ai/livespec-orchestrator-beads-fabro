"""Behaviour of the roll workflow's split revert/reland gate (bd-ib-ozxhs4).

The gate is a Python program embedded in
``.github/workflows/fast-forward-release-branch.yml``.  These tests extract
that exact program and run it against throwaway git repositories, so the
shipped text is what is exercised.  The contract is contracts.md "Revert and
reland coverage" (spec v400).
"""

from __future__ import annotations

import json
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ROLL_WORKFLOW = _REPO_ROOT / ".github/workflows/fast-forward-release-branch.yml"
_PROGRAM = re.compile(r"<<'SPLIT_PAIR_PY'\n(.*?)\n\s*SPLIT_PAIR_PY\n", re.DOTALL)


def _program() -> str:
    match = _PROGRAM.search(_ROLL_WORKFLOW.read_text(encoding="utf-8"))
    assert match is not None
    return textwrap.dedent(match.group(1))


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.test", *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _commit(repo: Path, name: str, message: str) -> str:
    (repo / name).write_text(message, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _run(
    repo: Path,
    record: Path | None,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str]:
    """Run the embedded program in-process; return its exit code and stderr."""
    monkeypatch.chdir(repo)
    for name, value in {
        "ROLL_TAG": "v9.9.9",
        "BASE_REF": "base",
        "MASTER_REF": "master",
        "COVERAGE_RECORD": str(record or repo / "absent.json"),
    }.items():
        monkeypatch.setenv(name, value)
    code = 0
    try:
        exec(compile(_program(), "<split-pair-gate>", "exec"), {"__name__": "__main__"})  # noqa: S102
    except SystemExit as stop:
        code = int(stop.code or 0)
    return code, capsys.readouterr().err


def _split_repo(tmp_path: Path) -> tuple[Path, str, str, str]:
    """A tag holding a revert whose reland is on master past the tag."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    _commit(repo, "a.txt", "base")
    _git(repo, "branch", "base")
    feature = _commit(repo, "f.txt", "feat: the withdrawal")
    revert = _commit(repo, "r.txt", f"Revert the withdrawal\n\nThis reverts commit {feature}.")
    tag_commit = _git(repo, "rev-parse", "HEAD")
    _git(repo, "checkout", "-q", "--detach", tag_commit)
    _git(repo, "checkout", "-q", "master")
    reland = _commit(repo, "l.txt", f"fix: reland the broker\n\nRelands: {feature}")
    _git(repo, "checkout", "-q", "--detach", tag_commit)
    return repo, revert, feature, reland


def test_a_tag_that_splits_a_revert_from_its_reland_is_refused_without_a_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The run fails, naming the tag and the uncovered pair."""
    repo, revert, _feature, _reland = _split_repo(tmp_path)

    code, stderr = _run(repo, None, monkeypatch, capsys)

    assert code == 1
    assert "v9.9.9" in stderr
    assert revert[:12] in stderr


def test_a_split_pair_covered_by_a_successful_citation_on_the_tag_commit_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The record names the pair and cites proof_capture on the tag's commit."""
    repo, revert, feature, reland = _split_repo(tmp_path)
    tip = _git(repo, "rev-parse", "HEAD")
    record = tmp_path / "canary-coverage.json"
    record.write_text(
        json.dumps(
            {
                "split_pairs": [
                    {
                        "revert": revert,
                        "reverted": feature,
                        "reland": reland,
                        "citations": [
                            {"node": "proof_capture", "build_commit": tip, "outcome": "success"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert _run(repo, record, monkeypatch, capsys)[0] == 0


def test_a_citation_naming_another_build_commit_does_not_cover_the_pair(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A journal citation must name the tag's own commit."""
    repo, revert, feature, reland = _split_repo(tmp_path)
    record = tmp_path / "canary-coverage.json"
    record.write_text(
        json.dumps(
            {
                "split_pairs": [
                    {
                        "revert": revert,
                        "reverted": feature,
                        "reland": reland,
                        "citations": [
                            {
                                "node": "proof_capture",
                                "build_commit": "0" * 40,
                                "outcome": "success",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    assert _run(repo, record, monkeypatch, capsys)[0] == 1


def test_a_tag_that_holds_both_halves_of_the_pair_is_not_flagged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The reland is an ancestor of the tag, so there is no split pair."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    _commit(repo, "a.txt", "base")
    _git(repo, "branch", "base")
    feature = _commit(repo, "f.txt", "feat: the withdrawal")
    _commit(repo, "r.txt", f"Revert the withdrawal\n\nThis reverts commit {feature}.")
    _commit(repo, "l.txt", f"fix: reland the broker\n\nRelands: {feature}")

    assert _run(repo, None, monkeypatch, capsys)[0] == 0


def test_a_tag_with_no_revert_is_not_flagged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Neither half is present, so no record is demanded."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "master")
    _commit(repo, "a.txt", "base")
    _git(repo, "branch", "base")
    _commit(repo, "f.txt", "feat: ordinary change")

    assert _run(repo, None, monkeypatch, capsys)[0] == 0
