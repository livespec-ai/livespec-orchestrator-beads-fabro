"""The dispatcher names the fleet's repositories under the livespec-ai organization.

The fleet moves from the `thewoolleyman` account to the `livespec-ai` GitHub
organization (livespec-dev-tooling plan stale-base-merge-options, note 005).
After the move every `github.com/thewoolleyman/<repo>` URL only works through
GitHub's redirect, which breaks the day the old name is reused. These are the
repository URLs the dispatcher clones from, installs from, or probes, so each
one must name the organization directly.
"""

from livespec_orchestrator_beads_fabro.commands._dispatcher_driver_hooks_claude import (
    claude_materialize_script,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_driver_hooks_codex import (
    codex_materialize_script,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_integration_defaults import (
    FLEET_CORE_REPO_URL,
    RELEASE_REPOSITORY_URL,
)

_OLD_OWNER = "thewoolleyman/"


def test_the_fleet_core_default_names_the_organization() -> None:
    assert FLEET_CORE_REPO_URL == "https://github.com/livespec-ai/livespec.git"


def test_the_release_repository_names_the_organization() -> None:
    assert RELEASE_REPOSITORY_URL == (
        "https://github.com/livespec-ai/livespec-orchestrator-beads-fabro.git"
    )


def test_the_claude_driver_is_materialized_from_the_organization() -> None:
    script = claude_materialize_script()
    assert "https://github.com/livespec-ai/livespec-driver-claude.git" in script
    assert '"repo": "livespec-ai/livespec-driver-claude"' in script
    assert _OLD_OWNER not in script


def test_the_codex_driver_is_materialized_from_the_organization() -> None:
    script = codex_materialize_script()
    assert "https://github.com/livespec-ai/livespec-driver-codex.git" in script
    assert _OLD_OWNER not in script
