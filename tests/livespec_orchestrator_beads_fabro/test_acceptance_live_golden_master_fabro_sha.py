"""Checksum guard tests for the live golden-master image staging script."""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "orchestrator-image" / "acceptance-live-golden-master.sh"
_DOCKERFILE = _REPO_ROOT / "orchestrator-image" / "Dockerfile"


def test_live_golden_master_rejects_an_unpinned_fabro_before_docker_build() -> None:
    """The staged host binary must match Dockerfile's pinned Fabro digest.

    The Dockerfile check is intentionally retained as defense in depth, but a
    mismatch needs an actionable host-side error before Docker has begun a
    costly image build.
    """
    script = _SCRIPT.read_text(encoding="utf-8")
    dockerfile = _DOCKERFILE.read_text(encoding="utf-8")

    pinned = re.search(r"^ARG FABRO_BINARY_SHA256=([0-9a-f]{64})$", dockerfile, flags=re.MULTILINE)
    assert pinned
    assert (
        'expected_sha256="$(sed -nE '
        "'s/^ARG FABRO_BINARY_SHA256=([[:xdigit:]]{64})$/\\1/p' "
        '"$HERE/Dockerfile")"'
    ) in script
    assert 'computed_sha256="$(sha256sum "$HOST_FABRO_BIN" | awk \'{print $1}\')"' in script
    assert (
        'fail "fabro binary sha256 mismatch: expected $expected_sha256, '
        'computed $computed_sha256"'
    ) in script
    assert script.index('fail "fabro binary sha256 mismatch') < script.index(
        'docker build -t "$IMAGE" "$HERE"'
    )
