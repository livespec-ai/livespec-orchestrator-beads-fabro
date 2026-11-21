"""The one place a repository's name is read off a root path a CLI handed in.

A CLI `--project-root` or `--repo` is usually relative, and the relative root `.` has the EMPTY
string as its `Path.name`. A name derived from the unresolved path therefore comes out empty for
the most common invocation, and every identity built on it degrades with it: the hygiene attention
candidates keyed `hygiene:<kind>:<repo>` ended in a bare colon the runtime validator refuses
(bd-ib-sliucq), and the calibration, reconcile-pass and proof-rendering lanes labelled their
records with an empty repository. Resolve first, then take the name.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = ["repository_name"]


def repository_name(*, root: Path) -> str:
    """Return the repository's directory name for `root`, however `root` was spelled."""
    return root.resolve().name
