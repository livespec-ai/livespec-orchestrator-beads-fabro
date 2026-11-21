"""Failure and compatibility controls for push-time credential replacement."""

import base64
import subprocess
from urllib.parse import urlsplit, urlunsplit

import pytest

from tests.integration import test_push_time_credentials as fixtures
from tests.integration.test_push_time_credentials import (
    BRANCH,
    EXPIRED,
    FRESH,
    PushSandbox,
    executable,
    git,
)

push_sandbox = fixtures.push_sandbox


@pytest.mark.parametrize("mint_body", ["raise SystemExit(3)\n", ""])
def test_a_failed_or_empty_mint_never_attempts_a_push(
    push_sandbox: PushSandbox,
    mint_body: str,
) -> None:
    box = push_sandbox
    (box.bundle / "bin/mint_app_token.py").write_text(mint_body)
    result = box.run(node="publish_draft")
    assert result.returncode != 0
    assert "LIVESPEC_PUSH_AUTH_MINT" in result.stderr
    assert box.writes == []


def test_an_unexpected_origin_host_never_receives_an_app_token(push_sandbox: PushSandbox) -> None:
    box = push_sandbox
    box.env["GITHUB_API_URL"] = "https://different.example.invalid"
    result = box.run(node="publish_draft")
    assert result.returncode != 0
    assert "LIVESPEC_PUSH_AUTH_HOST" in result.stderr
    assert box.mint_count() == 0
    assert box.writes == []


def test_a_separate_push_url_with_an_expired_credential_is_also_refreshed(
    push_sandbox: PushSandbox,
) -> None:
    box = push_sandbox
    old = git("remote", "get-url", "origin", cwd=box.clone, env=box.env)
    git("config", "remote.origin.pushurl", old, cwd=box.clone, env=box.env)
    before = (box.clone / ".git/config").read_bytes()
    result = box.run(node="publish_draft")
    assert result.returncode == 0, result.stderr
    # The normal -u push may append branch tracking, but the stored remote URLs remain intact.
    assert before in (box.clone / ".git/config").read_bytes()
    assert box.head(ref=f"refs/heads/{BRANCH}") == git(
        "rev-parse", "HEAD", cwd=box.clone, env=box.env
    )


def test_the_publication_push_retains_its_pre_push_hook(push_sandbox: PushSandbox) -> None:
    box = push_sandbox
    marker = box.root / "hook-ran"
    executable(
        path=box.clone / ".git/hooks/pre-push", source=f"#!/bin/sh\ntouch '{marker}'\nexit 1\n"
    )
    result = box.run(node="publish_draft")
    assert result.returncode != 0
    assert marker.is_file()
    assert box.writes == []


def test_a_publication_hook_pushes_without_being_able_to_read_a_forge_secret(
    push_sandbox: PushSandbox,
) -> None:
    """Scenario 202: the hook gets a push, not the credential that enables it."""
    box = push_sandbox
    executable(
        path=box.clone / ".git/hooks/pre-push",
        source=(
            "#!/bin/sh\n"
            "set -eu\n"
            "if env | grep -Eq '^(GH_TOKEN|GITHUB_TOKEN|GITHUB_PRIVATE_KEY|LIVESPEC_PUSH_TOKEN)='; then\n"
            "  echo hook-read-a-forge-secret >&2\n"
            "  exit 1\n"
            "fi\n"
        ),
    )

    result = box.run(node="publish_draft")

    assert result.returncode == 0, result.stderr
    assert box.head(ref=f"refs/heads/{BRANCH}") == git(
        "rev-parse", "HEAD", cwd=box.clone, env=box.env
    )


