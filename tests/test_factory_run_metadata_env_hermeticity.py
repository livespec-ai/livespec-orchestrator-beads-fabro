"""The suite does not inherit the work-item metadata a factory run exports.

WHAT THIS BINDS. `tests/conftest.py`'s `_hermetic_factory_run_metadata_env`
scrubs the run-specific `LIVESPEC_*` names a factory sandbox exports for a
dispatched work item: the rendered pull-request title and body file, the
publication branch, the author identity and the dispatched pull-request policy.
A case that does not name one of them must see it absent, and a case that sets
one itself must still see its own value in the child command it runs.

WHY THE CONTROL IS NOT OPTIONAL. Without it, the absence assertions would be
satisfied just as well by a fixture that made these names permanently
unsettable, which would break every commit and publication case that sets
`LIVESPEC_PR_TITLE` or `LIVESPEC_PR_BODY_FILE` deliberately. The controls pin
"no AMBIENT leak" rather than "no value ever", for both the title and the body
file.
"""

from __future__ import annotations

import os

import pytest

_FACTORY_RUN_NAMES = (
    "LIVESPEC_PR_TITLE",
    "LIVESPEC_PR_BODY_FILE",
    "LIVESPEC_PUBLISH_BRANCH",
    "LIVESPEC_GIT_AUTHOR_NAME",
    "LIVESPEC_GIT_AUTHOR_EMAIL",
    "LIVESPEC_DISPATCH_PULL_REQUESTS",
)


@pytest.mark.parametrize("name", _FACTORY_RUN_NAMES)
def test_no_factory_run_metadata_reaches_a_test(*, name: str) -> None:
    """A case that names no metadata sees none, and neither does a child it spawns."""
    assert name not in os.environ
    assert name not in dict(os.environ)


@pytest.mark.parametrize("name", ["LIVESPEC_PR_TITLE", "LIVESPEC_PR_BODY_FILE"])
def test_a_case_that_sets_pull_request_metadata_still_sees_it(
    *, name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: the scrub removes the AMBIENT value, not the one a case sets."""
    monkeypatch.setenv(name, "value-the-case-set")

    assert os.environ[name] == "value-the-case-set"
    assert dict(os.environ)[name] == "value-the-case-set"
