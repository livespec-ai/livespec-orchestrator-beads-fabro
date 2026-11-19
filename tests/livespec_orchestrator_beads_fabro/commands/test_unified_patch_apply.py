"""Applying one file's unified patch to its base text, strictly and fail-closed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from livespec_orchestrator_beads_fabro.commands._unified_patch_apply import (
    PatchApplied,
    PatchRefused,
    apply_unified_patch,
    patched_mode,
)

_FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"


def _applied(*, base: bytes | None, patch: str) -> bytes:
    result = apply_unified_patch(base=base, patch=patch)
    assert isinstance(result, PatchApplied), result
    return result.content


def _refused(*, base: bytes | None, patch: str) -> str:
    result = apply_unified_patch(base=base, patch=patch)
    assert isinstance(result, PatchRefused), result
    return result.detail


def test_a_modification_replaces_only_the_hunk_lines() -> None:
    patch = "--- a/x\n+++ b/x\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n"

    assert _applied(base=b"a\nb\nc\nd\n", patch=patch) == b"a\nB\nc\nd\n"


def test_an_added_file_is_built_from_the_patch_alone() -> None:
    patch = "new file mode 100755\n--- /dev/null\n+++ b/x\n@@ -0,0 +1,2 @@\n+one\n+two\n"

    assert _applied(base=None, patch=patch) == b"one\ntwo\n"
    assert patched_mode(patch=patch) == "100755"


def test_a_patch_that_declares_no_mode_reports_none() -> None:
    assert patched_mode(patch="--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n") is None


def test_a_patch_with_no_hunk_and_no_mode_reports_none() -> None:
    assert patched_mode(patch="diff --git a/x b/x\nindex 1..2\n") is None


def test_two_hunks_apply_in_order() -> None:
    base = b"1\n2\n3\n4\n5\n6\n"
    patch = "@@ -1,2 +1,2 @@\n-1\n+one\n 2\n@@ -5,2 +5,2 @@\n 5\n-6\n+six\n"

    assert _applied(base=base, patch=patch) == b"one\n2\n3\n4\n5\nsix\n"


def test_a_deleted_last_line_keeps_the_previous_line_s_newline() -> None:
    assert _applied(base=b"a\nb\n", patch="@@ -2 +2,0 @@\n-b\n") == b"a\n"


def test_a_pure_insertion_after_a_line_is_placed_after_it() -> None:
    assert _applied(base=b"a\nc\n", patch="@@ -1,0 +2 @@\n+b\n") == b"a\nb\nc\n"


def test_a_file_that_gains_a_final_newline_ends_with_one() -> None:
    patch = "@@ -1,2 +1,2 @@\n a\n-b\n\\ No newline at end of file\n+b\n"

    assert _applied(base=b"a\nb", patch=patch) == b"a\nb\n"


def test_a_file_that_loses_its_final_newline_ends_without_one() -> None:
    patch = "@@ -1,2 +1,2 @@\n a\n-b\n+b\n\\ No newline at end of file\n"

    assert _applied(base=b"a\nb\n", patch=patch) == b"a\nb"


def test_an_unchanged_bare_final_line_stays_bare() -> None:
    patch = "@@ -1,2 +1,2 @@\n-a\n+A\n b\n\\ No newline at end of file\n"

    assert _applied(base=b"a\nb", patch=patch) == b"A\nb"


def test_a_patch_emptying_a_file_produces_empty_bytes() -> None:
    assert _applied(base=b"a\n", patch="@@ -1 +0,0 @@\n-a\n") == b""


@pytest.mark.parametrize(
    ("base", "patch", "needle"),
    [
        (b"a\nz\n", "@@ -1,2 +1,2 @@\n a\n-b\n+c\n", "does not match"),
        (b"a\n", "@@ -1,2 +1,2 @@\n a\n-b\n+c\n", "does not match"),
        (b"a\n", "@@ -9,1 +9,1 @@\n-a\n+b\n", "does not fit"),
        (b"a\nb\n", "@@ -2 +2 @@\n-b\n+B\n@@ -1 +1 @@\n-a\n+A\n", "does not fit"),
        (b"a\n", "no hunk here\n", "no hunk"),
        (b"a\n", "@@ -1 +1 @@\n?bad\n", "unexpected line"),
        (b"a\n", "Binary files a/x and b/x differ\n", "binary"),
        (b"a\n", "GIT binary patch\nliteral 1\n", "binary"),
        (b"\xff\xfe", "@@ -1 +1 @@\n-a\n+b\n", "UTF-8"),
    ],
)
def test_a_patch_that_does_not_apply_to_its_base_is_refused(
    base: bytes, patch: str, needle: str
) -> None:
    assert needle in _refused(base=base, patch=patch)


@pytest.mark.parametrize(
    "name",
    [
        "run_files_sandbox_gone_01M7T6W8N0EZ_33_files.json",
        "run_files_sandbox_gone_01M7T6HBJQXX_10_files.json",
    ],
)
def test_every_real_patch_applies_to_the_base_it_describes(name: str) -> None:
    """Each real `unified_patch` applies to a base rebuilt from its own context and removed lines."""
    payload = json.loads((_FIXTURES / name).read_text(encoding="utf-8"))
    for entry in payload["data"]:
        patch = entry["unified_patch"]
        added = entry["change_kind"] == "added"
        base = None if added else _rebuilt_base(patch=patch)
        expected = _expected(patch=patch)
        result = apply_unified_patch(base=base, patch=patch)
        assert isinstance(result, PatchApplied), (entry["new_file"]["name"], result)
        assert result.content.decode("utf-8") == expected


def _hunk_lines(*, patch: str) -> list[str]:
    """The patch from its first hunk header on, so a header line is never read as content."""
    lines = patch.split("\n")
    first = next(i for i, line in enumerate(lines) if line.startswith("@@ "))
    return lines[first:]


def _old_range(*, header: str) -> tuple[int, int]:
    old = header.split(" ")[1].removeprefix("-")
    start, _, length = old.partition(",")
    return int(start), int(length) if length else 1


def _rebuilt_base(*, patch: str) -> bytes:
    """A base the patch applies to: filler up to each hunk, then the hunk's old-side lines."""
    lines = _hunk_lines(patch=patch)
    base: list[str] = []
    bare = False
    for index, line in enumerate(lines):
        if line.startswith("@@ "):
            start, length = _old_range(header=line)
            target = start if length == 0 else start - 1
            held = len(base)
            base.extend(f"filler {held + n}" for n in range(target - held))
        elif line.startswith((" ", "-")):
            base.append(line[1:])
        elif line.startswith("\\") and lines[index - 1].startswith((" ", "-")):
            bare = True
    return ("\n".join(base) + ("" if bare else "\n")).encode("utf-8")


def _expected(*, patch: str) -> str:
    """The text the hunks produce: the same filler, then each hunk's new-side lines."""
    lines = _hunk_lines(patch=patch)
    out: list[str] = []
    consumed = 0
    bare = False
    for index, line in enumerate(lines):
        if line.startswith("@@ "):
            start, length = _old_range(header=line)
            target = start if length == 0 else start - 1
            out.extend(f"filler {consumed + n}" for n in range(target - consumed))
            consumed = target
        elif line.startswith("\\") and lines[index - 1].startswith((" ", "+")):
            bare = True
        elif line.startswith((" ", "+")):
            out.append(line[1:])
            consumed += 1 if line.startswith(" ") else 0
        elif line.startswith("-"):
            consumed += 1
    return "\n".join(out) + ("" if bare else "\n")
