#!/usr/bin/env bash
#
# Amend the Red commit outside the implement agent turn.  Engine checkpoints
# carry Green's staged implementation, so they are folded before the amend.
#
# Usage: livespec-commit-green.sh [MECHANICAL_REENTRIES [MECHANICAL_TARGETS]]
# The Dispatcher renders both from dispatcher.implement.mechanical_reentries
# and dispatcher.implement.mechanical_targets (comma-separated); absent, no
# refusal is mechanical.

set -euo pipefail

readonly CHECKPOINT_LIMIT=500
readonly CHECKPOINT_SUBJECT='^fabro\([^)]*\): '
readonly HANDOFF_NAME="livespec-implement-handoff.md"
readonly OUTPUT_NAME="livespec-commit-green-output"
readonly MECHANICAL_SPENT_NAME="livespec-green-mechanical-reentries"
readonly MECHANICAL_BUDGET_NAME="livespec-green-mechanical-budget"
readonly MECHANICAL_GRANT_NAME="livespec-green-mechanical-reentry"
# bd-ib-v5qotp: the full aggregate reports a per-file coverage refusal as
# check-per-file-coverage and the affected-tests gate as
# check-check-coverage-incremental, so the two names are one class here.
readonly COVERAGE_TARGETS=" check-per-file-coverage check-check-coverage-incremental "

checkpoint_commit() {
    local ref="$1"
    local subject=""
    local message=""
    subject="$(git log -1 --format=%s "$ref" 2>/dev/null)" || return 1
    message="$(git log -1 --format=%B "$ref" 2>/dev/null)" || return 1
    [[ "$subject" =~ $CHECKPOINT_SUBJECT ]] && grep -q '^Fabro-Run: ' <<<"$message"
}

checkpoint_run_id() {
    local ref="$1"
    local message=""
    message="$(git log -1 --format=%B "$ref" 2>/dev/null)" || return 0
    awk '!found && sub(/^Fabro-Run: /, "") { print; found = 1 }' <<<"$message"
}

checkpoint_for_run() {
    local ref="$1"
    local run_id="$2"
    checkpoint_commit "$ref" && [[ "$(checkpoint_run_id "$ref")" == "$run_id" ]]
}

red_commit_for_current_run() {
    local ref="$1"
    local run_id=""
    local subject=""
    local message=""
    subject="$(git log -1 --format=%s "$ref" 2>/dev/null)" || return 1
    message="$(git log -1 --format=%B "$ref" 2>/dev/null)" || return 1
    run_id="$(git config --local --get livespec.factoryRunId 2>/dev/null || true)"
    [[ -n "$run_id" ]] \
        && [[ "$subject" == "feat: red" ]] \
        && grep -qxF "Factory-Run-Id: $run_id" <<<"$message"
}

open_seed_red() {
    local ref="$1"
    local message=""
    message="$(git log -1 --format=%B "$ref" 2>/dev/null)" || return 1
    grep -q '^TDD-Red-Test-File-Checksum: ' <<<"$message" \
        && ! grep -q '^TDD-Green-Verified-At: ' <<<"$message"
}

seeded_open_red_declared() {
    local handoff=""
    handoff="$(git rev-parse --git-path "$HANDOFF_NAME")"
    grep -q '^##[[:space:]]\+seeded-open-red\([[:space:]]\|$\)' "$handoff"
}

current_engine_run_id() {
    local branch=""
    if [[ -n "${FABRO_RUN_ID:-}" ]]; then
        printf '%s\n' "$FABRO_RUN_ID"
        return 0
    fi
    branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
    if [[ "$branch" == fabro/run/?* ]]; then
        printf '%s\n' "${branch#fabro/run/}"
    fi
}

fold_checkpoints() {
    local depth=0
    local ref="HEAD"
    local checkpoint_run=""
    checkpoint_run="$(current_engine_run_id)"
    if [[ -z "$checkpoint_run" ]]; then
        printf '%s\n' "current engine run id is unknown, so no checkpoint commit can be attributed to this run"
        return 2
    fi
    while (( depth < CHECKPOINT_LIMIT )) && checkpoint_for_run "$ref" "$checkpoint_run"; do
        ((depth += 1))
        ref="HEAD~${depth}"
    done
    if red_commit_for_current_run "$ref"; then
        if (( depth > 0 )); then
            git reset --soft "$ref"
        fi
        return
    fi
    while (( depth < CHECKPOINT_LIMIT )) && checkpoint_commit "$ref"; do
        ((depth += 1))
        ref="HEAD~${depth}"
    done
    if ! seeded_open_red_declared || ! open_seed_red "$ref"; then
        printf '%s\n' "current run's own Red commit was not found beneath checkpoint commits"
        return 2
    fi
    if (( depth > 0 )); then
        git reset --soft "HEAD~${depth}"
    fi
}

append_failure_details() {
    local output="$1"
    printf 'Failed targets:\n'
    awk '
        /^Failed targets \([0-9]+\):[[:space:]]*$/ { printing = 1; next }
        printing && /^[[:space:]]+-[[:space:]]+/ { print; next }
        printing { exit }
    ' "$output"
    append_failing_section "$output"
    printf 'Hook output (last 80 lines):\n```text\n'
    tail -n 80 "$output"
    printf '\n```\n'
}

