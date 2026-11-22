"""The launch guard records the workflow node's stage for the publication guard (bd-ib-ssipvb).

The stage reaches the launch guard through the leading env assignment the graph
renderer wrote, before the agent exists to edit it. The guard writes it beside the
publication helpers as `<launcher pid> <stage>`, and the publication guard reads
that record instead of an environment value the agent can set.
"""

import os
import re
import subprocess
from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_credential_use_guard import (
    guard_script_text,
)


def _run_guard(*, tmp_path: Path, stage: str | None) -> str:
    script = tmp_path / "guard.sh"
    script.write_text(guard_script_text(), encoding="utf-8")
    root = tmp_path / "bundle"
    root.mkdir()
    # A Codex-projected factory sandbox exports LIVESPEC_CREDENTIAL_USE_DEADLINE_EPOCH
    # container-wide, and the guard refuses an unprotected declaration beside a
    # deadline, so an inherited LIVESPEC_CREDENTIAL_USE_* name is dropped here.
    env = {
        **{
            k: v
            for k, v in os.environ.items()
            if k != "LIVESPEC_AGENT_STAGE" and not k.startswith("LIVESPEC_CREDENTIAL_USE_")
        },
        "LIVESPEC_CREDENTIAL_USE_UNPROTECTED": "1",
        "LIVESPEC_SANDBOX_GH_REFRESH_ROOT": str(root),
    }
    if stage is not None:
        env["LIVESPEC_AGENT_STAGE"] = stage
    subprocess.run(
        ["/bin/sh", str(script), "--", "true"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    record = root / "agent-stage"
    return record.read_text(encoding="utf-8") if record.exists() else ""


def test_the_guard_records_the_launched_nodes_stage(tmp_path: Path) -> None:
    assert re.fullmatch(r"\d+ implement\n", _run_guard(tmp_path=tmp_path, stage="implement"))


def test_the_guard_records_nothing_for_a_launch_without_a_stage(tmp_path: Path) -> None:
    assert _run_guard(tmp_path=tmp_path, stage=None) == ""