def test_no_process_between_a_publication_hook_and_its_caller_holds_a_forge_secret(
    push_sandbox: PushSandbox,
) -> None:
    """Scenario 202: every ancestor of the hook, up to the caller, is secret-free.

    A hook runs as the same user as the helper that started it, so it can read
    `/proc/<pid>/environ` and `/proc/<pid>/cmdline` of every ancestor. The
    caller here is a shell that holds the App inputs in its environment, as a
    publication node does; it is the control that the hook's scan can read a
    secret at all, and it is the boundary the walk stops at.
    """
    box = push_sandbox
    walked = box.root / "hook-walked"
    control = box.root / "hook-control"
    executable(
        path=box.clone / ".git/hooks/pre-push",
        source=(
            "#!/bin/sh\n"
            "names='^(GH_TOKEN|GITHUB_TOKEN|GITHUB_PRIVATE_KEY|GITHUB_APP_ID"
            "|GITHUB_APP_INSTALLATION_ID|LIVESPEC_PUSH_TOKEN)='\n"
            f"values='fixture-key|{FRESH}'\n"
            "leaks() { tr '\\0' '\\n' < \"/proc/$1/$2\" 2>/dev/null"
            ' | grep -Eq "$names|$values"; }\n'
            "pid=$$\n"
            "count=0\n"
            'while test "$pid" != "$LIVESPEC_TEST_BOUNDARY_PID"; do\n'
            '  test "$pid" -gt 1 || { echo hook-never-reached-its-caller >&2; exit 1; }\n'
            "  for source in environ cmdline; do\n"
            '    if leaks "$pid" "$source"; then\n'
            '      echo "hook-read-a-forge-secret: pid $pid $source" >&2\n'
            "      exit 1\n"
            "    fi\n"
            "  done\n"
            "  count=$((count + 1))\n"
            "  pid=$(awk '/^PPid:/ { print $2 }' \"/proc/$pid/status\")\n"
            "done\n"
            f'echo "$count" > "{walked}"\n'
            'leaks "$pid" environ && echo readable > '
            f'"{control}"\n'
            "exit 0\n"
        ),
    )
    box.env["LIVESPEC_TEST_BOUNDARY_PID"] = "unset"
    result = subprocess.run(
        [
            "sh",
            "-c",
            'LIVESPEC_TEST_BOUNDARY_PID=$$ "$@"; exit $?',
            "sh",
            str(box.bundle / "bin/push_origin"),
            "git",
            "push",
            "-u",
            "origin",
            f"HEAD:refs/heads/{BRANCH}",
        ],
        cwd=box.clone,
        env=box.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert box.head(ref=f"refs/heads/{BRANCH}") == git(
        "rev-parse", "HEAD", cwd=box.clone, env=box.env
    )
    # The hook, git and the helper process that ran git are all ancestors.
    assert int(walked.read_text()) >= 3
    assert control.read_text().strip() == "readable"


def test_the_helper_preserves_inherited_process_config(push_sandbox: PushSandbox) -> None:
    box = push_sandbox
    box.env.update(
        GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="livespec.control", GIT_CONFIG_VALUE_0="kept"
    )
    result = subprocess.run(
        [str(box.bundle / "bin/push_origin"), "git", "config", "livespec.control"],
        cwd=box.clone,
        env=box.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "kept"


def test_non_http_origins_use_their_existing_transport(push_sandbox: PushSandbox) -> None:
    box = push_sandbox
    git("remote", "set-url", "origin", str(box.origin), cwd=box.clone, env=box.env)
    result = subprocess.run(
        [str(box.bundle / "bin/push_origin"), "git", "push", "origin", f"HEAD:{BRANCH}"],
        cwd=box.clone,
        env=box.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert box.mint_count() == 0
    assert box.head(ref=f"refs/heads/{BRANCH}") == git(
        "rev-parse", "HEAD", cwd=box.clone, env=box.env
    )


def test_an_app_sandbox_with_a_missing_helper_refuses_publication(
    push_sandbox: PushSandbox,
) -> None:
    box = push_sandbox
    (box.bundle / "bin/push_origin").unlink()
    result = box.run(node="publish_draft")
    assert result.returncode != 0
    assert "LIVESPEC_PUSH_AUTH_ABSENT" in result.stderr
    assert box.writes == []


def test_the_server_rejects_the_expired_credential_without_the_refresh_helper(
    push_sandbox: PushSandbox,
) -> None:
    """Positive control: the same real transport refuses an unrefreshed push.

    The expired credential is handed to git through a static
    `credential.helper` and the origin URL is stripped of its userinfo,
    because a credential carried in the URL no longer reaches receive-pack at
    all on libcurl 8.5.0-2ubuntu10.16 (CVE-2026-94266): that release returns
    `CURLINFO_EFFECTIVE_URL` with the userinfo removed, git reads the
    difference against the URL it asked for as a redirect, and rebases every
    later request onto the credential-free URL. The POST then carries no
    `Authorization` header, so the server answers the UNAUTHENTICATED 401 arm,
    git falls through to a credential prompt, and with no terminal the control
    reports `could not read Username` instead of the refusal it exists to
    observe — `box.writes` would be empty too. git's credential layer passes
    the token as `CURLOPT_USERPWD`, which libcurl never puts in the effective
    URL, so this channel observes the same refusal on both libcurl releases.

    `http.extraHeader` is the other channel the URL-stripping rules in, and it
    is deliberately NOT the one used here: git does not know such a header is
    a credential, so on the receive-pack 401 it asks its credential layer for
    a username it has no source for, and the push dies with the same
    `could not read Username` this control must not accept.
    """
    box = push_sandbox
    origin_url = urlsplit(git("remote", "get-url", "origin", cwd=box.clone, env=box.env))
    credential_free = urlunsplit(
        (origin_url.scheme, f"{origin_url.hostname}:{origin_url.port}", origin_url.path, "", "")
    )
    assert "@" not in credential_free
    helper = box.root / "expired-credential-helper"
    executable(
        path=helper,
        source=(
            "#!/bin/sh\n"
            '[ "$1" = get ] || exit 0\n'
            f"printf 'username=x-access-token\\npassword=%s\\n' '{EXPIRED}'\n"
        ),
    )
    git("remote", "set-url", "origin", credential_free, cwd=box.clone, env=box.env)
    git("config", "credential.helper", str(helper), cwd=box.clone, env=box.env)
    result = subprocess.run(
        ["git", "push", "origin", f"HEAD:{BRANCH}"],
        cwd=box.clone,
        env=box.env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "HTTP 401" in result.stderr
    expected = "Basic " + base64.b64encode(f"x-access-token:{EXPIRED}".encode()).decode()
    assert box.writes == [expected]
    assert box.mint_count() == 0


def test_a_planted_pre_push_hook_cannot_merge_the_run_with_the_publication_credential(
    push_sandbox: PushSandbox,
) -> None:
    """Scenario 202: a hook an agent stage planted to merge the run's pull request fails.

    `gh` here is a stand-in for the forge: a `pr merge` call takes effect, and leaves
    its marker, only when the caller holds a forge credential in its environment
    (any other `gh` call, such as the `pr list --state merged` publish_draft itself makes, is a harmless no-op). The
    planted hook tries `gh pr merge` while publish_draft pushes through it. The
    control calls the same `gh` with a credential and DOES merge, which is what
    makes the planted hook's failure evidence about the credential and not about a
    `gh` that could never merge.
    """
    box = push_sandbox
    merged = box.root / "pull-request-merged"
    hook_rc = box.root / "hook-merge-rc"
    stub_dir = box.root / "stub-bin"
    stub_dir.mkdir()
    executable(
        path=stub_dir / "gh",
        source=(
            "#!/bin/sh\n"
            'case "$*" in "pr merge"*) ;; *) exit 0 ;; esac\n'
            "if env | grep -Eq '^(GH_TOKEN|GITHUB_TOKEN|GITHUB_PRIVATE_KEY|LIVESPEC_PUSH_TOKEN)='; then\n"
            f"  echo merged > '{merged}'\n"
            "  exit 0\n"
            "fi\n"
            "echo 'gh: no credential' >&2\n"
            "exit 4\n"
        ),
    )
    box.env["PATH"] = f"{stub_dir}:{box.env['PATH']}"
    executable(
        path=box.clone / ".git/hooks/pre-push",
        source=(
            "#!/bin/sh\n"
            "has=no; env | grep -Eq '^(GH_TOKEN|GITHUB_TOKEN|GITHUB_PRIVATE_KEY|LIVESPEC_PUSH_TOKEN)=' && has=yes\n"
            "gh pr merge 1 --merge 2>/dev/null\n"
            f"echo \"rc=$? credential=$has pid=$$ ppid=$PPID\" >> '{hook_rc}'\n"
            "exit 0\n"
        ),
    )

    result = box.run(node="publish_draft")

    assert result.returncode == 0, result.stderr
    assert "rc=0" not in hook_rc.read_text(), hook_rc.read_text()
    assert not merged.exists(), "the planted hook merged the pull request"

    control = subprocess.run(
        [str(stub_dir / "gh"), "pr", "merge", "1", "--merge"],
        env={**box.env, "GH_TOKEN": FRESH},
        capture_output=True,
        text=True,
        check=False,
    )
    assert control.returncode == 0, control.stderr
    assert merged.exists(), "the control gh could not merge even with a credential"
