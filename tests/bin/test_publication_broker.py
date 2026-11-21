"""Per-wrapper coverage test for bin/publication_broker.py."""

from collections.abc import Callable


def test_publication_broker_wrapper_threads_exit_code(
    wrapper_runner: Callable[[str, str, int], None],
) -> None:
    wrapper_runner(
        "publication_broker.py",
        "livespec_orchestrator_beads_fabro.commands.publication_broker",
        0,
    )
