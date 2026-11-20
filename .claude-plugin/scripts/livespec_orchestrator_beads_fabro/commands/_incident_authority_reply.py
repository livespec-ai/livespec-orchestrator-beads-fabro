"""Stable serialization helpers for the incident-authority command boundary."""

from __future__ import annotations

from typing import cast

__all__: list[str] = ["without_walk_scope"]


def without_walk_scope(*, value: object) -> object:
    """Remove the non-deterministic operation-walk scope from serialized readings."""
    if isinstance(value, dict):
        return {
            key: without_walk_scope(value=item)
            for key, item in cast("dict[str, object]", value).items()
            if key != "operation_ids"
        }
    return value
