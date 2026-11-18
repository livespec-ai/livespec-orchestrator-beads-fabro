"""A seed ruling that names a seed behind the default branch is reseeded, never laid over it (bd-ib-nlofrn).

`SPECIFICATION/scenarios.md` Scenario 372: a stale seed is re-seeded by diff-apply
onto the default branch's tip. The seed-ruling route took the ruled commit as the
run's start (livespec-dev-tooling jgl66s run 01M7R9CKG75T: the run's diff against its
base was 91 files, +574/-2214 where the seed's own diff is 13 files, +306/-14), so
the seed's whole tree reverted every master change in between.

Every git read and write runs against a REAL local bare origin; only the forge's Git
Data API (`gh api`) is emulated, by an object-writing double.
"""

from __future__ import annotations

import base64
import json
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_routes import (
    RecoveryHold,
    RecoverySeed,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_recovery_ruled_seed import ruled_seed
from livespec_orchestrator_beads_fabro.commands._dispatcher_seed_ruling import SeedRuling

_ITEM = "bd-ib-nlofrn"
_SEED_REF = "refs/heads/needs-human/f423cbb58ceb462f81a91319a09ec309"
_LINES = "".join(f"line {n}\n" for n in range(1, 21))
_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.test",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.test",
}


def _git(*, cwd: Path, args: list[str], stdin: bytes | None = None) -> str:
    env = {**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}, **_ENV}
    done = subprocess.run(
        ["git", *args], cwd=cwd, input=stdin, capture_output=True, check=True, env=env
    )
    return done.stdout.decode("utf-8").strip()


def _commit(*, work: Path, message: str) -> str:
    _git(cwd=work, args=["add", "-A"])
    _git(cwd=work, args=["commit", "-q", "--allow-empty", "-m", message])
    return _git(cwd=work, args=["rev-parse", "HEAD"])


@dataclass(kw_only=True)
class _World:
    work: Path
    origin: Path
    base: str
    tip: str
    seed: str


def _world(*, tmp_path: Path, conflicting: bool = False, stale: bool = True) -> _World:
    """A default branch that moved past the seed's merge base, with the seed on origin."""
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(cwd=tmp_path, args=["init", "-q", "--bare", str(origin)])
    _git(cwd=origin, args=["config", "uploadpack.allowAnySHA1InWant", "true"])
    _git(cwd=tmp_path, args=["init", "-q", "-b", "master", str(work)])
    _git(cwd=work, args=["remote", "add", "origin", str(origin)])
    (work / "a.txt").write_text(_LINES, encoding="utf-8")
    (work / "b.txt").write_text("b\n", encoding="utf-8")
    base = _commit(work=work, message="base")
    _git(cwd=work, args=["checkout", "-q", "-b", "seed"])
    seed_a = _LINES.replace("line 1\n", "seed line 1\n", 1)
    (work / "a.txt").write_text(seed_a, encoding="utf-8")
    (work / "n.txt").write_text("seed work\n", encoding="utf-8")
    seed = _commit(work=work, message="seed work")
    _git(cwd=work, args=["checkout", "-q", "master"])
    if stale:
        tip_a = _LINES.replace("line 1\n" if conflicting else "line 20\n", "tip edit\n", 1)
        (work / "a.txt").write_text(tip_a, encoding="utf-8")
        (work / "b.txt").write_text("master moved b\n", encoding="utf-8")
        (work / "master_only.txt").write_text("master only\n", encoding="utf-8")
        _commit(work=work, message="master moved on")
    else:
        _git(cwd=work, args=["merge", "-q", "--ff-only", "seed"])
    tip = _git(cwd=work, args=["rev-parse", "HEAD"])
    _git(cwd=work, args=["push", "-q", "origin", "master:refs/heads/master"])
    _git(cwd=work, args=["push", "-q", "origin", f"seed:{_SEED_REF}"])
    _git(cwd=work, args=["fetch", "-q", "origin"])
    _git(cwd=work, args=["remote", "set-head", "origin", "master"])
    return _World(work=work, origin=origin, base=base, tip=tip, seed=seed)


