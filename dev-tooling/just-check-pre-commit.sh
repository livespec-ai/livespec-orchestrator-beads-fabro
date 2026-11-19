#!/usr/bin/env bash
set -euo pipefail

# The gate Job sets LIVESPEC_GATE_CONTEXT after restoring the staged index.
# Its aggregate must run locally there, never submit another Job.
if [[ -z "${LIVESPEC_GATE_CONTEXT:-}" ]]; then
    set +e
    uv run python -m livespec_dev_tooling.pre_commit_delegate run
    delegate_status=$?
    set -e
    case "$delegate_status" in
        0)
            exit 0
            ;;
        75)
            ;;
        *)
            exit "$delegate_status"
            ;;
    esac
fi

# `check-master-ci-green` is an ENVIRONMENTAL gate, and inside a Fabro sandbox
# it refuses commits for a condition the staged tree cannot cause or cure:
# master CI re-queues on every merge, so with many sessions merging per hour the
# aggregate is frequently red, queued or running, and the sandbox carries a
# GitHub token so the check ENFORCES rather than warning. The refusal then lands
# on the sandbox's own Red and Green commits and on the engine's checkpoint
# commits alike — measured 2026-10-12, 5 of 27 hp checkpoint-commit failures
# since 2026-10-09 named this target, two of them alone (work-item
# bd-ib-hot3g6). Whether a run may START against a red master is already
# governed by the dispatch-time master-CI preflight, so skipping it here removes
# a duplicate signal rather than an only one.
#
# The marker is the RESOLVED sandbox-exemption key, read literally for the same
# reason the commit-refuse hook body reads it literally: the integration
# contract closes `dispatcher.sandbox_exempt_marker` to the single value
# `livespec.sandboxExempt`, so a declared alternate would be set by the
# projection and honored by nothing. A checkout WITHOUT the marker — every
# human worktree — keeps the gate exactly as it was.
sandbox_skips=()
if [[ "$(git config --get --bool livespec.sandboxExempt || printf 'false')" == true ]]; then
    echo ":: sandbox-exemption marker livespec.sandboxExempt is true: skipping check-master-ci-green"
    echo ":: the dispatch-time master-CI preflight governs whether a run may start against a red master"
    sandbox_skips+=(check-master-ci-green)
fi
# Inside the delegated gate Job this script IS the Job's gate, and the shared
# client exports into `SKIP_TARGETS` the members that read authority held
# outside the tree (the work-items ledger, the forge's settings), running them
# on the committing host instead. Dropping the variable here ran
# `check-no-workflow-edits` in a pod holding no credential, where it failed
# closed on every tree carrying an approved workflow edit (gate Jobs of
# bd-ib-oxx6eo, 2026-11-08). The pre-push script reads it the same way. Unset,
# nothing extra is skipped.
read -ra delegated_skip_targets <<< "${SKIP_TARGETS:-}"

