"""A failed run's final-patch read is published from the patch, fail-closed when it cannot be.

A final-patch read with null contents is the NORMAL input of a publish that runs after the run's sandbox
was released. The publication builds each entry's bytes from its `unified_patch` over the run's base
commit, publishes removals as null tree entries, and fails closed at the files-read step for a base it
cannot read or a patch that does not apply.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_engine import CommandResult
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree import publish_run_tree
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_publish import (
    STEP_FILES_READ,
    PreservedTree,
    PublishFailure,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_preserved_tree_record import (
    preserved_tree_body,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_http import (
    FabroHttpPort,
    FabroHttpResult,
)
from livespec_orchestrator_beads_fabro.commands._fabro_port_types import FabroTarget

_BASE_COMMIT = "5d511335aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_RUN_ID = "01M7T6HBJQXXXZXZAF0WDH4T4V"
_COMMIT = "c0mm1tc0mm1tc0mm1tc0mm1tc0mm1tc0mm1tc0mm"
_MODIFIED_PATCH = (
    "diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n"
)
_ADDED_PATCH = (
    "diff --git a/new.sh b/new.sh\nnew file mode 100755\n--- /dev/null\n+++ b/new.sh\n"
    "@@ -0,0 +1,2 @@\n+echo\n+hi\n"
)


def _entry(*, name: str, kind: str, patch: str | None, old: str | None = None) -> dict[str, object]:
    return {
        "change_kind": kind,
        "new_file": {"name": name, "contents": None},
        "old_file": {"name": old if old is not None else name, "contents": None},
        "unified_patch": patch,
    }


def _payload(*, entries: list[dict[str, object]]) -> dict[str, object]:
    return {
        "data": entries,
        "meta": {
            "degraded": True,
            "degraded_reason": "sandbox_gone",
            "scope": "committed",
            "source": "final_patch",
        },
    }


@dataclass(kw_only=True)
class _Transport:
    payload: dict[str, object]

    def send(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
        timeout_seconds: float,
    ) -> FabroHttpResult:
        _ = (method, url, headers, body, timeout_seconds)
        return FabroHttpResult(
            status=200, body=json.dumps(self.payload), error=None, payload=None, succeeded=True
        )


@dataclass(kw_only=True)
class _Forge:
    """Answers the base-file read from `bases` and every other `gh api` call with an object name."""

    bases: dict[str, str]
    fetch_exit: int = 0
    bodies: list[object] = field(default_factory=list)
    fetched: list[str] = field(default_factory=list)
    answers: list[str] = field(
        default_factory=lambda: ["basetree", "blob1", "blob2", "treesha", _COMMIT, ""]
    )
    posted: int = 0

    def run(
        self,
        *,
        argv: list[str],
        cwd: Path,
        timeout_seconds: float,
        env: Mapping[str, str | None] | None = None,
        stdin: int | None = None,
    ) -> CommandResult:
        _ = (cwd, timeout_seconds, env)
        if "Accept: application/vnd.github.raw" in argv:
            self.fetched.append(argv[-1])
            path = argv[-1].split("/contents/")[1].split("?")[0]
            return CommandResult(
                exit_code=self.fetch_exit, stdout=self.bases.get(path, ""), stderr=""
            )
        if stdin is not None:
            self.bodies.append(json.loads(os.pread(stdin, 1_000_000, 0).decode("utf-8")))
        answer = self.answers[self.posted] if self.posted < len(self.answers) else ""
        self.posted += 1
        return CommandResult(exit_code=0, stdout=f"{answer}\n", stderr="")


def _publish(*, payload: dict[str, object], forge: _Forge) -> PreservedTree | PublishFailure:
    return publish_run_tree(
        port=FabroHttpPort(
            target=FabroTarget(server_url="https://f.example:32276"),
            transport=_Transport(payload=payload),
        ),
        runner=forge,
        repo=Path("/nonexistent"),
        work_item_id="bd-ib-ph62fj",
        run_id=_RUN_ID,
        base_commit=_BASE_COMMIT,
    )


def test_modified_added_and_removed_entries_are_published_from_a_final_patch() -> None:
    forge = _Forge(bases={"x.py": "a\nb\nc\n"})
    payload = _payload(
        entries=[
            _entry(name="x.py", kind="modified", patch=_MODIFIED_PATCH),
            _entry(name="new.sh", kind="added", patch=_ADDED_PATCH, old=""),
            _entry(name="gone.py", kind="deleted", patch="diff --git a/gone.py b/gone.py\n"),
        ]
    )

    published = _publish(payload=payload, forge=forge)

    assert isinstance(published, PreservedTree), published
    assert published.degraded_reason == "sandbox_gone"
    # Only the modified file's base is read; an added file has none and a removal needs none.
    assert [f.split("/contents/")[1].split("?")[0] for f in forge.fetched] == ["x.py"]
    assert forge.fetched[0].endswith(f"?ref={_BASE_COMMIT}")
    assert forge.bodies[0] == {"content": "YQpCCmMK", "encoding": "base64"}  # a, B, c
    assert forge.bodies[1] == {"content": "ZWNobwpoaQo=", "encoding": "base64"}  # echo, hi
    assert forge.bodies[2] == {
        "base_tree": "basetree",
        "tree": [
            {"path": "x.py", "mode": "100644", "type": "blob", "sha": "blob1"},
            {"path": "new.sh", "mode": "100755", "type": "blob", "sha": "blob2"},
            {"path": "gone.py", "mode": "100644", "type": "blob", "sha": None},
        ],
    }


def test_a_patch_that_does_not_apply_to_the_base_fails_closed_at_files_read() -> None:
    forge = _Forge(bases={"x.py": "a\nz\nc\n"})
    payload = _payload(entries=[_entry(name="x.py", kind="modified", patch=_MODIFIED_PATCH)])

    failure = _publish(payload=payload, forge=forge)

    assert isinstance(failure, PublishFailure)
    assert failure.step == STEP_FILES_READ
    assert "x.py" in failure.detail
    assert forge.posted == 0


def test_an_unreadable_base_file_fails_closed_at_files_read() -> None:
    forge = _Forge(bases={}, fetch_exit=1)
    payload = _payload(entries=[_entry(name="x.py", kind="modified", patch=_MODIFIED_PATCH)])

    failure = _publish(payload=payload, forge=forge)

    assert isinstance(failure, PublishFailure)
    assert failure.step == STEP_FILES_READ
    assert "x.py" in failure.detail
    assert forge.posted == 0


def test_the_comment_names_the_degraded_reason_beside_the_scope_and_source() -> None:
    preserved = PreservedTree(
        ref="refs/livespec/preserved-publish/bd-ib-ph62fj/c",
        commit="c",
        file_count=1,
        scope="committed",
        source="final_patch",
        degraded_reason="sandbox_gone",
    )
    plain = PreservedTree(ref="r", commit="c", file_count=1, scope="committed", source="sandbox")

    degraded_body = preserved_tree_body(
        work_item_id="bd-ib-ph62fj",
        run_id=_RUN_ID,
        factory="petri",
        base_commit=_BASE_COMMIT,
        preserved=preserved,
    )
    plain_body = preserved_tree_body(
        work_item_id="bd-ib-ph62fj",
        run_id=_RUN_ID,
        factory="petri",
        base_commit=_BASE_COMMIT,
        preserved=plain,
    )

    assert "served degraded reason: sandbox_gone" in degraded_body
    assert "served source: final_patch" in degraded_body
    assert "degraded reason" not in plain_body
