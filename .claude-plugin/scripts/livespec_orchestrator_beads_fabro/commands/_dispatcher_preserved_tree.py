"""Preserving a checkpoint-failed run's tree on a forge ref.

The run whose engine checkpoint failed left its work in a stopped container's
work tree on the factory server and nowhere else: the checkpoint is what would
have committed it, a stage diff artifact never carries a failed node's tree,
and the run's terminal patch -- the one other carrier -- is exactly what is
absent in the case this module exists for. So the sequence here is the only
route from that work to anything durable: read the changed files off the
factory that ran the dispatch, then publish them as one commit on a
preservation ref.

THIS MODULE JOINS A READ TO A PUBLICATION AND OWNS NEITHER. `_fabro_run_files`
reads, `_dispatcher_preserved_tree_publish` publishes, and both are reachable
without the other so each is exercisable on its own. What is owned here is the
STEP ATTRIBUTION across the join: a failed read is the clause's "the files
read" step, which the publication layer never sees and therefore cannot name.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from urllib.parse import quote

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_FILES_READ,
    PreservedTree,
    PublishFailure,
    publish_preserved_tree,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import FabroHttpPort
from livespec_orchestrator_beads_fabro.commands._fabro_run_files import (
    RunFile,
    RunFilesUnreadable,
    read_run_files,
)
from livespec_orchestrator_beads_fabro.commands._fabro_stage_diffs import (
    stage_diffs_from_run_state,
)
from livespec_orchestrator_beads_fabro.commands._unified_patch_apply import (
    PatchRefused,
    apply_unified_patch,
    patched_mode,
)

__all__: list[str] = ["preserved_tree_message", "publish_run_tree"]

_FORGE_TIMEOUT_SECONDS = 120.0
_STATE_READ_TIMEOUT_SECONDS = 300.0


def preserved_tree_message(*, work_item_id: str, run_id: str) -> str:
    """The commit message the preservation commit carries.

    It says on its own face that the commit is a RECOVERY ARTIFACT, because the
    one way this ref does harm is being mistaken for work to land: it ran no
    hook, passed no check suite and carries no Red/Green trailers.
    """
    return (
        f"fabro({run_id}): preserved tree of a checkpoint-failed run for {work_item_id}\n"
        "\n"
        "Recovery artifact, NOT a commit to land: these are the changed files the\n"
        "factory still held after the run's engine checkpoint failed. No hook ran\n"
        "and no check suite passed on them. Recover by checking out this commit's\n"
        "parent and taking this tree onto it as uncommitted work.\n"
    )


def publish_run_tree(
    *,
    port: FabroHttpPort,
    runner: CommandRunner,
    repo: Path,
    work_item_id: str,
    run_id: str,
    base_commit: str,
) -> PreservedTree | PublishFailure:
    """Read one run's changed files from its factory and publish them.

    An unreadable read is reported as the FILES-READ step rather than let the
    publication proceed on an empty file set: publishing nothing would create a
    ref whose tree equals the base commit's, which reads as a run that changed
    nothing -- the one conclusion this whole clause exists to prevent.

    THE WHOLE READ is handed on rather than its files alone, so what the factory
    said it SERVED -- the scope and the source -- reaches the ledger comment that
    names the ref. Re-deriving either at the record would be a second account of
    one reading, and nothing at the record could ask the factory anyway: by then
    the run is pruned.
    """
    read = read_run_files(port=port, run_id=run_id)
    if isinstance(read, RunFilesUnreadable):
        return PublishFailure(step=STEP_FILES_READ, detail=read.detail)
    discrepancy = _empty_run_files_discrepancy(port=port, run_id=run_id, file_count=len(read.files))
    if discrepancy is not None:
        return PublishFailure(step=STEP_FILES_READ, detail=discrepancy, discrepancy=True)
    resolved = _resolved_files(runner=runner, repo=repo, base_commit=base_commit, files=read.files)
    if isinstance(resolved, PublishFailure):
        return resolved
    return publish_preserved_tree(
        runner=runner,
        repo=repo,
        work_item_id=work_item_id,
        base_commit=base_commit,
        read=replace(read, files=resolved),
        message=preserved_tree_message(work_item_id=work_item_id, run_id=run_id),
    )


def _empty_run_files_discrepancy(
    *, port: FabroHttpPort, run_id: str, file_count: int
) -> str | None:
    """Refuse an empty run-files answer when run state retains stage diffs.

    An empty files list is normally a valid account of a run that changed
    nothing.  It becomes unsafe only when the same factory's run state still
    carries a non-empty stage-diff artifact: publishing then would manufacture
    a preservation ref whose tree says the run changed nothing despite the
    retained evidence to the contrary.
    """
    if file_count != 0:
        return None
    state = port.run_state(run_id=run_id, timeout_seconds=_STATE_READ_TIMEOUT_SECONDS)
    if not state.succeeded:
        return None
    stage_diffs = stage_diffs_from_run_state(run_state=state.payload)
    retained = tuple(stage_diff for stage_diff in stage_diffs if stage_diff.payload)
    if not retained:
        return None
    return (
        f"run-files read for {run_id} reported zero changed files, but the run state retains"
        f" {len(retained)} non-empty stage diff artifact(s); refusing to publish an empty tree"
    )


def _resolved_files(
    *, runner: CommandRunner, repo: Path, base_commit: str, files: tuple[RunFile, ...]
) -> tuple[RunFile, ...] | PublishFailure:
    """Every file with its bytes: a final-patch entry's patch applied to its base file.

    A final-patch read is the NORMAL input of a publish that runs after the run finished (the
    sandbox is released at finish), so its null-contents entries are built here, not refused. The
    base file is the forge's copy at the run's base commit; an added file has none. An unreadable
    base, or a patch that does not apply to it, is the FILES-READ step failing closed: a tree
    built from a patch applied to the wrong text would misreport the run.
    """
    resolved: list[RunFile] = []
    for changed in files:
        if changed.patch is None:
            resolved.append(changed)
            continue
        base: bytes | None = None
        if changed.base_path is not None:
            fetched = runner.run(
                argv=[
                    "gh",
                    "api",
                    "-H",
                    "Accept: application/vnd.github.raw",
                    f"/repos/{{owner}}/{{repo}}/contents/{quote(changed.base_path)}?ref={base_commit}",
                ],
                cwd=repo,
                timeout_seconds=_FORGE_TIMEOUT_SECONDS,
            )
            if fetched.exit_code != 0:
                return PublishFailure(
                    step=STEP_FILES_READ,
                    detail=(
                        f"the forge could not read {changed.base_path} at the run's base commit"
                        f" {base_commit} to apply its patch: exit {fetched.exit_code}"
                    ),
                )
            base = fetched.stdout.encode("utf-8")
        applied = apply_unified_patch(base=base, patch=changed.patch)
        if isinstance(applied, PatchRefused):
            return PublishFailure(
                step=STEP_FILES_READ,
                detail=f"the run's patch for {changed.path} does not apply: {applied.detail}",
            )
        resolved.append(
            RunFile(
                path=changed.path,
                content=applied.content,
                mode=patched_mode(patch=changed.patch) or changed.mode,
            )
        )
    return tuple(resolved)
