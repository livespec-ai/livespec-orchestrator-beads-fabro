"""Gathering one dispatch's completed-cycle series at an evaluation boundary.

Plan slice S6 (`bd-ib-z2y4ca`), the IO half. The derivations are pure and live
in `_dispatcher_completed_cycles` (what a pair is, what its elapsed interval is)
and `_dispatcher_cycle_measure` (what a changed product logical line is); this
module only reaches for their inputs — the forge's commit series and the two
source trees each pair spans.

HOW THE SERIES IS SELECTED, AND WHY IT IS THE SAME MECHANISM AS THE TDD PROBE.
The Dispatcher mints a `dispatch_id` per dispatch and writes it into the sandbox
clone's `livespec.factoryRunId` git config, which stamps a `Factory-Run-Id`
trailer onto every commit that run authors. Filtering the pull request's commits
by that trailer is an EXACT per-run selection, so a re-dispatch of the same item
and a human commit pushed onto the same branch cannot contribute to it. That is
`_dispatcher_tdd_probe`'s mechanism and this module reuses it deliberately
rather than inventing a second selection that could disagree.

WHERE THE RED STATE COMES FROM, which is the one derivation worth reading twice.
A completed cycle is ONE commit: the Red commit carried the test alone, and the
Green `--amend` replaced it, so the Red state is not an object in the branch
history at all. What IS in history is the commit's parent — the state before the
test — and the commit itself. Their difference over PRODUCT paths is therefore
exactly the product code the Green added on top of the test-only Red, which is
what the clause asks for: "added plus removed logical lines between the pair's
test-only Red state and Green state". The test file's own change falls out
because a test path is not a product path, so no subtraction of it is needed.

THREE ABSENCES, THREE DIFFERENT ANSWERS. An UNIDENTIFIABLE series — no pull
request, no dispatch id, a failing or unparseable `gh` probe, or a payload whose
commits carry none of this run's trailer — is UNREADABLE: the honest statement is
that this run's series could not be found, not that it authored no cycle. A
series that WAS identified and holds no verified pair is OBSERVED and EMPTY,
which is a finding about the run. And a pair whose objects this clone does not
hold keeps its place in the count while reporting its SIZE unobserved, because
"an unavailable individual size/time measurement MUST NOT erase an otherwise
independently established completed-pair count".

WHY THE FORGE PROBE IS INJECTED AND THE GIT READS ARE NOT. `runner` answers the
ONE `gh` call, which is what a hermetic test must be able to script — a forge is
not reproducible in a fixture. The git reads go to a `ShellCommandRunner` built
here, against the repository handed in, which is what lets the paired test point
this probe at a REAL repository carrying real trailer blocks: the measurement is
then exercised through the same objects a live dispatch reads rather than through
a stub that could agree with a wrong implementation.

Every git read is fail-soft to the per-pair absence above, and no read mutates
anything: `diff-tree`, `ls-tree` and `show` are the whole vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_assertion_count import (
    assertion_count_for,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_measure import (
    changed_product_logical_lines,
    is_product_path,
    product_source_prefixes,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_io import ShellCommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_commits import commit_trailers
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_probe import (
    FACTORY_RUN_ID_TRAILER_KEY,
)
from livespec_orchestrator_beads_fabro.effects import (
    AttemptFailure,
    JsonParseFailure,
    attempt,
    parse_json,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

__all__: list[str] = [
    "UNOBSERVED_COUNTING",
    "UNOBSERVED_SOURCE_TREE",
    "UNOBSERVED_TIMESTAMPS",
    "UNREADABLE_PROVENANCE",
    "CompletedCycle",
    "CompletedCycleSeries",
    "gather_completed_cycle_series",
    "parse_provenance_commits",
]

# The same probe budget the sibling commit-series and diff-size probes carry:
# fail-soft rather than hold up an evaluation boundary.
_PROBE_TIMEOUT_SECONDS = 60.0

# The repository's own source-tree declaration, read from the working tree so
# the classification matches the population this repository's gates classify.
_PYPROJECT = "pyproject.toml"

UNOBSERVED_SOURCE_TREE = "source-tree-unavailable"
UNOBSERVED_COUNTING = "unsupported-counting"
UNOBSERVED_TIMESTAMPS = "invalid-or-reversed-timestamps"
UNREADABLE_PROVENANCE = "provenance-unreadable"
_RED_TRAILER_KEY = "TDD-Red-Captured-At"
_GREEN_TRAILER_KEY = "TDD-Green-Verified-At"
_RED_CHECKSUM_KEY = "TDD-Red-Test-File-Checksum"


@dataclass(frozen=True, kw_only=True)
class ProvenanceCommit:
    """One forge-reported commit and the complete message used to identify it."""

    sha: str
    message: str


@dataclass(frozen=True, kw_only=True)
class CycleSource:
    """The provenance retained for one distinct verified Red-Green pair."""

    commit: str
    pair_id: str
    red_captured_at: str
    green_verified_at: str


@dataclass(frozen=True, kw_only=True)
class CompletedCycle:
    """One completed pair's identity, ordinal and independently observed measures."""

    ordinal: int
    pair_id: str
    commit: str
    product_lloc_changed: int | None
    product_lloc_unobserved_reason: str | None
    elapsed_seconds: int | None
    elapsed_unobserved_reason: str | None


