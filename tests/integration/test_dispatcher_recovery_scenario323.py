"""Integration-tier journeys for Scenario 323's run-age recovery rules.

The production recovery router is exercised against the hermetic origin and
factory board shared by the focused regression fixtures.  Reusing that
instrument is intentional: every row still drives ``route_recovery`` through
its real forge, journal, and route-record seams, while this integration module
binds the combined journey to the specification heading.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

_COMMAND_TESTS = Path(__file__).parents[1] / "livespec_orchestrator_beads_fabro" / "commands"


def _fixture_module(name: str) -> ModuleType:
    path = _COMMAND_TESTS / name
    spec = importlib.util.spec_from_file_location(f"scenario323_{path.stem}", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "row_name",
    [
        "an earlier run's needs-human ref loses to a later run's head",
        "an earlier run's preservation ref loses to a later run's head",
        "an earlier run's needs-human ref beats a head its own run published",
    ],
)
def test_scenario323_ranks_a_terminal_ref_against_the_published_run_age(
    row_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite = _fixture_module("test_dispatcher_recovery_seed_precedence.py")
    case_root = tmp_path / row_name.replace(" ", "-")
    case_root.mkdir()

    suite.test_the_source_routing_takes_is_the_one_the_precedence_table_names(
        name=row_name, tmp_path=case_root, monkeypatch=monkeypatch
    )


def test_scenario323_holds_an_unattributable_competing_ref_and_leaves_the_item_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite = _fixture_module("test_dispatcher_recovery_publishing_run_hold.py")
    suite.test_an_unattributable_head_against_a_competing_ref_is_held_under_its_own_measurement(
        tmp_path=tmp_path, monkeypatch=monkeypatch
    )


def test_scenario323_refuses_only_a_same_run_descendant_that_would_lose_work() -> None:
    suite = _fixture_module("test_dispatcher_resume_preserved_descendant.py")
    suite.test_a_same_run_descending_ref_with_more_work_is_a_resume_refusal()
    suite.test_an_unattributed_published_descendant_allows_the_resume()


def test_scenario323_distinguishes_unattributable_head_and_preserved_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    suite = _fixture_module("test_dispatcher_resume_preserved_descendant.py")
    suite.test_a_head_no_journal_row_attributes_names_the_head_row_and_its_command(
        monkeypatch=monkeypatch, tmp_path=tmp_path
    )
    suite.test_a_preserved_run_without_a_journal_position_is_named_instead_of_the_head(
        monkeypatch=monkeypatch, tmp_path=tmp_path
    )


def test_scenario323_attributes_a_trailer_ref_and_ignores_non_competing_refs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise sub-scenarios 5, 7, and 8 through recovery routing's real seams."""
    preserved = _fixture_module("test_dispatcher_recovery_preserved_tree.py")
    precedence = _fixture_module("test_dispatcher_recovery_seed_precedence.py")

    preserved.test_a_needs_human_ref_is_attributed_from_its_tip_trailer()
    preserved.test_an_unattributable_needs_human_ref_with_the_published_heads_tree_is_not_competing()
    precedence.test_the_source_routing_takes_is_the_one_the_precedence_table_names(
        name="the observed published head beats an earlier reclaim's preserved head",
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
    )


def test_scenario323_allows_resume_past_an_earlier_or_non_descending_preserve() -> None:
    """Exercise sub-scenarios 11 and 12 without weakening the same-run refusal."""
    measurement = _fixture_module("test_dispatcher_resume_preserved_descendant_measurement.py")
    descendant = _fixture_module("test_dispatcher_resume_preserved_descendant.py")

    measurement.test_the_measurement_only_refuses_a_descendant_with_a_different_tree(
        answers=(), age="later", expected="none"
    )
    descendant.test_an_unattributed_published_descendant_allows_the_resume()
