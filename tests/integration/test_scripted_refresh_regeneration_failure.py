"""The clean-rebase generated-record regeneration failure is terminal and explicit."""

# ruff: noqa: SLF001

# This control imports the execution fixture's private harness deliberately:
# duplicating its real-origin setup would test a second implementation instead
# of the `pr_refresh` bytes the fixture is designed to execute.

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType


def _refresh_execution_module() -> ModuleType:
    """Load the real-refresh harness so this control executes shipped stage bytes."""
    path = Path(__file__).with_name("test_scripted_refresh_execution.py")
    spec = importlib.util.spec_from_file_location("scripted_refresh_execution", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_a_nonconvergent_regenerated_record_names_its_file_and_generator(tmp_path: Path) -> None:
    """One regeneration is retried exactly once for verification, then fails closed.

    The generator writes a different record for each invocation.  The refresh's
    first reading finds a stale record, its one permitted regeneration commits
    the next output, and its verification sees a different output again.  That
    is not a repairable rebase failure: the stage must retain the exact record
    path and generator argv in its failure rather than spend a repair round.
    """
    refresh = _refresh_execution_module()
    declaration = json.dumps(
        {
            "livespec-orchestrator-beads-fabro": {
                "dispatcher": {
                    "record_files": [
                        {"path": refresh._RECORD_JSON, "generator": ["sh", "generate.sh"]}
                    ]
                }
            }
        }
    )
    box = refresh._build(
        root=tmp_path,
        declaration=declaration,
        record_json="generation: 0\n",
        extra_files={
            "generate.sh": (
                "#!/bin/sh\n"
                "next=$(( $(cat ../generation) + 1 ))\n"
                "printf '%s\\n' \"$next\" > ../generation\n"
                "printf 'generation: %s\\n' \"$next\" > record.json\n"
            ),
        },
    )
    _ = (tmp_path / "generation").write_text("0\n", encoding="utf-8")
    _ = subprocess.run(
        ["sh", "generate.sh"], cwd=box.clone, check=True, capture_output=True, text=True
    )
    _ = refresh._git("add", refresh._RECORD_JSON, cwd=box.clone)
    _ = refresh._git("commit", "--quiet", "-m", "chore: refresh generated record", cwd=box.clone)
    _ = refresh._git(
        "push", "--quiet", "--force", "origin", f"HEAD:refs/heads/{refresh._BRANCH}", cwd=box.clone
    )
    _ = (box.state_dir() / refresh.PUBLISH_HEAD_STATE_FILENAME).write_text(
        box.local_head(), encoding="utf-8"
    )
    _ = refresh._advance_default(box=box)

    result = refresh._run(box=box)

    assert result.returncode != 0
    assert "LIVESPEC_PR_REFRESH_GENERATED_RECORD_FILE_REGENERATION_FAILED" in result.stderr
    assert "generated-record-file:record.json" in result.stderr
    assert "regenerate: record.json via sh generate.sh" in result.stderr
    assert "LIVESPEC_REFRESH_REPAIR" not in result.stderr
