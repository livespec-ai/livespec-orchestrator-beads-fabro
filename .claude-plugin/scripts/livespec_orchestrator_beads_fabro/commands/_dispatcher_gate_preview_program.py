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
import time
from pathlib import Path

FAILED_TARGETS_HEADER = re.compile(r"^Failed targets \(\d+\):\s*$", re.MULTILINE)
FAILED_TARGET_LINE = re.compile(r"^\s+-\s+(\S+)\s*$")
PYTEST_PROGRESS_FAILURE = re.compile(r"^(\S+::.+?)\s+FAILED(?:\s|$)", re.MULTILINE)
# A parametrize id may hold " - " inside its brackets, so the id closes at the
# first "]" that is followed by the summary's " - " separator or the line end.
PYTEST_FAILURE_SUMMARY = re.compile(
    r"^FAILED\s+([^\s\[]+::[^\s\[]*(?:\[.*?\])?)(?=\s+-\s|\s*$)", re.MULTILINE
)
SKIP_VARIABLE = re.compile(r"^LIVESPEC_.*(?:_SKIP|_RELAX|_DISABLE)(?:_|$)")
CHECKPOINT_SUBJECT = re.compile(r"^fabro\([^)]*\): ")
NO_MATCHING_STAGED_FILES = re.compile(r"\(skip\) no matching staged files")
HOOK_STEP_RAN = re.compile(r"(?:┃\s+\S+\s+\u276f|(?:✔️|🥊)\s+\S+\s+\(\d+(?:\.\d+)? seconds\))")
CHECKPOINT_RUN_TRAILER = re.compile(r"^Fabro-Run: ", re.MULTILINE)
CHECKPOINT_LIMIT = 500
GREEN_RESULT_NAME = "livespec-implement-gate-preview-green-result.json"
RESULT_NAME_TEMPLATE = "livespec-implement-gate-preview-{stage}-result.json"
LOG_NAME_TEMPLATE = "livespec-implement-gate-preview-{stage}.{stream}.log"
LEFTHOOK_STEP = re.compile(r"\u2503\s+(\S+)\s+\u276f")
PROGRESS_SECONDS_VARIABLE = "LIVESPEC_GATE_PREVIEW_PROGRESS_SECONDS"
# A caller reading the output before the hook ends sees a progress line at least
# this often (bd-ib-42erfz); the variable may shorten the cadence, never lengthen it.
DEFAULT_PROGRESS_SECONDS = 30
NOT_FINISHED_EXIT = 75
OUTPUT_TAIL_LINES = 40
# A tail line carrying a credential-shaped value is replaced wholesale, as the
# needs-human writer does: a tokenized URL, a well-known token prefix, or an
# assignment to a credential-named variable.  The record is durable and the
# completion node copies the tail into the handoff and stage cause.
CREDENTIAL_LINE = re.compile(
    r"[a-zA-Z0-9_-]+:[^@\s/]+@"
    r"|\b(?:gh[pousr]_|github_pat_|glpat-|xox[abprs]-|sk-)[A-Za-z0-9_-]{8,}"
    r"|(?:token|secret|password|passwd|api[_-]?key|authorization|bearer)\w*\s*[=:]\s*\S",
    re.IGNORECASE,
)
REDACTION_MARKER = "[redacted]"


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


def latest_checkpoint(root):
    """Return this run's newest checkpoint, if its history carries one.

    ``dispatch_base`` deliberately walks past consecutive checkpoints so the
    preview can identify every path that ``commit_green`` will fold.  That is
    not, however, the tree the hook is meant to inspect: a Green run's latest
    checkpoint is the tree it will hand to the commit node.  Keep these two
    choices separate.
    """
    ref = "HEAD"
    for _ in range(CHECKPOINT_LIMIT):
        if checkpoint_commit(ref, root):
            return ref
        parent = command("git", "rev-parse", "--verify", f"{ref}~1", cwd=root, check=False)
        if parent.returncode:
            return None
        ref = f"{ref}~1"
    raise RuntimeError("gate preview found too many commits while finding its checkpoint")


