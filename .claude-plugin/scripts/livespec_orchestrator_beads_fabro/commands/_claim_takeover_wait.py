"""The monotonic wait a one-shot claim writer observes before one retry."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from livespec_orchestrator_beads_fabro._store_claim_tokens import TRANSITION_WAIT_SECONDS

__all__: list[str] = ["TakeoverWait"]


@dataclass(frozen=True, kw_only=True)
class TakeoverWait:
    """Wait out the claim-token takeover interval on one monotonic clock.

    The writer has already made the first observation when it creates this
    wait.  Its fresh retry therefore occurs at least ``seconds`` later on the
    same clock.  The injectable clock and sleeper keep callers' tests from
    waiting in wall-clock time.
    """

    seconds: float = TRANSITION_WAIT_SECONDS
    clock: Callable[[], float] = time.monotonic
    sleep: Callable[[float], None] = time.sleep

    def wait_out(self) -> None:
        """Return only after ``seconds`` have elapsed, despite short sleeps."""
        deadline = self.clock() + self.seconds
        while (remaining := deadline - self.clock()) > 0:
            self.sleep(remaining)
