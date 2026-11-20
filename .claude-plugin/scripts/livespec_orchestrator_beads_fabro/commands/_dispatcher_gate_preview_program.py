"""Materialize the non-mutating commit-gate preview used by Red and Green turns."""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_prepare_payload import (
    PAYLOAD_ENV_VAR,
    PrepareStep,
    payload_write_command,
    render_prepare_step,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)

__all__: list[str] = [
    "GATE_PREVIEW_PROGRAM_FILENAME",
    "gate_preview_prepare_steps_block",
    "gate_preview_program_path_expansion",
    "gate_preview_program_source",
]

GATE_PREVIEW_PROGRAM_FILENAME = "livespec-implement-gate-preview.py"

_PROGRAM_SOURCE = r'''#!/usr/bin/env python3
"""Preview a Red or Green command-node commit without touching its repository state."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

FAILED_TARGETS_HEADER = re.compile(r"^Failed targets \(\d+\):\s*$", re.MULTILINE)
FAILED_TARGET_LINE = re.compile(r"^\s+-\s+(\S+)\s*$")
SKIP_VARIABLE = re.compile(r"^LIVESPEC_.*(?:_SKIP|_RELAX|_DISABLE)(?:_|$)")
CHECKPOINT_SUBJECT = re.compile(r"^fabro\([^)]*\): ")
NO_MATCHING_STAGED_FILES = re.compile(r"\(skip\) no matching staged files")
HOOK_STEP_RAN = re.compile(r"(?:┃\s+\S+\s+\u276f|(?:✔️|🥊)\s+\S+\s+\(\d+(?:\.\d+)? seconds\))")
CHECKPOINT_RUN_TRAILER = re.compile(r"^Fabro-Run: ", re.MULTILINE)
CHECKPOINT_LIMIT = 500
GREEN_RESULT_NAME = "livespec-implement-gate-preview-green-result.json"


def command(*argv, cwd, env=None, check=True):
    result = subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True, check=False)
    if check and result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result


def git(*argv, cwd):
    return command("git", *argv, cwd=cwd)


def checkpoint_commit(ref, root):
    subject_result = command(
        "git", "log", "-1", "--format=%s", ref, cwd=root, check=False
    )
    if subject_result.returncode:
        return False
    message_result = command(
        "git", "log", "-1", "--format=%B", ref, cwd=root, check=False
    )
    if message_result.returncode:
        return False
    subject = subject_result.stdout.strip()
    message = message_result.stdout
    return bool(CHECKPOINT_SUBJECT.match(subject)) and bool(
        CHECKPOINT_RUN_TRAILER.search(message)
    )


def dispatch_base(root):
    ref = "HEAD"
    for _ in range(CHECKPOINT_LIMIT):
        if not checkpoint_commit(ref, root):
            return ref
        ref = f"{ref}~1"
    raise RuntimeError("gate preview found too many consecutive Fabro checkpoint commits")


def changed_paths(root, base):
    tracked = git("diff", "--name-only", "--no-renames", base, cwd=root).stdout.splitlines()
    untracked = git("ls-files", "--others", "--exclude-standard", cwd=root).stdout.splitlines()
    return sorted(set(tracked + untracked))


def selected_paths(stage, root, test_file, base):
    if stage == "red":
        return [test_file]
    return changed_paths(root, base)


def copy_path(path, root, preview):
    source, target = root / path, preview / path
    if source.exists() or source.is_symlink():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target, follow_symlinks=False)
    elif target.is_dir() and not target.is_symlink():
        shutil.rmtree(target)
    else:
        target.unlink(missing_ok=True)


def failed_targets(output):
    header = FAILED_TARGETS_HEADER.search(output)
    if header is None:
        return []
    targets = []
    for line in output[header.end() :].splitlines()[1:]:
        match = FAILED_TARGET_LINE.match(line)
        if match is None:
            break
        targets.append(match.group(1))
    return targets


def skipped_environment():
    names = sorted(
        name
        for name in os.environ
        if name == "LIVESPEC_CHECK_SKIP" or SKIP_VARIABLE.match(name)
    )
    environment = os.environ.copy()
    for name in names:
        environment.pop(name, None)
    return environment, names


def just_exports(*, cwd, environment):
    """Return the environment a hook recipe receives from the repository's justfile.

    The commit hook starts its checks through ``just``, whose exported variables
    become part of the check process environment.  The preview calls the hook
    directly, so it must materialize those exports first or it can approve a
    worker-sensitive test that the real hook rejects.
    """
    if not environment.get("JUST_JUSTFILE") and not any(
        (cwd / name).is_file() for name in ("justfile", "Justfile", ".justfile", ".Justfile")
    ):
        return {}, 0
    result = command("just", "--command", "env", cwd=cwd, env=environment, check=False)
    if result.returncode:
        sys.stderr.write(result.stdout + result.stderr)
        return None, result.returncode
    exports = {}
    for line in result.stdout.splitlines():
        name, separator, value = line.partition("=")
        if separator:
            exports[name] = value
    return exports, 0


def preview_parent():
    """The directory the disposable worktree is made in, never the system temp directory.

    The fleet's coverage configuration omits /tmp/* so the tests' own scratch directories
    are not measured, so a worktree under it has every source file omitted: coverage
    collects nothing and reports 0% (bd-ib-2j5k74). LIVESPEC_GATE_PREVIEW_ROOT names the
    directory; otherwise it is below the home directory.
    """
    named = os.environ.get("LIVESPEC_GATE_PREVIEW_ROOT")
    try:
        parent = Path(named) if named else Path.home() / ".livespec-gate-preview"
        parent.mkdir(parents=True, exist_ok=True)
    except (OSError, RuntimeError) as error:
        print("gate preview parent directory unusable: " + str(error), file=sys.stderr)
        return None
    return str(parent)


def preview(stage, test_file):
    root = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()).stdout.strip())
    base = dispatch_base(root)
    paths = selected_paths(stage, root, test_file, base)
    if not paths:
        return 2, [], [], False
    preview_root = Path(tempfile.mkdtemp(prefix="livespec-gate-preview-", dir=preview_parent()))
    unset = []
    try:
        git("worktree", "add", "--detach", "--quiet", str(preview_root), base, cwd=root)
        for path in paths:
            copy_path(path, root, preview_root)
        git("add", "--all", "--", *paths, cwd=preview_root)
        hook_path = git(
            "rev-parse", "--git-path", "hooks/pre-commit", cwd=preview_root
        ).stdout.strip()
        hook = Path(hook_path)
        if not hook.is_file():
            return 0, [], unset, True
        environment, unset = skipped_environment()
        # The hook selects the scoped affected-tests gate for commits made by an
        # implement turn.  This disposable index is the prospective implement
        # commit, so preview it through that same selection path.  It is also a
        # local preview of that gate rather than a request to delegate a second
        # full pre-commit aggregate to a gate Job.
        environment["LIVESPEC_AUTHORING_TURN"] = "implement"
        environment["LIVESPEC_GATE_CONTEXT"] = "1"
        # The preview is feedback for the changed modules, not a substitute
        # for the commit's import-closure gate or the final aggregate.
        environment["LIVESPEC_GATE_PREVIEW"] = "1"
        trust = command("mise", "trust", cwd=preview_root, env=environment, check=False)
        trust_output = trust.stdout + trust.stderr
        if trust.returncode:
            sys.stderr.write(trust_output)
            return trust.returncode, [], unset, False
        exports, exports_status = just_exports(cwd=preview_root, environment=environment)
        if exports_status:
            return exports_status, [], unset, False
        environment.update(exports)
        result = command(str(hook), cwd=preview_root, env=environment, check=False)
        output = result.stdout + result.stderr
        sys.stdout.write(output)
        preview_ran = bool(HOOK_STEP_RAN.search(output)) or not bool(
            NO_MATCHING_STAGED_FILES.search(output)
        )
        return result.returncode, failed_targets(output), unset, preview_ran
    except (OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 2, [], unset, False
    finally:
        command("git", "worktree", "remove", "--force", str(preview_root), cwd=root, check=False)
        shutil.rmtree(preview_root, ignore_errors=True)


def record_green_result(report):
    """Persist Green's completed tool result outside the commit tree.

    The completion gate must grade the last completed preview, rather than an
    agent's transcription of it in the append-only handoff.  `git-path` keeps
    that evidence scoped to this run's clone, and the replace prevents a
    stopped writer from turning a previous complete record into malformed JSON.
    """
    root = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()).stdout.strip())
    record = Path(git("rev-parse", "--git-path", GREEN_RESULT_NAME, cwd=root).stdout.strip())
    temporary = record.with_name(f"{record.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(report, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, record)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("red", "green"))
    parser.add_argument("test_file", nargs="?")
    args = parser.parse_args()
    if (args.stage == "red") != (args.test_file is not None):
        parser.error("red requires the test file path commit_red will stage; green takes none")
    status, targets, unset, preview_ran = preview(args.stage, args.test_file)
    report = {
        "status": status,
        "failed_targets": targets,
        "preview_ran": preview_ran,
        "unset_variables": unset,
    }
    if args.stage == "green":
        record_green_result(report)
    print(json.dumps(report, sort_keys=True))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
'''


def gate_preview_program_source() -> str:
    """Return the exact stdlib-only program the sandbox executes."""
    return _PROGRAM_SOURCE


def gate_preview_program_path_expansion() -> str:
    """Return the sandbox-local preview path shared by the overlay and prompts."""
    return f"{sandbox_plugins_root_expansion()}/{GATE_PREVIEW_PROGRAM_FILENAME}"


def gate_preview_prepare_steps_block() -> str:
    """Render the prepare step that writes the preview beside the commit runner."""
    root = sandbox_plugins_root_expansion()
    path = gate_preview_program_path_expansion()
    step = PrepareStep(
        script=(
            f'set -eu\nmkdir -p "{root}"\n'
            + payload_write_command(path_word=f'"{path}"')
            + f'\nchmod 755 "{path}"'
        ),
        env={PAYLOAD_ENV_VAR: gate_preview_program_source()},
    )
    return (
        "\n# --- Dispatcher-materialized implement gate preview (bd-ib-cwnt3b) ---\n"
        + render_prepare_step(step=step)
    )
