"""The separately launched entry point of the publication broker.

The workflow starts this process beside an agent node, as its own process and
ideally as a different user, and hands it two files by argv: a launch file naming
the stage, pull request and proof asset store it serves, and a credential file.
Both are read here, once, before any request, and the launch is bound to the
``PublicationBroker`` at construction.  A request is one JSON object per line on
standard input and has no field that maps onto either file, so nothing an agent
sends can change the stage the broker serves or the credential it holds.

Both files are refused unless the broker's own user owns them and no one else can
write the launch file or read the credential file.  That check is what makes the
launch "workflow-owned state": a file an agent could rewrite would let it choose
its own stage.  It only means something when the agent runs as a different user
from the broker, which is how the workflow launches it.

The reply never carries the child's standard error, because that stream belongs to
a process that held the credential.  Wiring an agent-facing client to this entry
point is the following broker-routing item.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import TextIO, cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_command_types import CommandRunner
from livespec_orchestrator_beads_fabro.commands._dispatcher_publication_broker import (
    BrokerRequest,
    BrokerResult,
    PublicationBroker,
    WorkflowLaunch,
)
from livespec_orchestrator_beads_fabro.io import write_stderr, write_stdout

__all__: list[str] = [
    "CREDENTIAL_FILE_FLAG",
    "LAUNCH_FILE_FLAG",
    "credential_reader",
    "load_launch",
    "main",
    "request_from_line",
]

LAUNCH_FILE_FLAG = "--launch-file"
CREDENTIAL_FILE_FLAG = "--credential-file"

_USAGE = (
    f"publication broker refused to start: usage {LAUNCH_FILE_FLAG} <file> "
    f"{CREDENTIAL_FILE_FLAG} <file>"
)
_ARGV_LENGTH = 4
_NO_OTHER_WRITER = 0o022
_NO_OTHER_ACCESS = 0o077


def main(
    *,
    argv: Sequence[str],
    request_lines: Iterable[str],
    runner: CommandRunner,
    cwd: Path,
    stdout: TextIO,
) -> int:
    """Serve one JSON request per line until the stream ends; 1 when it cannot start."""
    pairs = dict(zip(argv[0::2], argv[1::2], strict=False))
    if len(argv) != _ARGV_LENGTH or set(pairs) != {LAUNCH_FILE_FLAG, CREDENTIAL_FILE_FLAG}:
        return _fail(text=_USAGE)
    launch = load_launch(path=Path(pairs[LAUNCH_FILE_FLAG]))
    if isinstance(launch, str):
        return _fail(text=launch)
    credential_file = Path(pairs[CREDENTIAL_FILE_FLAG])
    refusal = _private_file_refusal(
        path=credential_file, kind="credential file", forbidden=_NO_OTHER_ACCESS
    )
    if refusal is not None:
        return _fail(text=refusal)
    broker = PublicationBroker(
        runner=runner,
        credential=credential_reader(path=credential_file),
        cwd=cwd,
        launch=launch,
    )
    for line in request_lines:
        if not line.strip():
            continue
        parsed = request_from_line(line=line)
        result = (
            BrokerResult(refusal=parsed)
            if isinstance(parsed, str)
            else broker.handle(request=parsed)
        )
        write_stdout(text=_reply(result=result), stream=stdout)
        stdout.flush()
    return 0


def credential_reader(*, path: Path) -> Callable[[], str]:
    """Read the credential at each use, so a rotation reaches the next request."""

    def read() -> str:
        return path.read_text(encoding="utf-8").strip()

    return read


def load_launch(*, path: Path) -> WorkflowLaunch | str:
    """Return the launch a workflow-owned file records, or the refusal naming why not."""
    refusal = _private_file_refusal(path=path, kind="launch file", forbidden=_NO_OTHER_WRITER)
    if refusal is not None:
        return refusal
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, ValueError) as error:
        return f"publication broker refused launch file {str(path)!r}: {error}"
    document = _json_object(text=text, what="launch file")
    if isinstance(document, str):
        return document
    problems = _shape_problems(
        document=document,
        required_text=("stage",),
        optional_text=("proof_asset_store", "request_directory"),
        required_int=("pull_request_number",),
    )
    if problems:
        return f"publication broker refused launch file {str(path)!r}: {'; '.join(problems)}"
    return WorkflowLaunch(
        stage=cast("str", document["stage"]),
        pull_request_number=cast("int", document["pull_request_number"]),
        proof_asset_store=cast("str | None", document.get("proof_asset_store")),
        request_directory=_path(value=document.get("request_directory")),
    )


def request_from_line(*, line: str) -> BrokerRequest | str:
    """Parse one untrusted request line, refusing any field the request type lacks."""
    document = _json_object(text=line, what="request")
    if isinstance(document, str):
        return document
    problems = _shape_problems(
        document=document,
        required_text=("operation", "claimed_stage"),
        optional_text=("comment_body", "proof_asset", "proof_asset_name", "proof_asset_store"),
        required_int=("pull_request_number",),
    )
    if problems:
        return f"publication broker refused request: {'; '.join(problems)}"
    return BrokerRequest(
        operation=cast("str", document["operation"]),
        claimed_stage=cast("str", document["claimed_stage"]),
        pull_request_number=cast("int", document["pull_request_number"]),
        comment_body=_path(value=document.get("comment_body")),
        proof_asset=_path(value=document.get("proof_asset")),
        proof_asset_name=cast("str | None", document.get("proof_asset_name")),
        proof_asset_store=cast("str | None", document.get("proof_asset_store")),
    )


def _fail(*, text: str) -> int:
    write_stderr(text=text + "\n")
    return 1


def _reply(*, result: BrokerResult) -> str:
    command = result.command
    return (
        json.dumps(
            {
                "refusal": result.refusal,
                "exit_code": None if command is None else command.exit_code,
                "stdout": None if command is None else command.stdout,
            }
        )
        + "\n"
    )


def _path(*, value: object) -> Path | None:
    return None if value is None else Path(cast("str", value))


def _json_object(*, text: str, what: str) -> dict[str, object] | str:
    try:
        document = cast("object", json.loads(text))
    except ValueError as error:
        return f"publication broker refused {what}: not JSON ({error})"
    if not isinstance(document, dict):
        return f"publication broker refused {what}: not a JSON object"
    return cast("dict[str, object]", document)


def _shape_problems(
    *,
    document: Mapping[str, object],
    required_text: tuple[str, ...],
    optional_text: tuple[str, ...],
    required_int: tuple[str, ...],
) -> list[str]:
    allowed = {*required_text, *optional_text, *required_int}
    problems = [f"unknown field {key!r}" for key in sorted(set(document) - allowed)]
    for key in required_text:
        value = document.get(key)
        if not isinstance(value, str) or not value:
            problems.append(f"{key} must be a non-empty string")
    for key in optional_text:
        value = document.get(key)
        if value is not None and (not isinstance(value, str) or not value):
            problems.append(f"{key} must be a non-empty string or null")
    for key in required_int:
        value = document.get(key)
        if isinstance(value, bool) or not isinstance(value, int):
            problems.append(f"{key} must be an integer")
    return problems


def _private_file_refusal(*, path: Path, kind: str, forbidden: int) -> str | None:
    """Refuse a file the broker's own user does not own or others can reach."""
    lead = f"publication broker refused {kind} {str(path)!r}"
    try:
        info = path.stat()
    except OSError as error:
        return f"{lead}: it cannot be read ({error.strerror})"
    if not stat.S_ISREG(info.st_mode):
        return f"{lead}: it is not a regular file"
    if info.st_uid != os.geteuid():
        return f"{lead}: it is not owned by the broker's own user"
    if stat.S_IMODE(info.st_mode) & forbidden:
        return f"{lead}: its mode lets another user reach it"
    return None
