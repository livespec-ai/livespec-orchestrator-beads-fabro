"""The narrow proof-only acceptance disposition guard."""

from __future__ import annotations

from types import SimpleNamespace
from typing import cast

from livespec_orchestrator_beads_fabro.commands._dispatcher_acceptance_ai import (
    AcceptancePassResult,
)
from livespec_orchestrator_beads_fabro.commands._dispatcher_completion import (
    _proof_only_arm_did_not_reproduce_factory_assertion,
)


def test_a_proof_only_reaccept_does_not_park_a_nonnegative_or_missing_record() -> None:
    """Only the proof-only arm's explicit negative factory assertion suppresses rework."""
    missing_record = cast(AcceptancePassResult, SimpleNamespace(proof=SimpleNamespace(record=None)))

    assert (
        _proof_only_arm_did_not_reproduce_factory_assertion(  # pyright: ignore[reportPrivateUsage]
            acceptance_pass=missing_record
        )
        is False
    )
