"""A final-patch read with null contents is the NORMAL, supported input, not an error case.

The petri engine releases a run's sandbox at run finish (`run finished status=success released_count=1`,
the pod killed in the same second) and the publish step then reopens a NEW same-named pod with no
workspace, so every publish that runs after finish reads `meta.source = "final_patch"` with null contents.

Measured on build 55126d726cb3 against the petri factory (:32276), 2026-11-19: once a run's sandbox pod
is gone, `GET /api/v1/runs/<id>/files` answers 200 with `meta.degraded = true`,
`meta.degraded_reason = "sandbox_gone"`, `meta.source = "final_patch"`, and `new_file.contents = null` on
EVERY entry, the change living only in each entry's `unified_patch`. The reader refused such a response
(a null-contents non-removal is fail-closed), so a run that ended `status=success` died at the
publish step `files-read` and its finished work was never published.

The fixtures are the REAL responses, captured unedited for runs 01M7T6W8N0EZEDRNCA612DJJMN (33 files) and
01M7T6HBJQXXXZXZAF0WDH4T4V (10 files). The reader must now carry each entry's patch so the publication can
build the content from it, while a null-contents entry that is NOT a final-patch read stays refused.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._fabro_run_files import (
    RunFiles,
    RunFilesUnreadable,
    run_files_from_payload,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
_REAL = (
    ("run_files_sandbox_gone_01M7T6W8N0EZ_33_files.json", 33),
    ("run_files_sandbox_gone_01M7T6HBJQXX_10_files.json", 10),
)


def _payload(*, name: str) -> dict[str, object]:
    return json.loads((_FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize(("name", "count"), _REAL)
def test_a_final_patch_read_with_null_contents_is_supported_and_carries_every_patch(
    name: str, count: int
) -> None:
    payload = _payload(name=name)

    read = run_files_from_payload(payload=payload)

    assert isinstance(read, RunFiles)
    assert (read.scope, read.source) == ("committed", "final_patch")
    assert len(read.files) == count
    for changed in read.files:
        assert changed.content is None
        assert changed.patch is not None
        assert f"+++ b/{changed.path}" in changed.patch


def test_null_contents_outside_a_final_patch_read_stays_refused() -> None:
    payload = _payload(name=_REAL[1][0])
    meta = payload["meta"]
    assert isinstance(meta, dict)
    meta["source"] = "sandbox"

    read = run_files_from_payload(payload=payload)

    assert isinstance(read, RunFilesUnreadable)
