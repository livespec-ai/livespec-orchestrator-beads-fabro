"""The `reconcile-runs` pass runs under the tenant's committed credential wrapper.

`install.sh` installs `tenant-wrap.sh` with the family wrapper's path
substituted, and the committed unit runs the pass through it (bd-ib-ft426g).
These tests install it against STUB wrappers that log what they saw, then run
the installed wrapper from a tenant repository whose `.livespec.jsonc` declares
each of the three shapes the dispatcher's tenant wrapper distinguishes.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

_INSTALL = (
    Path(__file__).resolve().parents[1]
    / "orchestrator-image"
    / "services"
    / "reconcile-runs"
    / "install.sh"
)

# Each stub appends one line naming itself and whether BEADS_DOLT_PASSWORD was
# set when it ran. The family stub then sets the family password, as the real
# family wrapper does, so an unset password downstream proves it was removed.
_FAMILY_STUB = """#!/bin/sh
printf 'family pw=%s\\n' "${BEADS_DOLT_PASSWORD-unset}" >> "$TW_LOG"
[ "$1" = -- ] && shift
BEADS_DOLT_PASSWORD=family exec "$@"
"""
_DECLARED_STUB = """#!/bin/sh
printf 'declared pw=%s\\n' "${BEADS_DOLT_PASSWORD-unset}" >> "$TW_LOG"
[ "$1" = -- ] && shift
BEADS_DOLT_PASSWORD=declared exec "$@"
"""
# The pass itself: records the password it received and its argv, one per line.
_PASS = """#!/bin/sh
printf 'pass pw=%s\\n' "${BEADS_DOLT_PASSWORD-unset}" >> "$TW_LOG"
for a in "$@"; do printf 'arg=%s\\n' "$a" >> "$TW_LOG"; done
"""
# A non-family wrapper shaped like a `/bin/sh -c '<script>' sh` route: one argv
# element is a whole script containing spaces, which must arrive intact.
_TENANT_SCRIPT = (
    'printf \'tenant pw=%s\\n\' "${BEADS_DOLT_PASSWORD-unset}" >> "$TW_LOG"; '
    'BEADS_DOLT_PASSWORD=tenant exec "$@"'
)

# A hop after a declared wrapper's "--": logs one line, then runs the rest.
_HOP_SCRIPT = 'printf \'hop\\n\' >> "$TW_LOG"; exec "$@"'


def _executable(*, path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(0o755)
    return path


def _installed_tenant_wrap(*, tmp_path: Path) -> Path:
    family = _executable(path=tmp_path / "family" / "with-livespec-env.sh", body=_FAMILY_STUB)
    tenant_wrap = tmp_path / "libexec" / "livespec-tenant-wrap.sh"
    (tmp_path / "primary").mkdir()
    completed = subprocess.run(
        [str(_INSTALL), "--repo", str(tmp_path / "primary"), "--user", "fabro"],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "LIVESPEC_ENV_WRAPPER": str(family),
            "LIVESPEC_TENANT_WRAP": str(tenant_wrap),
            "UNIT_DIR": str(tmp_path / "units"),
            "DRY_RUN": "1",
        },
    )
    assert completed.returncode == 0, completed.stderr
    return tenant_wrap


def _invoke(
    *, tmp_path: Path, livespec_jsonc: str | None
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    """Run the installed wrapper from a tenant repository; `None` writes no `.livespec.jsonc`.

    The tenant directory may already exist, so a test can place something
    other than a file at `.livespec.jsonc` first.
    """
    tenant_wrap = _installed_tenant_wrap(tmp_path=tmp_path)
    repo = tmp_path / "tenant"
    repo.mkdir(exist_ok=True)
    if livespec_jsonc is not None:
        _ = (repo / ".livespec.jsonc").write_text(livespec_jsonc, encoding="utf-8")
    pass_cmd = _executable(path=tmp_path / "pass.sh", body=_PASS)
    log = tmp_path / "log"
    ambient = ("BEADS_DOLT_PASSWORD", "TW_REPO", "TW_FAMILY_WRAPPER")
    env = {k: v for k, v in os.environ.items() if k not in ambient}
    completed = subprocess.run(
        [str(tenant_wrap), "--", str(pass_cmd), "reconcile-runs", "--json"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env={**env, "TW_LOG": str(log)},
    )
    return completed, repo, log


def _run_pass(*, tmp_path: Path, livespec_jsonc: str | None) -> list[str]:
    completed, _, log = _invoke(tmp_path=tmp_path, livespec_jsonc=livespec_jsonc)
    assert completed.returncode == 0, completed.stderr
    return log.read_text(encoding="utf-8").splitlines()


def _assert_refused(*, tmp_path: Path, livespec_jsonc: str | None, cause: str) -> None:
    """The pass exits 78, names the repository and the cause, and runs nothing."""
    completed, repo, log = _invoke(tmp_path=tmp_path, livespec_jsonc=livespec_jsonc)
    assert completed.returncode == 78, completed.stderr
    assert cause in completed.stderr
    assert str(repo) in completed.stderr
    assert not log.exists()


def test_a_repository_without_a_credential_wrapper_runs_under_the_family_wrapper(
    tmp_path: Path,
) -> None:
    lines = _run_pass(
        tmp_path=tmp_path,
        livespec_jsonc='{\n  // no credential_wrapper here\n  "dispatcher": {}\n}\n',
    )

    assert lines == ["family pw=unset", "pass pw=family", "arg=reconcile-runs", "arg=--json"]


def test_a_declared_family_wrapper_is_run_as_declared(tmp_path: Path) -> None:
    # Declared through a symlink, so the match is on the resolved file, and with
    # a hop after its "--" that only an un-nested, as-committed run executes once.
    link = tmp_path / "link" / "with-livespec-env.sh"
    link.parent.mkdir()
    link.symlink_to(tmp_path / "family" / "with-livespec-env.sh")
    argv = json.dumps([str(link), "--", "/bin/sh", "-c", _HOP_SCRIPT, "sh"])

    lines = _run_pass(
        tmp_path=tmp_path,
        livespec_jsonc=f'{{\n  "credential_wrapper": {argv} // family\n}}\n',
    )

    assert lines == [
        "family pw=unset",
        "hop",
        "pass pw=family",
        "arg=reconcile-runs",
        "arg=--json",
    ]


def test_a_different_file_with_the_family_basename_nests_as_a_tenant_wrapper(
    tmp_path: Path,
) -> None:
    # A tenant's own or vendored copy shares the basename but is not the family
    # wrapper, so it runs nested, with the family's BEADS_DOLT_PASSWORD removed
    # before it.
    vendored = _executable(path=tmp_path / "vendor" / "with-livespec-env.sh", body=_DECLARED_STUB)
    argv = json.dumps([str(vendored), "--"])

    lines = _run_pass(
        tmp_path=tmp_path,
        livespec_jsonc=f'{{\n  "credential_wrapper": {argv}\n}}\n',
    )

    assert lines == [
        "family pw=unset",
        "declared pw=unset",
        "pass pw=declared",
        "arg=reconcile-runs",
        "arg=--json",
    ]


def test_a_non_family_wrapper_nests_inside_the_family_wrapper_without_its_password(
    tmp_path: Path,
) -> None:
    argv = json.dumps(["/bin/sh", "-c", _TENANT_SCRIPT, "sh"])

    lines = _run_pass(
        tmp_path=tmp_path,
        livespec_jsonc=f'{{\n  "credential_wrapper": {argv}\n}}\n',
    )

    # The family wrapper runs first and sets its password; the tenant wrapper
    # then sees it UNSET and injects its own, which is what the pass receives.
    assert lines == [
        "family pw=unset",
        "tenant pw=unset",
        "pass pw=tenant",
        "arg=reconcile-runs",
        "arg=--json",
    ]


def test_a_repository_without_a_livespec_jsonc_runs_under_the_family_wrapper(
    tmp_path: Path,
) -> None:
    lines = _run_pass(tmp_path=tmp_path, livespec_jsonc=None)

    assert lines == ["family pw=unset", "pass pw=family", "arg=reconcile-runs", "arg=--json"]


# The refusals below never fall back to the family wrapper: a bare family
# wrapper mints the wrong GitHub App, which is the failure this wrapper prevents.
def test_a_malformed_credential_wrapper_refuses_the_pass(tmp_path: Path) -> None:
    _assert_refused(
        tmp_path=tmp_path,
        livespec_jsonc='{\n  "credential_wrapper": ["/bin/sh", \n}\n',
        cause="credential-wrapper-unreadable",
    )


def test_an_empty_credential_wrapper_refuses_the_pass(tmp_path: Path) -> None:
    _assert_refused(
        tmp_path=tmp_path,
        livespec_jsonc='{\n  "credential_wrapper": []\n}\n',
        cause="credential-wrapper-unreadable",
    )


def test_a_credential_wrapper_that_is_not_an_argv_refuses_the_pass(tmp_path: Path) -> None:
    _assert_refused(
        tmp_path=tmp_path,
        livespec_jsonc='{\n  "credential_wrapper": "/bin/sh -c x"\n}\n',
        cause="credential-wrapper-unreadable",
    )


def test_an_unreadable_livespec_jsonc_refuses_the_pass(tmp_path: Path) -> None:
    # A directory where the file belongs cannot be opened even by root, which a
    # mode-000 file can be, so the test holds in a root CI container too.
    (tmp_path / "tenant" / ".livespec.jsonc").mkdir(parents=True)

    _assert_refused(tmp_path=tmp_path, livespec_jsonc=None, cause="credential-wrapper-unreadable")


def test_a_credential_wrapper_that_is_not_executable_refuses_the_pass(tmp_path: Path) -> None:
    missing = tmp_path / "absent" / "with-tenant-env.sh"
    argv = json.dumps([str(missing), "--"])

    _assert_refused(
        tmp_path=tmp_path,
        livespec_jsonc=f'{{\n  "credential_wrapper": {argv}\n}}\n',
        cause="is not an executable file",
    )


def test_the_installer_removes_the_drop_in_the_committed_unit_supersedes(
    tmp_path: Path,
) -> None:
    drop_in = tmp_path / "units" / "reconcile-runs.service.d" / "60-tenant-wrap.conf"
    drop_in.parent.mkdir(parents=True)
    _ = drop_in.write_text("[Service]\nExecStart=\n", encoding="utf-8")

    _ = _installed_tenant_wrap(tmp_path=tmp_path)

    assert not drop_in.exists()
    assert (tmp_path / "units" / "reconcile-runs.service").exists()
