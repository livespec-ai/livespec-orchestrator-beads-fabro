"""Materialize the exact-object leased publication push `pr_refresh` performs.

WHY A MATERIALIZED PROGRAM RATHER THAN SHELL IN THE NODE. The ratified clause
grants `pr_refresh` ONE rewriting capability and bounds it tightly: "a rewrite
MUST use an explicit lease against the recorded remote head of this run's own
publish branch", and "MUST NOT use bare force, `--no-verify`, or rewrite
another ref". Those are three separate properties, and a `git push` assembled
inline in a node's `script` attribute puts all three one typo away from being
lost -- a `--force` that should have been `--force-with-lease=`, a refspec that
should have named one branch, an expected object that arrived empty and turned
the lease into a no-op.

So the push is a PROGRAM with exactly one exec, and the program validates its
own arguments before reaching it: two arguments or nothing, a non-empty branch,
and an expected object that is a full forty-character lowercase sha. The last
check is the load-bearing one, because `--force-with-lease=<ref>:` with an
EMPTY expected object is accepted by git and means "the ref does not exist" --
so an empty value does not fail, it silently becomes a different and much
weaker assertion.

The program is materialized below the sandbox plugins root at prepare time, the
way `_dispatcher_plugin_cache_gate` already materializes its gate, and the node
fails closed on its absence rather than falling back to an inline push.
"""

from __future__ import annotations

from livespec_orchestrator_beads_fabro.commands._dispatcher_sandbox_plugins import (
    sandbox_plugins_root_expansion,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_tdd_lineage_gate import (
    tdd_lineage_gate_program_body,
)

__all__: list[str] = [
    "PUBLICATION_PUSH_PROGRAM_FILENAME",
    "publication_push_program_path_expansion",
    "publication_push_program_source",
]

PUBLICATION_PUSH_PROGRAM_FILENAME = "livespec-push-exact-head"

_PROGRAM_SOURCE = (
    """#!/bin/sh
set -eu
livespec_validate_tdd_lineage() {
    python3 -c '
"""
    + tdd_lineage_gate_program_body()
    + """'
}
if test "$#" -ne 1 && test "$#" -ne 2; then
    echo 'livespec publication push: expected <branch> <expected-object> or <branch>' >&2
    exit 2
fi
branch=$1
if test -z "$branch"; then
    echo 'livespec publication push: branch is empty' >&2
    exit 2
fi
if test "$#" -eq 2; then
    expected=$2
    if test "${#expected}" -ne 40; then
        echo 'livespec exact-head push: expected object is not a full lowercase sha' >&2
        exit 2
    fi
    case "$expected" in
        *[!0-9a-f]*)
            echo 'livespec exact-head push: expected object is not a full lowercase sha' >&2
            exit 2
            ;;
    esac
    set -- --force-with-lease="refs/heads/$branch:$expected"
else
    if git ls-remote --exit-code --heads origin "refs/heads/$branch" >/dev/null 2>&1; then
        echo 'livespec exact-head push: expected <branch> <expected-object>' >&2
        exit 2
    fi
    set -- -u
fi
livespec_validate_tdd_lineage
exec git push "$@" origin "HEAD:refs/heads/$branch"
"""
)


def publication_push_program_source() -> str:
    """The sandbox helper's exact bytes; its one push pins the expected object."""
    return _PROGRAM_SOURCE


def publication_push_program_path_expansion() -> str:
    """The path both the prepare step and `pr_refresh` resolve."""
    return f"{sandbox_plugins_root_expansion()}/{PUBLICATION_PUSH_PROGRAM_FILENAME}"
