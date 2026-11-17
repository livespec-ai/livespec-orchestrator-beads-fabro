"""The moved session-headroom dial resolvers keep their design-record docstrings.

The resolvers moved out of `_dispatcher_session_headroom_gate` to keep that
module inside its size limit. A move carries a function's docstring and
comments verbatim, so the reasoning for why each dial needs both a minimum and
a maximum, and why the dials are committed-only, must survive it.
"""

from __future__ import annotations

import inspect

from livespec_orchestrator_beads_fabro.commands import (
    _dispatcher_session_headroom_settings as settings,
)


def test_floor_resolver_explains_why_the_dial_needs_a_maximum() -> None:
    doc = inspect.getdoc(settings.resolve_session_headroom_floor_percent) or ""

    assert "carries a\nminimum and no maximum" in doc
    assert "refuse\nevery covered candidate in the repository forever" in doc


def test_horizon_resolver_keeps_its_mirror_image_and_committed_only_reasoning() -> None:
    doc = inspect.getdoc(settings.resolve_session_headroom_horizon_minutes) or ""

    assert "mirror-image reason the floor does" in doc
    assert "COMMITTED-ONLY, as the clause ratifies it" in doc
    assert "`_drive_config_schema.CONFIG_KEYS`" in doc


def test_module_keeps_the_one_grader_rationale_and_its_minimum() -> None:
    source = inspect.getsource(settings)

    assert "ONE grader for both dials rather than one apiece" in source
    assert "minimum: int" in source
