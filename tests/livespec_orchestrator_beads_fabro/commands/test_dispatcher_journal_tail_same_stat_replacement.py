"""A journal replaced at the same path is never served from the previous file's cache.

The tail cache keys on the path and trusts inode, size and mtime. A test's
`tmp_path` is named after the test, so once a finished test's directory is
removed the next test of that name gets the SAME path, very often the same
inode, and a same-shaped journal written within one timestamp tick has the same
size and mtime too. A real journal replaced at its path can do the same.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_journal_tail import (
    journal_tail_records,
)


def _line(*, item: str) -> str:
    return json.dumps({"item": item}, sort_keys=True) + "\n"


def test_a_same_size_replacement_with_the_same_inode_and_mtime_is_read_afresh(
    tmp_path: Path,
) -> None:
    journal = tmp_path / "journal.jsonl"
    journal.write_text(_line(item="AAA"), encoding="utf-8")
    observed = journal.stat()
    assert journal_tail_records(journal_path=journal) == ({"item": "AAA"},)

    journal.write_text(_line(item="BBB"), encoding="utf-8")
    os.utime(journal, ns=(observed.st_atime_ns, observed.st_mtime_ns))
    replaced = journal.stat()
    assert (replaced.st_ino, replaced.st_size, replaced.st_mtime_ns) == (
        observed.st_ino,
        observed.st_size,
        observed.st_mtime_ns,
    )

    assert journal_tail_records(journal_path=journal) == ({"item": "BBB"},)
