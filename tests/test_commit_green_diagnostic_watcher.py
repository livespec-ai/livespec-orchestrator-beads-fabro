"""The commit-green diagnostic watcher has bounded, inspectable observation."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).parents[1]
_WATCHER = _ROOT / "dev-tooling" / "watch-commit-green.sh"


def test_watcher_has_the_required_observation_bounds_and_samples() -> None:
    """The same-image investigation cannot wait indefinitely or hide its evidence."""
    assert _WATCHER.is_file()
    watcher = _WATCHER.read_text(encoding="utf-8")

    assert "MAX_WALL_SECONDS=2700" in watcher
    assert "MAX_STALLED_SECONDS=900" in watcher
    assert "ps -eo pid,ppid,stat,wchan,etime,args" in watcher
    assert "lsof" in watcher
    assert "output_size" in watcher
    assert "observation ended: " in watcher