@dataclass(kw_only=True)
class _Forge:
    """Runs git for real and plays the forge's Git Data API against the same objects."""

    world: _World
    tree: str
    calls: list[list[str]] = field(default_factory=list)

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: object = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        self.calls.append(list(argv))
        if argv[0] == "git":
            done = subprocess.run(
                argv,
                cwd=self.world.work,
                capture_output=True,
                check=False,
                env={**{k: v for k, v in os.environ.items() if not k.startswith("GIT_")}, **_ENV},
            )
            return CommandResult(
                exit_code=done.returncode,
                stdout=done.stdout.decode("utf-8", errors="replace"),
                stderr=done.stderr.decode("utf-8", errors="replace"),
            )
        endpoint = next(one for one in argv if one.startswith("/repos/"))
        if endpoint.endswith("/git/refs"):
            fields = [one for one in argv if one.startswith(("ref=", "sha="))]
            ref = next(one for one in fields if one.startswith("ref=")).removeprefix("ref=")
            sha = next(one for one in fields if one.startswith("sha=")).removeprefix("sha=")
            _git(cwd=self.world.work, args=["push", "-q", "origin", f"{sha}:{ref}"])
            return CommandResult(exit_code=0, stdout="", stderr="")
        assert stdin is not None
        with os.fdopen(os.dup(stdin), "rb") as handle:
            body = json.loads(handle.read())
        if endpoint.endswith("/git/blobs"):
            sha = _git(
                cwd=self.world.work,
                args=["hash-object", "-w", "--stdin"],
                stdin=base64.b64decode(body["content"]),
            )
        elif endpoint.endswith("/git/trees"):
            sha = self.tree
        else:
            sha = _git(
                cwd=self.world.work,
                args=["commit-tree", body["tree"], "-p", body["parents"][0], "-m", body["message"]],
            )
        return CommandResult(exit_code=0, stdout=f"{sha}\n", stderr="")

    def forge_writes(self) -> list[list[str]]:
        return [one for one in self.calls if one[0] == "gh"]


def _expected_tree(*, tmp_path: Path, world: _World) -> str:
    """The tip's tree with the seed's merge-base diff applied, by `git apply --3way`."""
    scratch = tmp_path / "scratch"
    _git(cwd=tmp_path, args=["clone", "-q", str(world.origin), str(scratch)])
    _git(cwd=scratch, args=["checkout", "-q", "--detach", world.tip])
    patch = _git(cwd=world.work, args=["diff", "--binary", world.base, world.seed]) + "\n"
    _git(cwd=scratch, args=["apply", "--3way", "--index"], stdin=patch.encode("utf-8"))
    return _git(cwd=scratch, args=["write-tree"])


def _ruled(*, world: _World, forge: _Forge) -> RecoverySeed | RecoveryHold:
    return ruled_seed(
        runner=forge,
        repo=world.work,
        work_item_id=_ITEM,
        ruling=SeedRuling(
            work_item_id=_ITEM,
            preservation_ref=_SEED_REF,
            commit_sha=world.seed,
            invoker="coordinator",
            reason="the ruled tree carries the checked work",
            instant="2026-11-18T22:00:00Z",
        ),
        earlier_run_ids=("01M7R9CKG75T",),
    )


def _changed_files(*, work: Path, old: str, new: str) -> list[str]:
    return _git(cwd=work, args=["diff", "--name-only", old, new]).splitlines()


def test_a_stale_ruled_seed_starts_the_run_from_one_reseed_commit_on_the_tip(
    tmp_path: Path,
) -> None:
    world = _world(tmp_path=tmp_path)
    forge = _Forge(world=world, tree=_expected_tree(tmp_path=tmp_path, world=world))

    ruled = _ruled(world=world, forge=forge)

    assert isinstance(ruled, RecoverySeed)
    assert ruled.commit_sha != world.seed
    assert ruled.preservation_ref == f"refs/livespec/reseed/{_ITEM}/{ruled.commit_sha}"
    parents = _git(cwd=world.work, args=["rev-list", "--parents", "-n", "1", ruled.commit_sha])
    assert parents.split(" ") == [ruled.commit_sha, world.tip]
    # The run's diff against the default branch tip equals the seed's own diff, file for file.
    assert _changed_files(work=world.work, old=world.tip, new=ruled.commit_sha) == (
        _changed_files(work=world.work, old=world.base, new=world.seed)
    )
    # Every file master changed after the seed's merge base still reads as it does at the tip.
    for path in ("b.txt", "master_only.txt"):
        assert _git(cwd=world.work, args=["show", f"{ruled.commit_sha}:{path}"]) == _git(
            cwd=world.work, args=["show", f"{world.tip}:{path}"]
        )


def test_a_stale_ruled_seed_that_conflicts_holds_with_a_named_record_and_launches_nothing(
    tmp_path: Path,
) -> None:
    world = _world(tmp_path=tmp_path, conflicting=True)
    forge = _Forge(world=world, tree="")

    ruled = _ruled(world=world, forge=forge)

    assert isinstance(ruled, RecoveryHold)
    (measurement,) = ruled.measurements
    assert measurement.name == "seed-reseed-conflict"
    for named in (_SEED_REF, world.seed, world.tip, "a.txt"):
        assert named in measurement.detail
    assert forge.forge_writes() == []


def test_a_ruled_seed_that_already_contains_the_tip_is_taken_as_ruled(tmp_path: Path) -> None:
    world = _world(tmp_path=tmp_path, stale=False)
    forge = _Forge(world=world, tree="")

    ruled = _ruled(world=world, forge=forge)

    assert isinstance(ruled, RecoverySeed)
    assert (ruled.commit_sha, ruled.preservation_ref) == (world.seed, _SEED_REF)
    assert forge.forge_writes() == []
