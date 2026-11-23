"""Edges for the product logical-line counter."""

from __future__ import annotations

from importlib import import_module

from livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_measure import (
    changed_product_logical_lines,
    is_product_path,
    product_source_prefixes,
)

_counter = import_module("livespec_orchestrator_beads_fabro.commands._dispatcher_cycle_measure")
_PRIVATE = "_"
_docstring_lines = getattr(_counter, _PRIVATE + "docstring_lines")
_walk = getattr(_counter, _PRIVATE + "walk")


def test_comments_docs_formatting_and_invalid_source_are_not_false_product_sizes() -> None:
    assert (
        changed_product_logical_lines(
            before='"""One."""\n\nvalue = render(first, second)\n',
            after='"""A longer doc."""\n# Comment\nvalue = render(\n first,\n second,\n)\n',
        )
        == 0
    )
    assert changed_product_logical_lines(before="value = (\n", after="value = 1\n") is None


def test_missing_or_unparseable_source_declaration_does_not_guess_product_trees() -> None:
    assert product_source_prefixes(pyproject_text="[tool.other]\nx = 1\n") == ()
    assert product_source_prefixes(pyproject_text="not = = toml") == ()


def test_counter_helpers_reject_non_product_paths_and_non_table_walks() -> None:
    assert not is_product_path(path="src/pkg/notes.md", prefixes=("src/pkg",))
    assert _walk(table={"tool": 1}, path=("tool", "nested")) is None
    assert _docstring_lines(source="") == frozenset()
    assert _docstring_lines(source="1\n") == frozenset()


def test_a_sibling_tree_sharing_a_declared_trees_name_is_not_product() -> None:
    declared = product_source_prefixes(
        pyproject_text='[tool.livespec_dev_tooling]\nsource_trees = ["src/pkg"]\n'
    )
    assert is_product_path(path="src/pkg/module.py", prefixes=declared)
    assert not is_product_path(path="src/pkg_extra/module.py", prefixes=declared)
    assert not is_product_path(path="src/pkg_extra/module.py", prefixes=("src/pkg",))
