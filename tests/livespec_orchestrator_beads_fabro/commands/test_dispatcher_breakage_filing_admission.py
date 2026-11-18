"""A breakage item files with manual admission until the per-job dedupe ships."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands import _dispatcher_breakage_filing as filing
from livespec_orchestrator_beads_fabro.types import StoreConfig
from returns.io import IOSuccess


class _Client:
    def update_issue(self, **_: object) -> None:
        return None


def test_breakage_item_files_with_manual_admission() -> None:
    captured: list[object] = []
    config = StoreConfig(
        tenant="breakage", prefix="bd-ib", server_user="breakage", database="breakage", bd_path="bd"
    )
    item_id, problem = filing.file_job(
        context=filing.FilingContext(config=config, client=_Client(), existing={}),
        record=filing.FilingRecord(
            workflow="ci.yml",
            job={"name": "tests", "steps": []},
            url="https://run",
            head_sha="abc",
            tests=(),
            breakage_key="ci.yml:tests:abc",
        ),
        capture=lambda **kwargs: captured.append(kwargs["item"]) or IOSuccess("ready"),
    )
    assert problem is None
    assert item_id is not None
    assert [getattr(item, "admission_policy", None) for item in captured] == ["manual"]