staged=$(git diff --cached --name-only --diff-filter=AM)
py_staged=$(echo "$staged" | grep -E '\.py$' || true)
# The ordinary Red/Green shape detection below intentionally considers only
# added and modified paths. An authoring turn's affected-tests gate, however,
# must also cover a deleted product module: the selector includes deletions in
# its changed set and cannot run if the hook sends that commit down doc-only.
staged_with_deletions=$(git diff --cached --name-only --diff-filter=ACDMR)
authoring_py_staged=$(echo "$staged_with_deletions" | grep -E '\.py$' || true)
# `check-fleet-launch` is expensive because it runs the hermetic launcher
# harness. The harness and every script it sources live below fleet-launch/.
# The remaining paths are the target's declared execution chain: its recipe
# and inventory, the aggregate declaration reader and runner, and its driver.
is_fleet_launch_input() {
    case "$1" in
        fleet-launch/* | check-targets.txt | justfile | dev-tooling/aggregate-targets.sh | dev-tooling/just-check.sh | dev-tooling/just-check-fleet-launch.sh)
            return 0
            ;;
        *)
            return 1
            ;;
    esac
}
fleet_launch_input_staged=''
while IFS= read -r staged_path; do
    if is_fleet_launch_input "$staged_path"; then
        fleet_launch_input_staged+="${staged_path}"$'\n'
    fi
done <<<"$staged_with_deletions"
# In Red mode the staged test is a deliberately failing one, so the harness must not refuse the commit for the
# scenario the staged diff ADDS (bd-ib-ganm6d, measured on bd-ib-zdqshg run 01M7RYJ0VTEB: commit_red failed three times
# at 755 s on its own new section 31a). Every other scenario still gates: the harness records each failing scenario's
# label in HARNESS_FAILED_SCENARIOS_FILE, and the commit passes only when the harness failed AND every recorded label
# is a `scenario "<label>"` line the staged diff of fleet-launch/test/run-tests.sh adds. A failure that names no
# scenario, or names one the diff did not add, is refused.
red_fleet_launch_gate() {
    local failed_file log status allowed label unexpected
    failed_file=$(mktemp)
    log=$(mktemp)
    set +e
    HARNESS_FAILED_SCENARIOS_FILE="$failed_file" just check-fleet-launch >"$log" 2>&1
    status=$?
    set -e
    cat "$log"
    if [[ "$status" -eq 0 ]]; then
        rm -f "$failed_file" "$log"
        return 0
    fi
    allowed=$(git diff --cached -U0 -- fleet-launch/test/run-tests.sh | sed -n 's/^+scenario "\(.*\)"$/\1/p')
    unexpected=""
    if [[ ! -s "$failed_file" ]]; then
        unexpected="the harness failed without naming a failing scenario"
    else
        while IFS= read -r label; do
            if ! grep -Fxq -- "$label" <<<"$allowed"; then
                unexpected+="${unexpected:+; }scenario not added by this commit: $label"
            fi
        done < <(sort -u "$failed_file")
    fi
    rm -f "$failed_file" "$log"
    if [[ -n "$unexpected" ]]; then
        echo ":: fleet-launch gate refused the Red commit: $unexpected" >&2
        return "$status"
    fi
    echo ":: Red mode: every failing fleet-launch scenario is one this commit adds, so the staged Red test is expected to fail"
    return 0
}
fleet_launch_skips=()
if [[ -z "$fleet_launch_input_staged" ]]; then
    fleet_launch_skips+=(check-fleet-launch)
fi
test_staged=$(echo "$staged" | grep -E '^tests/.*\.py$' || true)
impl_staged=$(echo "$staged" | grep -E '^(\.claude-plugin/scripts/|dev-tooling/checks/).*\.py$' || true)
green_amend_staged=$(echo "$py_staged" | grep -Ev '^tests/' || true)
# A deleted workflow graph is a change to it as well: the graph-reading tests must run.
workflow_fabro_staged=$(echo "$staged_with_deletions" | grep -E '^\.claude-plugin/\.fabro/workflows/[^/]+/workflow\.fabro$' || true)
pre_commit_hook_staged=$(echo "$staged" | grep -E '^dev-tooling/just-check-pre-commit\.sh$' || true)
green_amend_staged=$(printf '%s\n%s\n%s\n' "$green_amend_staged" "$workflow_fabro_staged" "$pre_commit_hook_staged" | sed '/^$/d')
test_count=0
impl_count=0
[[ -n "$test_staged" ]] && test_count=$(echo "$test_staged" | wc -l)
[[ -n "$impl_staged" ]] && impl_count=$(echo "$impl_staged" | wc -l)
# A repair turn may finish a Red test that this item already introduced, but it
# may not turn an unrelated janitor failure into a new Red of another item's
# test.  The item's already-recorded branch diff is the only evidence of that
# ownership: accepting the staged test itself would let the repair turn claim
# any test merely by staging it.  `check-changed` below needs the same
# `origin/master` comparison, so a missing or unreadable base fails closed here
# as an empty owned-test set rather than granting the Red fast path.
if [[ "${LIVESPEC_AUTHORING_TURN:-}" =~ ^(fix|review_fix)$ ]] && [[ -n "$test_staged" ]]; then
    owned_tests=$(git diff --name-only origin/master...HEAD -- tests/ 2>/dev/null || true)
    # A newly-added test is part of this item's own change, rather than a
    # pre-existing test a janitor failure might tempt the repair to weaken.
    # In a throwaway or otherwise unanchored repository, fail closed instead:
    # there is no default-branch tree from which that distinction is knowable.
    if git rev-parse --verify --quiet origin/master >/dev/null; then
        existing_default_tests=$(while IFS= read -r test_path; do
            test -n "$test_path" || continue
            if git cat-file -e "origin/master:$test_path" 2>/dev/null; then
                printf '%s\n' "$test_path"
            fi
        done <<<"$test_staged")
    else
        existing_default_tests=$test_staged
    fi
    foreign_tests=$(comm -23 \
        <(printf '%s\n' "$existing_default_tests" | sed '/^$/d' | sort -u) \
        <(printf '%s\n' "$owned_tests" | sed '/^$/d' | sort -u))
    if [[ -n "$foreign_tests" ]]; then
        echo "LIVESPEC_FOREIGN_REPAIR_TEST: $LIVESPEC_AUTHORING_TURN may not edit a test this item did not already touch: $foreign_tests" >&2
        echo ":: preserve the named test; identify its owning work item from origin/master and end at needs-human" >&2
        exit 1
    fi
fi
head_msg=$(git log -1 --format=%B 2>/dev/null || true)
red_test_staged=$(git diff-tree --no-commit-id --name-only --diff-filter=AM -r HEAD -- tests/ \
    | grep -E '^tests/.*\.py$' || true)
# A merge in progress is neither a Red nor a Green-amend: whatever HEAD's
# trailers say, its staged tree is the merged tree. red_green_replay routes a
# MERGE_HEAD commit to its suite-green leg, which reuses only the full
# aggregate's same-tree evidence, and the Green-amend and Red-mode branches
# below write none. So a merge staging `.py` skips them and reaches the
# evidence-writing aggregate; a merge staging no `.py` stays on the doc-only path.
merge_in_progress=false
if git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
    merge_in_progress=true
fi
# A commit made inside an implement, fix or review_fix turn runs the affected-tests
# gate (`just check-changed`) in place of the full check aggregate; the janitor stage
# runs the aggregate once per run before publication. The detached commit runner
# carries the turn's stage in LIVESPEC_AUTHORING_TURN. It cannot carry
# LIVESPEC_AGENT_STAGE, which activates the publication guard that a test suite run by
# this hook must not meet, and it names a different gate rather than skipping a check.
#
# Three shapes stay on the existing paths below. A Red commit (one staged test, no
# staged impl) is deliberately a failing test, so it keeps the Red-mode fast path. A
# merge in progress is the merged tree, graded by the full aggregate. A commit that
# stages neither a `.py` file nor a workflow graph has no tests to scope to and keeps
# the doc-only path.
#
# Exit 75 from the gate means it cannot determine the affected tests (a shared
# configuration file, a module no test reaches, a file the scan cannot parse): the
# commit then falls through to the full check aggregate, which the paths below run for
# any commit made outside these turns. Any other non-zero status is the gate's refusal
# and its output names the failing test or each uncovered line of a changed module.
if [[ "$merge_in_progress" == false ]] \
    && [[ "${LIVESPEC_AUTHORING_TURN:-}" =~ ^(implement|fix|review_fix)$ ]] \
    && [[ -n "$authoring_py_staged$workflow_fabro_staged" ]] \
    && ! { [[ "$test_count" -eq 1 ]] && [[ "$impl_count" -eq 0 ]]; }; then
    echo ":: $LIVESPEC_AUTHORING_TURN-turn commit: running just check-changed in place of the full check aggregate"
    if [[ -z "$authoring_py_staged" ]]; then
        echo ":: a workflow graph with no .py staged: running just check-pre-commit-doc-only first"
        if ! just check-pre-commit-doc-only; then
            echo ":: doc-only gates refused the commit" >&2
            exit 1
        fi
    elif ! just check-staged-precheck; then
        echo ":: staged pre-check phase refused the commit" >&2
        exit 1
    fi
    if [[ -n "$fleet_launch_input_staged" ]] && ! just check-fleet-launch; then
        echo ":: fleet-launch gate refused the commit" >&2
        exit 1
    fi
    set +e
    just check-changed
    changed_status=$?
    set -e
    if [[ "$changed_status" -eq 0 ]]; then
        exit 0
    fi
    if [[ "$changed_status" -ne 75 ]]; then
        echo ":: affected-tests gate refused the commit" >&2
        exit "$changed_status"
    fi
    echo ":: check-changed could not determine the affected tests; running the full check aggregate"
fi
if [[ "$merge_in_progress" == false ]] \
    && [[ -n "$green_amend_staged" ]] \
    && [[ -n "$red_test_staged" ]] \
    && grep -q 'TDD-Red-Test-File-Checksum:' <<<"$head_msg" \
    && ! grep -q 'TDD-Green-Verified-At:' <<<"$head_msg"; then
    echo ":: Green-amend shape detected (implementation staged; HEAD carries Red-only trailers)"
    if ! just check-staged-precheck; then
        echo ":: staged pre-check phase refused the commit" >&2
        exit 1
    fi
    if [[ -n "$red_test_staged" ]] && ! just check-staged-tests $red_test_staged; then
        echo ":: staged tests phase refused the commit" >&2
        exit 1
    fi
    echo ":: staged pre-check and staged tests passed; running the gate once"
    echo ":: skipping no-arg check-red-green-replay and same-repo live TUI picker gate"
    if ! just check-skipping check-red-green-replay check-codex-skill-picker "${sandbox_skips[@]}" "${delegated_skip_targets[@]}" "${fleet_launch_skips[@]}"; then
        echo ":: gate phase refused the commit" >&2
        exit 1
    fi
    exit 0
fi
if [[ -z "$py_staged" ]]; then
    echo ":: doc-only mode detected (zero .py files staged): running just check-pre-commit-doc-only"
    echo ":: pre-push + CI keep the full aggregate as the load-bearing safety net"
    if ! just check-pre-commit-doc-only; then
        exit 1
    fi
    if [[ -n "$fleet_launch_input_staged" ]]; then
        just check-fleet-launch
    fi
    exit $?
fi
if [[ "$merge_in_progress" == false ]] && [[ "$test_count" -eq 1 ]] && [[ "$impl_count" -eq 0 ]]; then
    echo ":: Red-mode shape detected: $test_staged"
    echo ":: skipping coverage gates and same-repo live TUI picker gate in pre-commit"
    # check-check-coverage-incremental belongs in this skip list even though it
    # is vacuous on a FRESH branch: on a branch that already carries impl
    # commits, its incremental scope includes those impl files, so it RUNS the
    # branch's tests — the staged Red test among them. That test fails BY
    # DESIGN, which is the whole point of a Red commit, so leaving the gate
    # armed here refuses the ritual's own first step (work-item bd-ib-c4sfpr).
    # No coverage is lost: the Green amend, pre-push, and CI each run the full
    # aggregate on the final commit, which is the load-bearing net.
    red_fleet_skips=("${fleet_launch_skips[@]}")
    if [[ -n "$fleet_launch_input_staged" ]]; then
        red_fleet_skips=(check-fleet-launch)
    fi
    just check-skipping \
        check-coverage \
        check-per-file-coverage \
        check-check-coverage-incremental \
        check-codex-skill-picker \
        "${sandbox_skips[@]}" \
        "${delegated_skip_targets[@]}" "${red_fleet_skips[@]}"
    if [[ -n "$fleet_launch_input_staged" ]]; then
        red_fleet_launch_gate
    fi
    exit $?
fi
if [[ "$merge_in_progress" == false ]] \
    && [[ "$impl_count" -ge 1 ]] \
    && grep -q 'TDD-Red-Test-File-Checksum:' <<<"$head_msg" \
    && ! grep -q 'TDD-Green-Verified-At:' <<<"$head_msg"; then
    echo ":: Green-amend shape detected (impl staged; HEAD carries Red-only trailers)"
    echo ":: skipping no-arg check-red-green-replay and same-repo live TUI picker gate"
    just check-skipping check-red-green-replay check-codex-skill-picker "${sandbox_skips[@]}" "${delegated_skip_targets[@]}" "${fleet_launch_skips[@]}"
    exit $?
fi
echo ":: pre-push: skipping same-repo live TUI picker gate; run just check-codex-skill-picker explicitly for live Codex picker acceptance"
aggregate_log=$(mktemp "$(git rev-parse --git-path livespec-pre-commit-aggregate.XXXXXX)")
staged_tree=$(git write-tree)
set +e
just check-skipping check-codex-skill-picker "${sandbox_skips[@]}" "${delegated_skip_targets[@]}" "${fleet_launch_skips[@]}" 2>&1 | tee "$aggregate_log"
aggregate_status=${PIPESTATUS[0]}
set -e
# The local aggregate reads the working tree, so it can certify the staged tree
# only when both trees are identical and no untracked file could have affected
# its result. Capture the staged tree before the aggregate and confirm it again
# afterwards so an index mutation cannot receive evidence for an untested tree.
if [[ "$aggregate_status" -eq 0 ]] && git diff --quiet \
    && [[ -z "$(git ls-files --others --exclude-standard)" ]] \
    && [[ "$(git write-tree)" == "$staged_tree" ]]; then
    run_id="pre-commit-aggregate:$(date -u +%Y%m%dT%H%M%SZ):${staged_tree}"
    output_checksum="sha256:$(sha256sum "$aggregate_log" | awk '{print $1}')"
    uv run python -m livespec_dev_tooling.green_token write-pre-commit "$run_id" "$output_checksum"
fi
rm -f "$aggregate_log"
exit "$aggregate_status"
