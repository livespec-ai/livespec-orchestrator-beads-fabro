"""Applying ONE file's unified patch to that file's base text. PURE, STRICT, and fail-closed.

A run's changed files reach the Dispatcher as a final patch whenever the factory's sandbox is gone,
which is the normal path for a publish that runs after the run finished: every entry then carries
its change only as a `unified_patch` and null `contents`. The publication needs the file's BYTES,
so they are built here from the patch and the base text the forge holds for the run's base commit.

STRICT MEANS A CONTEXT OR REMOVED LINE THAT DOES NOT MATCH THE BASE REFUSES THE WHOLE FILE. No fuzz
and no offset search: a patch applied to a base it was not made against would publish a recovery
artifact whose tree disagrees with the run, which is worse than none. A binary patch is refused for
the same reason: this reader has no bytes to build from. An added file has no base, so the patch
carries all of its text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__: list[str] = ["PatchApplied", "PatchRefused", "apply_unified_patch", "patched_mode"]

_HUNK = re.compile(r"^@@ -(?P<old>\d+)(?:,(?P<old_len>\d+))? \+\d+(?:,\d+)? @@")
_MODE = re.compile(r"^(?:new file mode|new mode) (?P<mode>\d{6})$")
_NO_NEWLINE = "\\ No newline at end of file"
_BINARY_MARKERS = ("GIT binary patch", "Binary files ")


@dataclass(frozen=True, kw_only=True)
class PatchApplied:
    """The text the patch produces."""

    content: bytes


@dataclass(frozen=True, kw_only=True)
class PatchRefused:
    """The patch could not be applied to this base, and why."""

    detail: str


@dataclass(frozen=True, kw_only=True)
class _Row:
    """One hunk line: its kind (` `, `-` or `+`), its text, and whether it ends the file bare."""

    kind: str
    text: str
    no_newline: bool = False


@dataclass(frozen=True, kw_only=True)
class _Hunk:
    start: int
    old_len: int
    rows: tuple[_Row, ...]


def patched_mode(*, patch: str) -> str | None:
    """The file mode the patch's own header declares, or None when it declares none."""
    for line in patch.split("\n"):
        if line.startswith("@@"):
            return None
        match = _MODE.match(line)
        if match:
            return match.group("mode")
    return None


def apply_unified_patch(*, base: bytes | None, patch: str) -> PatchApplied | PatchRefused:
    """Apply `patch` to `base` (None for an added file), or say why it does not apply."""
    lines = patch.split("\n")
    if any(marker in line for line in lines for marker in _BINARY_MARKERS):
        return PatchRefused(detail="the patch is a binary patch and carries no text to build from")
    hunks = _hunks(lines=lines)
    if isinstance(hunks, PatchRefused):
        return hunks
    try:
        text = "" if base is None else base.decode("utf-8")
    except UnicodeDecodeError:
        return PatchRefused(detail="the base file is not UTF-8 text")
    return _applied(text=text, hunks=hunks)


def _hunks(*, lines: list[str]) -> list[_Hunk] | PatchRefused:
    """Every hunk of the patch, or the first line that is not part of one."""
    hunks: list[_Hunk] = []
    header: re.Match[str] | None = None
    rows: list[_Row] = []
    for line in lines:
        match = _HUNK.match(line)
        if match is not None:
            _close(hunks=hunks, header=header, rows=rows)
            header, rows = match, []
        elif header is None:
            continue
        elif line == _NO_NEWLINE:
            rows[-1:] = (
                [_Row(kind=rows[-1].kind, text=rows[-1].text, no_newline=True)] if rows else []
            )
        elif line and line[0] in " -+":
            rows.append(_Row(kind=line[0], text=line[1:]))
        elif line:
            return PatchRefused(detail=f"unexpected line in a hunk: {line!r}")
    _close(hunks=hunks, header=header, rows=rows)
    return hunks if hunks else PatchRefused(detail="the patch carries no hunk")


def _close(*, hunks: list[_Hunk], header: re.Match[str] | None, rows: list[_Row]) -> None:
    if header is None:
        return
    old_len = header.group("old_len")
    hunks.append(
        _Hunk(
            start=int(header.group("old")),
            old_len=1 if old_len is None else int(old_len),
            rows=tuple(rows),
        )
    )


def _applied(*, text: str, hunks: list[_Hunk]) -> PatchApplied | PatchRefused:
    final_newline = text.endswith("\n")
    source = text.split("\n")
    if final_newline or text == "":
        _ = source.pop()
    out: list[str] = []
    cursor = 0
    bare_end = False
    for hunk in hunks:
        target = hunk.start if hunk.old_len == 0 else hunk.start - 1
        if target < cursor or target > len(source):
            return PatchRefused(detail=f"the hunk at line {hunk.start} does not fit the base file")
        out.extend(source[cursor:target])
        cursor = target
        for row in hunk.rows:
            if row.kind == "+":
                out.append(row.text)
                bare_end = row.no_newline
                continue
            if cursor >= len(source) or source[cursor] != row.text:
                return PatchRefused(
                    detail=f"the base file does not match the patch at line {cursor + 1}"
                )
            cursor += 1
            if row.kind == " ":
                out.append(row.text)
                bare_end = row.no_newline
    rest = source[cursor:]
    out.extend(rest)
    newline = final_newline if rest else not bare_end
    return PatchApplied(
        content=("\n".join(out) + ("\n" if out and newline else "")).encode("utf-8")
    )