def tree_sha(ref, root):
    return git("rev-parse", f"{ref}^{{tree}}", cwd=root).stdout.strip()


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
    if header is not None:
        targets = []
        for line in output[header.end() :].splitlines()[1:]:
            match = FAILED_TARGET_LINE.match(line)
            if match is None:
                break
            targets.append(match.group(1))
        return targets

    # Full-suite pytest output has no hook-provided ``Failed targets`` block.
    # Read both the progress rows and failure summary, retaining first-seen
    # order because pytest normally prints each node id in both places.
    targets = []
    matches = (*PYTEST_PROGRESS_FAILURE.finditer(output), *PYTEST_FAILURE_SUMMARY.finditer(output))
    for match in matches:
        target = match.group(1)
        if target not in targets:
            targets.append(target)
    return targets


def output_tail(output):
    """Keep the final hook diagnostics available when no target summary exists."""
    lines = output.splitlines(keepends=True)[-OUTPUT_TAIL_LINES:]
    return "".join(
        REDACTION_MARKER + "\n" if CREDENTIAL_LINE.search(line) else line for line in lines
    )


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


def preview(stage, test_file, hook_log):
    root = Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()).stdout.strip())
    base = dispatch_base(root)
    checkpoint = latest_checkpoint(root) if stage == "green" else None
    checkpoint_tree = tree_sha(checkpoint, root) if checkpoint else None
    preview_ref = checkpoint or base
    paths = selected_paths(stage, root, test_file, base)
    if not paths:
        return 2, [], [], False, None, None
    preview_root = Path(tempfile.mkdtemp(prefix="livespec-gate-preview-", dir=preview_parent()))
    unset = []
    tree_mismatch = None
    try:
        git("worktree", "add", "--detach", "--quiet", str(preview_root), preview_ref, cwd=root)
        graded_tree = tree_sha("HEAD", preview_root)
        if checkpoint_tree is not None and graded_tree != checkpoint_tree:
            tree_mismatch = {
                "graded_tree_sha": graded_tree,
                "latest_checkpoint_tree_sha": checkpoint_tree,
            }
        for path in paths:
            copy_path(path, root, preview_root)
        if checkpoint is None:
            git("add", "--all", "--", *paths, cwd=preview_root)
        else:
            # The hook must see the same affected-path scope that commit_green
            # gets after folding checkpoint commits, while its HEAD must remain
            # the latest checkpoint tree.  Seed the disposable index with the
            # pre-checkpoint base, which makes checkpoint-carried paths visible
            # to hook selectors without moving HEAD.  Only post-checkpoint
            # edits need ordinary staging on top of that index.
            git("read-tree", base, cwd=preview_root)
            after_checkpoint = changed_paths(root, checkpoint)
            if after_checkpoint:
                git("add", "--all", "--", *after_checkpoint, cwd=preview_root)
        hook_path = git(
            "rev-parse", "--git-path", "hooks/pre-commit", cwd=preview_root
        ).stdout.strip()
        hook = Path(hook_path)
        if not hook.is_file():
            return 0, [], unset, True, None, tree_mismatch
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
            return trust.returncode, [], unset, False, None, tree_mismatch
        exports, exports_status = just_exports(cwd=preview_root, environment=environment)
        if exports_status:
            return exports_status, [], unset, False, None, tree_mismatch
        environment.update(exports)
        # The hook's output streams into the log the caller follows (bd-ib-42erfz):
        # captured in memory, nothing reached a caller until the whole aggregate
        # finished, and a caller whose tool call ended first saw nothing at all.
        sys.stdout.flush()
        sys.stderr.flush()
        offset = hook_log.stat().st_size
        with open(hook_log, "ab") as sink:
            returncode = subprocess.run(
                [str(hook)], cwd=preview_root, env=environment,
                stdin=subprocess.DEVNULL, stdout=sink, stderr=sink, check=False,
            ).returncode
        with open(hook_log, "rb") as source:
            source.seek(offset)
            output = source.read().decode("utf-8", errors="replace")
        preview_ran = bool(HOOK_STEP_RAN.search(output)) or not bool(
            NO_MATCHING_STAGED_FILES.search(output)
        )
        return returncode, failed_targets(output), unset, preview_ran, output, tree_mismatch
    except (OSError, RuntimeError) as error:
        print(error, file=sys.stderr)
        return 2, [], unset, False, None, tree_mismatch
    finally:
        command("git", "worktree", "remove", "--force", str(preview_root), cwd=root, check=False)
        shutil.rmtree(preview_root, ignore_errors=True)


def toplevel():
    return Path(git("rev-parse", "--show-toplevel", cwd=Path.cwd()).stdout.strip())


