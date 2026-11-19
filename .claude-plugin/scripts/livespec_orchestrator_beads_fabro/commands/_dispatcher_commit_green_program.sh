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

preserve_rebuilt_seed_red_subject() {
    [[ -n "${LIVESPEC_RESUME_PUBLISHED_HEAD:-}" ]] \
        && seeded_open_red_declared \
        && open_seed_red HEAD
}

seeded_red_passes_declared() {
    local handoff=""
    handoff="$(git rev-parse --git-path "$HANDOFF_NAME")"
    grep -q '^##[[:space:]]\+seeded-red-passes\([[:space:]]\|$\)' "$handoff"
}

commit_red_nothing_to_commit_declared() {
    local handoff=""
    handoff="$(git rev-parse --git-path "$HANDOFF_NAME")"
    grep -q '^Cause: LIVESPEC_COMMIT_RED_NOTHING_TO_COMMIT:' "$handoff"
}

seed_red_commit() {
    # The resumed seed's own open Red: the first commit under the seed head that is
    # not an engine checkpoint. It must carry TDD-Red trailers and no Green trailer,
    # so a seeded run still proves a failing Red existed.
    local seed_head="${LIVESPEC_RESUME_PUBLISHED_HEAD:-}"
    local index=0
    local ref=""
    [[ -n "$seed_head" ]] || return 1
    git cat-file -e "${seed_head}^{commit}" 2>/dev/null || return 1
    while (( index < CHECKPOINT_LIMIT )); do
        ref="${seed_head}~${index}"
        git rev-parse --verify --quiet "${ref}^{commit}" >/dev/null || return 1
        if ! checkpoint_commit "$ref"; then
            open_seed_red "$ref" || return 1
            git rev-parse "$ref"
            return 0
        fi
        ((index += 1))
    done
    return 1
}