# Contracts.md "Every commit-refusal re-entry brief names the failing files from
# the full recorded output": the commit runner materialized beside this program
# owns the one builder every refusal brief shares, so this section reads the
# FULL output the same way the fix and review_fix briefs do.
append_failing_section() {
    local output="$1"
    local runner=""
    runner="$(dirname "${BASH_SOURCE[0]}")/livespec-commit-runner.py"
    if [[ -f "$runner" ]]; then
        python3 "$runner" refusal-section "$output" \
            || printf 'failing files: unavailable (runner exited %s)\n' "$?"
    else
        printf 'failing files: unavailable, because the commit runner is not materialized beside this program\n'
    fi
}

failed_target_names() {
    awk '
        /^Failed targets \([0-9]+\):[[:space:]]*$/ { printing = 1; next }
        printing && /^[[:space:]]+-[[:space:]]+/ { sub(/^[[:space:]]+-[[:space:]]+/, ""); sub(/[[:space:]]+$/, ""); print; next }
        printing { exit }
    ' "$1" | tr '\n' ' ' | sed 's/ $//'
}

declared_mechanical() {
    local target="$1"
    local allowed="$2"
    local alias=""
    [[ "$allowed" == *" $target "* ]] && return 0
    [[ "$COVERAGE_TARGETS" == *" $target "* ]] || return 1
    for alias in $COVERAGE_TARGETS; do
        [[ "$allowed" == *" $alias "* ]] && return 0
    done
    return 1
}

non_negative() {
    case "$1" in
        ''|*[!0-9]*) printf '0\n' ;;
        *) printf '%s\n' "$1" ;;
    esac
}

# Contracts.md "A purely mechanical commit refusal has its own re-entry
# budget": a refusal whose every failed target is a declared mechanical target
# spends a mechanical re-entry while one remains, and green_admission then
# re-enters green without spending its ordinary re-entry. Anything else, a
# refusal naming no failed target included, spends the ordinary re-entry.
append_reentry_class() {
    local handoff="$1"
    local output="$2"
    local budget=""
    local allowed=" ${3//,/ } "
    local spent_path=""
    local grant_path=""
    local spent=0
    local names=""
    local target=""
    local mechanical=0
    local reason=""
    budget="$(non_negative "${4:-0}")"
    spent_path="$(git rev-parse --git-path "$MECHANICAL_SPENT_NAME")"
    grant_path="$(git rev-parse --git-path "$MECHANICAL_GRANT_NAME")"
    rm -f "$grant_path"
    printf '%s\n' "$budget" > "$(git rev-parse --git-path "$MECHANICAL_BUDGET_NAME")"
    spent="$(non_negative "$(cat "$spent_path" 2>/dev/null || true)")"
    names="$(failed_target_names "$output")"
    if [[ -n "$names" ]]; then
        mechanical=1
        for target in $names; do
            declared_mechanical "$target" "$allowed" || mechanical=0
        done
    fi
    if (( mechanical == 1 && spent < budget )); then
        spent=$((spent + 1))
        printf '%s\n' "$spent" > "$spent_path"
        printf 'mechanical\n' > "$grant_path"
        {
            printf 'Refusal: mechanical. Every failed target is a declared mechanical target, so the run re-enters green on a mechanical re-entry and leaves its ordinary re-entry unspent.\n'
            printf 'Mechanical failed targets: %s\n' "$names"
            printf 'Mechanical re-entries remaining: %s of %s\n' "$((budget - spent))" "$budget"
        } >> "$handoff"
        return 0
    fi
    if [[ -z "$names" ]]; then
        reason="the hook output names no failed target"
    elif (( mechanical == 1 )); then
        reason="every failed target is a declared mechanical target, but the mechanical re-entries are spent"
    else
        reason="a failed target is not a declared mechanical target"
    fi
    {
        printf 'Refusal: ordinary. %s, so this refusal spends green'"'"'s ordinary re-entry.\n' "${reason^}"
        printf 'Mechanical re-entries remaining: %s of %s\n' "$((budget - spent))" "$budget"
    } >> "$handoff"
}

append_verdict() {
    local handoff="$1"
    local status="$2"
    local output="$3"
    local cause="${4:-}"
    {
        printf '\n## commit_green\n\n'
        printf 'Exit status: %s\n' "$status"
        if [[ -n "$cause" ]]; then
            printf 'Cause: %s\n' "$cause"
        elif (( status != 0 )); then
            append_failure_details "$output"
        fi
    } >> "$handoff"
}

main() {
    local reentries="${1:-0}"
    local mechanical_targets="${2:-}"
    local handoff=""
    local output=""
    local status=0
    local cause=""
    handoff="$(git rev-parse --git-path "$HANDOFF_NAME")"
    output="$(git rev-parse --git-path "$OUTPUT_NAME")"
    set +e
    cause="$(fold_checkpoints)"
    status=$?
    set -e
    if (( status != 0 )); then
        : > "$output"
        printf '%s\n' "commit_green: $cause" >&2
        append_verdict "$handoff" "$status" "$output" "$cause"
        append_reentry_class "$handoff" "$output" "$mechanical_targets" "$reentries"
        return "$status"
    fi
    set +e
    git commit --amend --no-edit >"$output" 2>&1
    status=$?
    set -e
    cat "$output"
    append_verdict "$handoff" "$status" "$output"
    if (( status != 0 )); then
        append_reentry_class "$handoff" "$output" "$mechanical_targets" "$reentries"
    fi
    return "$status"
}

main "$@"