def record_path(root, stage):
    """The stage's record, outside the commit tree and scoped to this clone.

    The completion gate must grade the last completed preview, rather than an
    agent's transcription of it in the append-only handoff.  `git-path` keeps
    that evidence scoped to this run's clone.  While a preview runs, the record
    names it as running and carries no `status`; its verdict replaces it.
    """
    name = GREEN_RESULT_NAME if stage == "green" else RESULT_NAME_TEMPLATE.format(stage=stage)
    return root / git("rev-parse", "--git-path", name, cwd=root).stdout.strip()


def log_paths(record, stage):
    return (
        record.with_name(LOG_NAME_TEMPLATE.format(stage=stage, stream="out")),
        record.with_name(LOG_NAME_TEMPLATE.format(stage=stage, stream="err")),
    )


def write_json(path, data):
    """Replace the record whole, so a stopped writer never leaves malformed JSON."""
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def read_json(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        return stat.rsplit(")", 1)[1].split()[0] not in ("Z", "X")
    except (OSError, IndexError):
        pass
    try:
        os.kill(pid, 0)
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def descendants(pid):
    """Every process below `pid`, shallowest first."""
    children = {}
    try:
        entries = os.listdir("/proc")
    except OSError:
        return []
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            stat = Path(f"/proc/{entry}/stat").read_text(encoding="utf-8")
            parent = int(stat.rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(parent, []).append(int(entry))
    found, frontier = [], [pid]
    while frontier:
        frontier = [child for parent in frontier for child in sorted(children.get(parent, []))]
        found.extend(frontier)
    return found


def running_just_command(pid):
    """The outermost `just` invocation below the worker: the hook step's own command."""
    for child in descendants(pid):
        try:
            raw = Path(f"/proc/{child}/cmdline").read_bytes()
        except OSError:
            continue
        argv = [part.decode("utf-8", errors="replace") for part in raw.split(b"\0") if part]
        if argv and os.path.basename(argv[0]) == "just":
            return " ".join(argv)[:160]
    return None


def current_step(output, pid):
    """Name the hook step that is running.

    The hook runner prints a step's header only when that step FINISHES (measured on
    v1.13.6 writing to a pipe), so the newest header names the step before the
    running one.  The running step's own command is the outermost `just`
    process below the worker, so that leads; the header is reported as what it is.
    """
    headers = LEFTHOOK_STEP.findall(output)
    running = running_just_command(pid)
    finished = f"the hook runner last reported {headers[-1]} as finished" if headers else ""
    if running:
        return f"`{running}`" + (f" ({finished})" if finished else "")
    if finished:
        return f"the hook ({finished})"
    return "preparing the preview worktree (no hook step started yet)"


def progress_seconds():
    try:
        seconds = float(os.environ.get(PROGRESS_SECONDS_VARIABLE, DEFAULT_PROGRESS_SECONDS))
    except ValueError:
        seconds = DEFAULT_PROGRESS_SECONDS
    return min(max(seconds, 0.2), DEFAULT_PROGRESS_SECONDS)


def relay(path, offsets, stream):
    try:
        with open(path, "rb") as source:
            source.seek(offsets.get(path, 0))
            chunk = source.read()
    except OSError:
        return ""
    offsets[path] = offsets.get(path, 0) + len(chunk)
    text = chunk.decode("utf-8", errors="replace")
    if text:
        stream.write(text)
        stream.flush()
    return text


def running_record(stage, pid, started, record):
    return {
        "preview": "running",
        "stage": stage,
        "pid": pid,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "started_epoch": started,
        "record": str(record),
        "check_again": f"{sys.argv[0]} {stage} --status",
    }


def follow(stage, record, pid, started):
    """Relay the worker's output, print progress at the cadence, return its final record."""
    out_log, err_log = log_paths(record, stage)
    offsets = {}
    output = ""
    interval = progress_seconds()
    last_progress = time.monotonic()
    while True:
        output += relay(out_log, offsets, sys.stdout)
        relay(err_log, offsets, sys.stderr)
        current = read_json(record)
        if current is not None and "status" in current:
            break
        if not pid_alive(pid):
            current = read_json(record)
            if current is not None and "status" in current:
                break
            relay(out_log, offsets, sys.stdout)
            relay(err_log, offsets, sys.stderr)
            return None
        now = time.monotonic()
        if now - last_progress >= interval:
            print(
                f"gate preview ({stage}): still running {current_step(output, pid)}; "
                f"{int(time.time() - started)}s elapsed; if this call ends first the preview "
                f"keeps running and its verdict lands in {record}",
                flush=True,
            )
            last_progress = now
        time.sleep(0.2)
    relay(out_log, offsets, sys.stdout)
    relay(err_log, offsets, sys.stderr)
    return current


def program_argv(stage, test_file, mode):
    test_files = [test_file] if test_file else []
    return [sys.executable, os.path.abspath(__file__), stage, *test_files, mode]


def launch(stage, test_file):
    """Start the worker in its own session and exit, so the caller's ending cannot reach it."""
    record = record_path(toplevel(), stage)
    out_log, err_log = log_paths(record, stage)
    with open(out_log, "ab") as out, open(err_log, "ab") as err:
        worker = subprocess.Popen(
            program_argv(stage, test_file, "--worker"),
            stdin=subprocess.DEVNULL, stdout=out, stderr=err, start_new_session=True,
        )
    print(worker.pid)
    return 0


def work(stage, test_file):
    record = record_path(toplevel(), stage)
    write_json(record, running_record(stage, os.getpid(), time.time(), record))
    status, targets, unset, preview_ran, output, tree_mismatch = preview(
        stage, test_file, log_paths(record, stage)[0]
    )
    report = {
        "status": status,
        "failed_targets": targets,
        "preview_ran": preview_ran,
        "unset_variables": unset,
    }
    if status != 0 and not targets and output is not None:
        report["output_tail"] = output_tail(output)
    if tree_mismatch is not None:
        report.update(tree_mismatch)
    sys.stdout.flush()
    sys.stderr.flush()
    write_json(record, report)
    return status


def died(stage, record, current):
    report = {**(current or {}), "preview": "died-without-verdict", "stage": stage}
    report.pop("check_again", None)
    write_json(record, report)
    return report


def status_of(stage):
    record = record_path(toplevel(), stage)
    current = read_json(record)
    if current is None:
        print(json.dumps({"preview": "absent", "stage": stage, "record": str(record)}))
        return 2
    if "status" in current:
        print(json.dumps(current, sort_keys=True))
        return current["status"]
    if current.get("preview") == "running" and not pid_alive(current.get("pid")):
        current = died(stage, record, current)
    print(json.dumps(current, sort_keys=True))
    return NOT_FINISHED_EXIT


def run(stage, test_file):
    root = toplevel()
    record = record_path(root, stage)
    current = read_json(record)
    if (
        current is not None
        and "status" not in current
        and current.get("preview") == "running"
        and pid_alive(current.get("pid"))
    ):
        pid, started = current["pid"], float(current.get("started_epoch") or time.time())
        print(
            f"gate preview ({stage}): an earlier preview (pid {pid}, started "
            f"{current.get('started_at')}) is still running; following it to its verdict "
            "instead of starting a second one. Run the preview again after it ends to "
            "preview later changes.",
            flush=True,
        )
    else:
        started = time.time()
        for log in log_paths(record, stage):
            log.write_bytes(b"")
        write_json(record, running_record(stage, None, started, record))
        launched = subprocess.run(
            program_argv(stage, test_file, "--launch"),
            capture_output=True, text=True, check=False, start_new_session=True,
        )
        try:
            pid = int(launched.stdout.strip())
        except ValueError:
            sys.stderr.write(launched.stdout + launched.stderr)
            report = {
                "status": 2, "failed_targets": [], "preview_ran": False, "unset_variables": [],
            }
            write_json(record, report)
            print(json.dumps(report, sort_keys=True))
            return 2
    report = follow(stage, record, pid, started)
    if report is None:
        report = died(stage, record, read_json(record))
        print(
            f"gate preview ({stage}): the preview process ended without a verdict",
            file=sys.stderr,
        )
        print(json.dumps(report, sort_keys=True))
        return NOT_FINISHED_EXIT
    print(json.dumps(report, sort_keys=True))
    return report["status"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=("red", "green"))
    parser.add_argument("test_file", nargs="?")
    parser.add_argument(
        "--status", action="store_true",
        help="print the stage's record without waiting: exit 75 while it runs, else its verdict",
    )
    parser.add_argument("--launch", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.status:
        return status_of(args.stage)
    if (args.stage == "red") != (args.test_file is not None):
        parser.error("red requires the test file path commit_red will stage; green takes none")
    if args.launch:
        return launch(args.stage, args.test_file)
    if args.worker:
        return work(args.stage, args.test_file)
    return run(args.stage, args.test_file)


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