@dataclass(frozen=True, kw_only=True)
class CompletedCycleSeries:
    """The dispatch's measured pairs, or its unreadable provenance verdict."""

    cycles: tuple[CompletedCycle, ...]
    assertion_count: int
    unreadable_reason: str | None

    @property
    def observed(self) -> bool:
        """Whether dispatch provenance was readable."""
        return self.unreadable_reason is None

    @property
    def completed_count(self) -> int | None:
        """The established pair count, including zero, or None when unreadable."""
        return len(self.cycles) if self.observed else None


def gather_completed_cycle_series(
    *,
    repo: Path,
    item: WorkItem,
    pr_number: int | None,
    dispatch_id: str | None,
    runner: CommandRunner,
) -> CompletedCycleSeries:
    """This dispatch's completed-cycle series, measured or explicitly unreadable.

    The assertion count rides along even on an unreadable series, because the two
    sides of the progress comparison fail independently: a run whose provenance
    could not be read still has a dispatched assertion count worth recording.
    """
    assertions = assertion_count_for(item=item).count
    commits = _dispatch_commits(
        repo=repo, pr_number=pr_number, dispatch_id=dispatch_id, runner=runner
    )
    if commits is None:
        return CompletedCycleSeries(
            cycles=(), assertion_count=assertions, unreadable_reason=UNREADABLE_PROVENANCE
        )
    prefixes = _source_prefixes(repo=repo)
    git = ShellCommandRunner()
    return CompletedCycleSeries(
        cycles=tuple(
            _completed_cycle(
                ordinal=index + 1,
                source=source,
                product_lloc=_measure(repo=repo, source=source, prefixes=prefixes, runner=git),
            )
            for index, source in enumerate(_verified_pairs(commits=commits))
        ),
        assertion_count=assertions,
        unreadable_reason=None,
    )


