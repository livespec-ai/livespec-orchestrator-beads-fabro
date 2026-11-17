#!/usr/bin/env bash
# Return a test-wrong lap to the dispatch base while retaining git-dir handoff
# records. The graph calls this only after Green declares the Red test wrong.
#
# Before the reset, a lap whose tree differs from the dispatch base in any file
# is pushed to refs/heads/needs-human/<dispatch-id>-lap<N> so a later reset
# or needs_human cannot lose it (bd-ib-nckst7.2). A failed push never blocks the
# reset: the stage output names the failed step and says the lap was not preserved.

set -euo pipefail

if (( $# != 1 )); then
    echo "usage: $0 <default-branch>" >&2
    exit 2
fi

readonly default_branch="$1"
case "$default_branch" in
    "" | *[!A-Za-z0-9._/-]*)
        echo "dispatch base branch is not a safe ref name: $default_branch" >&2
        exit 2
        ;;
esac

engine_run_id=''
read -r engine_run_id 2>/dev/null || true
preservation_id=''
for candidate in "$(git config --local --get livespec.factoryRunId 2>/dev/null || true)" "$engine_run_id"; do
    if [[ -z "$preservation_id" ]]; then
        case "$candidate" in
            "" | *[!0-9A-Za-z]*) : ;;
            *) preservation_id="$candidate" ;;
        esac
    fi
done

if ! git diff --quiet "origin/$default_branch" HEAD 2>/dev/null; then
    lap_sha="$(git rev-parse --short=12 HEAD)"
    if [[ -z "$preservation_id" ]]; then
        echo "LIVESPEC_TEST_WRONG_LAP_NOT_PRESERVED: step=resolve-run-id; no unique run id names a lap ref, so the lap tree ($lap_sha) was not preserved" >&2
    else
        lap_n="$(cat "$(git rev-parse --git-path livespec-implement-test-wrong-reentries)" 2>/dev/null || true)"
        case "$lap_n" in "" | *[!0-9]*) lap_n="$lap_sha" ;; esac
        lap_ref="refs/heads/needs-human/${preservation_id}-lap${lap_n}"
        helper="${LIVESPEC_SANDBOX_GH_REFRESH_ROOT:-/workspace/.livespec-gh-refresh}/bin/push_origin"
        push_status=0
        if [[ -x "$helper" ]]; then
            push_out="$("$helper" git -c core.hooksPath=/dev/null push origin "HEAD:$lap_ref" 2>&1)" || push_status=$?
        else
            push_out="$(git -c core.hooksPath=/dev/null push origin "HEAD:$lap_ref" 2>&1)" || push_status=$?
        fi
        if (( push_status == 0 )); then
            diff_size="$(git diff --shortstat "origin/$default_branch...HEAD" 2>/dev/null || true)"
            echo "LIVESPEC_TEST_WRONG_LAP_PRESERVED: $lap_ref merge-base diff: ${diff_size:-unmeasured}" >&2
        else
            push_error="$(printf '%s\n' "$push_out" | sed -e 's#[^[:space:]/@][^[:space:]/@]*:[^[:space:]/@][^[:space:]/@]*@#<credential-redacted>@#g' | head -c 2000)"
            echo "LIVESPEC_TEST_WRONG_LAP_NOT_PRESERVED: step=push-lap-ref (exit $push_status); the lap tree ($lap_sha) was not preserved. Push output: $push_error" >&2
        fi
    fi
fi

git reset --hard "origin/$default_branch"
git clean -fd