rebuild_seeded_red() {
    # Re-create the seed's Red as a commit on the run's base: the base tree with the
    # paths the seed's Red changed taken from the carried tree, under the Red's own
    # message (its TDD-Red trailers). What the carried tree adds beyond those paths
    # stays staged for Green's amend.
    local base="$1"
    local seed_red="$2"
    local index_file=""
    local path=""
    local entry=""
    local mode=""
    local rest=""
    local blob=""
    local tree=""
    local rebuilt=""
    index_file="$(git rev-parse --git-path livespec-seed-red-index)"
    rm -f "$index_file"
    GIT_INDEX_FILE="$index_file" git read-tree "$base" || return 2
    while IFS= read -r path; do
        entry="$(git ls-tree HEAD -- "$path")"
        if [[ -z "$entry" ]]; then
            GIT_INDEX_FILE="$index_file" git update-index --force-remove -- "$path" || return 2
        else
            mode="${entry%% *}"
            rest="${entry#* }"
            blob="${rest#* }"
            blob="${blob%%$'\t'*}"
            GIT_INDEX_FILE="$index_file" git update-index --add --cacheinfo "$mode,$blob,$path" || return 2
        fi
    done < <(git diff-tree --no-commit-id --name-only -r --root "$seed_red")
    tree="$(GIT_INDEX_FILE="$index_file" git write-tree)" || return 2
    rm -f "$index_file"
    rebuilt="$(git log -1 --format=%B "$seed_red" | git commit-tree "$tree" -p "$base" -F -)" || return 2
    git reset --soft "$rebuilt" || return 2
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

red_search_evidence() {
    # The refusal's evidence: the run ids the search matched against and the
    # newest commits it walked, each with the provenance lines it read (bd-ib-eyhjwr).
    local depth="$1"
    local limit=$((depth + 3))
    local factory_run=""
    local index=0
    local ref=""
    local sha=""
    local subject=""
    local message=""
    local fabro_run=""
    local factory_trailer=""
    local inspected=""
    factory_run="$(git config --local --get livespec.factoryRunId 2>/dev/null || true)"
    while (( index < limit && index < 12 )); do
        ref="HEAD~${index}"
        sha="$(git rev-parse --short "$ref" 2>/dev/null)" || break
        subject="$(git log -1 --format=%s "$ref" 2>/dev/null || true)"
        message="$(git log -1 --format=%B "$ref" 2>/dev/null || true)"
        fabro_run="$(awk '!found && sub(/^Fabro-Run: /, "") { print; found = 1 }' <<<"$message")"
        factory_trailer="$(awk '!found && sub(/^Factory-Run-Id: /, "") { print; found = 1 }' <<<"$message")"
        inspected+="${inspected:+ | }${sha} ${subject} [Fabro-Run: ${fabro_run:-none}; Factory-Run-Id: ${factory_trailer:-none}]"
        ((index += 1))
    done
    printf 'factory run id %s; engine run id %s; inspected: %s' \
        "${factory_run:-unset}" "$(current_engine_run_id)" "${inspected:-none}"
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
    if seeded_red_passes_declared || commit_red_nothing_to_commit_declared; then
        if (( depth > 0 )); then
            git reset --soft "HEAD~${depth}"
        fi
        printf '%s\n' "LIVESPEC_COMMIT_GREEN_SEEDED_RED_PASSES: the Red test already passed in the carried seed, so no Red or Green commit was needed"
        return
    fi
    if seeded_open_red_declared && open_seed_red "$ref"; then
        if (( depth > 0 )); then
            git reset --soft "HEAD~${depth}"
        fi
        return
    fi
    # The engine's run branch hangs off the master base and snapshots the seeded tree,
    # so the seed's own Red commit never reaches this history and its Factory-Run-Id
    # names the EARLIER run (bd-ib-5ypy5v). Resolve it from the resumed seed itself.
    seed_red=""
    if seeded_open_red_declared && seed_red="$(seed_red_commit)" && [[ -n "$seed_red" ]]; then
        rebuild_seeded_red "$(git rev-parse "$ref")" "$seed_red"
        return
    fi
    printf '%s\n' "current run's own Red commit was not found beneath checkpoint commits ($(red_search_evidence "$depth"))"
    return 2
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

# Lefthook's closing summary marks each failed hook command with the boxing glove,
# `🥊 03-check-pre-commit (12.3 seconds)`; its boxed banner never starts a line.
failed_hook_commands() {
    grep -cE '^🥊 [^ ]+ \(' "$1" || true
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
    local commands=0
    local reason=""
    budget="$(non_negative "${4:-0}")"
    spent_path="$(git rev-parse --git-path "$MECHANICAL_SPENT_NAME")"
    grant_path="$(git rev-parse --git-path "$MECHANICAL_GRANT_NAME")"
    rm -f "$grant_path"
    printf '%s\n' "$budget" > "$(git rev-parse --git-path "$MECHANICAL_BUDGET_NAME")"
    spent="$(non_negative "$(cat "$spent_path" 2>/dev/null || true)")"
    names="$(failed_target_names "$output")"
    commands="$(non_negative "$(failed_hook_commands "$output")")"
    # The aggregate's list names only its own targets, so a refusal is mechanical
    # only when the aggregate is the one hook command that failed.
    if [[ -n "$names" ]] && (( commands <= 1 )); then
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
    elif (( commands > 1 )); then
        reason="a hook command beside the check aggregate also failed"
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
    local title=""
    local message=""
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
    if [[ "$cause" == LIVESPEC_COMMIT_GREEN_SEEDED_RED_PASSES:* ]]; then
        if ! git diff --cached --quiet; then
            cause="${cause}; Green left staged changes despite the already-complete seed"
            : > "$output"
            printf '%s\n' "commit_green: $cause" >&2
            append_verdict "$handoff" 2 "$output" "$cause"
            append_reentry_class "$handoff" "$output" "$mechanical_targets" "$reentries"
            return 2
        fi
        printf '%s\n' "$cause" | tee "$output"
        append_verdict "$handoff" 0 "$output" "$cause"
        return 0
    fi
    title="${LIVESPEC_PR_TITLE:-}"
    if [[ -n "$title" ]] && ! preserve_rebuilt_seed_red_subject; then
        # Keep the complete Red message after its first line.  `-F` then replaces
        # only the placeholder subject while the commit-msg hook appends Green's
        # evidence, so the replay trailers remain part of the amended commit.
        message="$(git rev-parse --git-path livespec-commit-green-message)"
        {
            printf '%s\n' "$title"
            git log -1 --format=%B | sed '1d'
        } > "$message"
        set +e
        # The command node follows the Green authoring turn rather than running
        # inside it.  Name that turn to the target repository's hook so it can
        # select its affected-tests gate; an unscopable change still falls back
        # to the hook's full aggregate.
        LIVESPEC_AUTHORING_TURN=implement git commit --amend -F "$message" >"$output" 2>&1
        status=$?
        set -e
        rm -f "$message"
    else
        # Direct command-program fixtures that do not represent a dispatched
        # work item have no rendered title.  Publication independently refuses
        # a remaining bare Red subject before it can reach a pull request.
        set +e
        LIVESPEC_AUTHORING_TURN=implement git commit --amend --no-edit >"$output" 2>&1
        status=$?
        set -e
    fi
    cat "$output"
    append_verdict "$handoff" "$status" "$output"
    if (( status != 0 )); then
        append_reentry_class "$handoff" "$output" "$mechanical_targets" "$reentries"
    fi
    return "$status"
}

main "$@"