def parse_provenance_commits(*, stdout: str) -> tuple[ProvenanceCommit, ...] | None:
    """The commits in a `gh pr view <pr> --json commits,oid` payload.

    `None` — unreadable — for an unparseable payload, a payload that is not an
    object, or one whose `commits` key is not a list. An entry missing its `oid`
    or its headline is SKIPPED rather than failing the whole read, for the reason
    the sibling parser skips one: a single odd entry must not blind the series.
    The commit identity is REQUIRED here, unlike in the sibling parser, because
    a pair cannot be measured without the object to read it out of.

    Each message is rebuilt as `<headline>\\n\\n<body>`, the shape `git log %B`
    produces, so the trailer scan reads a `gh`-sourced series exactly as it
    reads a git-sourced one.
    """
    parsed = parse_json(text=stdout)
    if isinstance(parsed, JsonParseFailure) or not isinstance(parsed, dict):
        return None
    raw_commits = cast("dict[str, object]", parsed).get("commits")
    if not isinstance(raw_commits, list):
        return None
    found: list[ProvenanceCommit] = []
    for raw in cast("list[object]", raw_commits):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, object]", raw)
        sha = entry.get("oid")
        headline = entry.get("messageHeadline")
        if not isinstance(sha, str) or sha == "" or not isinstance(headline, str):
            continue
        body = entry.get("messageBody")
        found.append(
            ProvenanceCommit(
                sha=sha, message=f"{headline}\n\n{body if isinstance(body, str) else ''}"
            )
        )
    return tuple(found)


