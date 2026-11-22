"""A restored Red test file is projected into the dispatch journal, never silently."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from typing import Protocol, cast


@dataclass(kw_only=True)
class _Journal:
    records: list[dict[str, object]] = field(default_factory=list)

    def append(self, *, record: dict[str, object]) -> None:
        self.records.append(record)


class _JournalMarker(Protocol):
    def __call__(
        self,
        *,
        journal: _Journal,
        work_item_id: str,
        text: str,
    ) -> object: ...


_MODULE = "livespec_orchestrator_beads_fabro.commands._dispatcher_engine_journal"
_RED_COMMIT = "a" * 40
_BLOB = "b" * 40


def _marker(*, path: str) -> str:
    return (
        f"LIVESPEC_RED_TEST_RESTORED: path={path} "
        f"red_commit={_RED_COMMIT} restored_blob={_BLOB}\n"
    )


def test_a_restoration_marker_becomes_a_red_test_restored_row() -> None:
    """The row names the restored path, the Red commit sha and the restored blob."""
    journal_module = importlib.import_module(_MODULE)
    journal_restored = cast("_JournalMarker", journal_module.journal_red_test_restored)
    journal = _Journal()

    journal_restored(journal=journal, work_item_id="bd-ib-v2amjz", text="unrelated output")
    journal_restored(
        journal=journal,
        work_item_id="bd-ib-v2amjz",
        text="stage output\n" + _marker(path="tests/test_a.py") + _marker(path="tests/test_b.py"),
    )

    assert journal.records == [
        {
            "work_item_id": "bd-ib-v2amjz",
            "stage": "red-test-restored",
            "path": path,
            "red_commit": _RED_COMMIT,
            "restored_blob": _BLOB,
        }
        for path in ("tests/test_a.py", "tests/test_b.py")
    ]


def test_the_run_output_pass_writes_the_restoration_row() -> None:
    """The one pass over a run's output that writes the other markers writes this one too."""
    journal_module = importlib.import_module(_MODULE)
    journal_markers = cast("_JournalMarker", journal_module.journal_run_output_markers)
    journal = _Journal()

    _ = journal_markers(
        journal=journal,
        work_item_id="bd-ib-v2amjz",
        text="start\n" + _marker(path="tests/test_a.py") + "end\n",
    )

    assert [record["stage"] for record in journal.records] == ["red-test-restored"]
