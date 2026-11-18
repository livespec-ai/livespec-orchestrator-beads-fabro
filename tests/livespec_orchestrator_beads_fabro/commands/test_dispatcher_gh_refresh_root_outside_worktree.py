"""The refreshing gh wrapper's bundle root lives outside the run's working tree.

The bundle holds the code that mints the run's forge credential. An agent stage can
edit and commit the working tree, so a bundle inside it could act with the credential
when a publication stage next runs (bd-ib-kzgpzm, Scenario 202).
"""

from __future__ import annotations

from pathlib import Path

from livespec_orchestrator_beads_fabro.commands._dispatcher_gh_refresh import (
    DEFAULT_SANDBOX_GH_REFRESH_ROOT,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_helper_materialize import (
    MaterializeRefusal,
    parse_roots,
)

__all__: list[str] = []


def test_publication_tooling_materializes_outside_the_run_worktree() -> None:
    """The default bundle root is not under the sandbox's /workspace working tree."""
    assert not Path(DEFAULT_SANDBOX_GH_REFRESH_ROOT).is_relative_to(Path("/workspace"))


def test_the_unexpanded_default_root_is_refused_by_the_materializer_not_made_a_directory() -> None:
    """A shell-expression root a Python caller adopts unexpanded must never become a path."""
    refused = parse_roots(argv=[f"gh-refresh={DEFAULT_SANDBOX_GH_REFRESH_ROOT}"])
    assert isinstance(refused, MaterializeRefusal)