def _dispatch_commits(
    *, repo: Path, pr_number: int | None, dispatch_id: str | None, runner: CommandRunner
) -> tuple[ProvenanceCommit, ...] | None:
    """This dispatch's OWN commits, or None when its series cannot be identified."""
    if pr_number is None or dispatch_id is None:
        return None
    result = runner.run(
        argv=["gh", "pr", "view", str(pr_number), "--json", "commits"],
        cwd=repo,
        timeout_seconds=_PROBE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    parsed = parse_provenance_commits(stdout=result.stdout)
    if parsed is None:
        return None
    mine = tuple(
        commit
        for commit in parsed
        if commit_trailers(message=commit.message).get(FACTORY_RUN_ID_TRAILER_KEY) == dispatch_id
    )
    return mine if mine else None


def _source_prefixes(*, repo: Path) -> tuple[str, ...] | None:
    """The repository's declared source trees, or None when its file cannot be read."""
    declaration = repo / _PYPROJECT
    if not declaration.is_file():
        return ()
    text = attempt(
        action=lambda: declaration.read_text(encoding="utf-8"),
        exceptions=(OSError, UnicodeError),
    )
    if isinstance(text, AttemptFailure):
        return None
    return product_source_prefixes(pyproject_text=text)


def _measure(
    *, repo: Path, source: CycleSource, prefixes: tuple[str, ...] | None, runner: CommandRunner
) -> tuple[int | None, str | None]:
    """One pair's changed product logical lines, or the unobserved verdict.

    The parent is resolved and the changed paths listed in one read; a failure of
    either means this clone cannot see the pair's source trees. A path the
    counter cannot read is reported as unsupported counting rather than as a
    missing tree, because the two have different remedies. An empty prefix tuple
    means the repository's source-tree declaration is absent or unreadable, so
    the canonical product classification cannot be applied: that is unsupported
    counting for the pair, never a numeric zero over a population nobody declared.
    """
    if not prefixes:
        return (None, UNOBSERVED_COUNTING)
    changed = _changed_paths(repo=repo, commit=source.commit, runner=runner)
    if changed is None:
        return (None, UNOBSERVED_SOURCE_TREE)
    total = 0
    for path in changed:
        if not is_product_path(path=path, prefixes=prefixes):
            continue
        before = _blob(repo=repo, rev=f"{source.commit}^", path=path, runner=runner)
        after = _blob(repo=repo, rev=source.commit, path=path, runner=runner)
        if before is None or after is None:
            return (None, UNOBSERVED_SOURCE_TREE)
        lines = changed_product_logical_lines(before=before, after=after)
        if lines is None:
            return (None, UNOBSERVED_COUNTING)
        total += lines
    return (total, None)


def _verified_pairs(*, commits: tuple[ProvenanceCommit, ...]) -> tuple[CycleSource, ...]:
    """Return distinct completed pairs in preserved Red chronology."""
    found: dict[str, CycleSource] = {}
    for commit in commits:
        trailers = commit_trailers(message=commit.message)
        red_at = trailers.get(_RED_TRAILER_KEY)
        green_at = trailers.get(_GREEN_TRAILER_KEY)
        if red_at is None or green_at is None:
            continue
        checksum = trailers.get(_RED_CHECKSUM_KEY)
        pair_id = f"{checksum}@{red_at}" if checksum is not None else f"commit:{commit.sha}"
        _ = found.setdefault(
            pair_id,
            CycleSource(
                commit=commit.sha,
                pair_id=pair_id,
                red_captured_at=red_at,
                green_verified_at=green_at,
            ),
        )
    return tuple(sorted(found.values(), key=lambda source: _red_order(source=source)))


def _completed_cycle(
    *, ordinal: int, source: CycleSource, product_lloc: tuple[int | None, str | None]
) -> CompletedCycle:
    """Combine independently-observed size and elapsed measurements for one pair."""
    elapsed, elapsed_reason = _elapsed_seconds(
        red_at=source.red_captured_at, green_at=source.green_verified_at
    )
    return CompletedCycle(
        ordinal=ordinal,
        pair_id=source.pair_id,
        commit=source.commit,
        product_lloc_changed=product_lloc[0],
        product_lloc_unobserved_reason=product_lloc[1],
        elapsed_seconds=elapsed,
        elapsed_unobserved_reason=elapsed_reason,
    )


def _red_order(*, source: CycleSource) -> tuple[int, float]:
    """Sort readable Red timestamps first, without dropping unreadable pairs."""
    instant = _instant(value=source.red_captured_at)
    return (1, 0.0) if instant is None else (0, instant.timestamp())


def _elapsed_seconds(*, red_at: str, green_at: str) -> tuple[int | None, str | None]:
    """Use preserved Red-to-Green provenance, never a merge timestamp."""
    red = _instant(value=red_at)
    green = _instant(value=green_at)
    if red is None or green is None or green < red:
        return (None, UNOBSERVED_TIMESTAMPS)
    return (round((green - red).total_seconds()), None)


def _instant(*, value: str) -> datetime | None:
    """Parse this trailer's UTC spelling, returning None for invalid provenance."""
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    parsed = attempt(action=lambda: datetime.fromisoformat(normalized), exceptions=(ValueError,))
    return None if isinstance(parsed, AttemptFailure) else parsed


def _changed_paths(*, repo: Path, commit: str, runner: CommandRunner) -> tuple[str, ...] | None:
    """The paths one commit changed against its parent, or None when unreadable."""
    result = runner.run(
        argv=["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit],
        cwd=repo,
        timeout_seconds=_PROBE_TIMEOUT_SECONDS,
    )
    if result.exit_code != 0:
        return None
    return tuple(line for line in result.stdout.splitlines() if line != "")


def _blob(*, repo: Path, rev: str, path: str, runner: CommandRunner) -> str | None:
    """One path's content at one revision: the EMPTY string when the tree lacks it.

    None means the content could not be read, which is a different finding from
    the path being absent. A file the pair ADDED does not exist at the parent and
    a file it DELETED does not exist at the commit, and both are ordinary
    measurable changes, so a tree that is readable and does not name the path
    reads as empty. A tree that cannot be read, or a path it names whose object
    cannot be read, is missing source evidence: reading it as empty would
    fabricate a numeric size for a change nobody saw. A failed listing falls
    through to the read below, which fails for the same reason and answers None.
    """
    listing = runner.run(
        argv=["git", "ls-tree", rev, "--", path],
        cwd=repo,
        timeout_seconds=_PROBE_TIMEOUT_SECONDS,
    )
    if listing.exit_code == 0 and listing.stdout.strip() == "":
        return ""
    result = runner.run(
        argv=["git", "show", f"{rev}:{path}"],
        cwd=repo,
        timeout_seconds=_PROBE_TIMEOUT_SECONDS,
    )
    return result.stdout if result.exit_code == 0 else None
