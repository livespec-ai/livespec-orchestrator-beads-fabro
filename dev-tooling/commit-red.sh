#!/usr/bin/env bash
#
# Make the Red commit outside the implement agent turn. The file it reads and
# writes is git-local so Fabro's checkpoint commits cannot carry it forward.

set -euo pipefail

readonly CHECKPOINT_LIMIT=500
readonly CHECKPOINT_SUBJECT='^fabro\([^)]*\): '
readonly HANDOFF_NAME="livespec-implement-handoff.md"
readonly OUTPUT_NAME="livespec-commit-red-output"
readonly FLEET_PRODUCT_PREFIXES=(".claude-plugin/scripts/" ".claude-plugin/hooks/" ".claude/hooks/" "dev-tooling/")

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
    git log -1 --format=%B "$ref" 2>/dev/null | awk '
        /^Fabro-Run: / { value = $0; sub(/^Fabro-Run: /, "", value) }
        END { print value }
    '
}

checkpoint_for_run() {
    local ref="$1"
    local run_id="$2"
    checkpoint_commit "$ref" && [[ "$(checkpoint_run_id "$ref")" == "$run_id" ]]
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

red_turn_base() {
    local ref="HEAD"
    local run_id=""
    run_id="$(current_engine_run_id)"
    [[ -n "$run_id" ]] || return 1
    while checkpoint_for_run "$ref" "$run_id"; do
        ref="${ref}~1"
    done
    git rev-parse "$ref"
}

fold_checkpoints() {
    local depth=0
    local ref="HEAD"
    local dispatch_base=""
    while (( depth < CHECKPOINT_LIMIT )) && checkpoint_commit "$ref"; do
        ((depth += 1))
        ref="HEAD~${depth}"
    done
    dispatch_base="$(git rev-parse "$ref")"
    if (( depth > 0 )); then
        git reset --soft "$dispatch_base"
    fi
    printf '%s\n' "$dispatch_base"
}

product_prefixes() {
    local declared=""
    if [[ -f pyproject.toml ]]; then
        declared="$(awk '
            /^\[/ { in_table = ($0 ~ /^\[tool\.livespec_dev_tooling\][[:space:]]*$/); in_array = 0 }
            in_table && /^(source_trees|source_tree_prefixes)[[:space:]]*=/ { in_array = 1 }
            in_table && in_array {
                line = $0
                sub(/#.*/, "", line)
                while (match(line, /"[^"]*"/)) {
                    value = substr(line, RSTART + 1, RLENGTH - 2)
                    sub(/\/+$/, "", value)
                    print value "/"
                    line = substr(line, RSTART + RLENGTH)
                }
                if ($0 ~ /\]/) { in_array = 0 }
            }
        ' pyproject.toml)"
    fi
    if [[ -n "$declared" ]]; then
        printf '%s\n' "$declared"
    else
        printf '%s\n' "${FLEET_PRODUCT_PREFIXES[@]}"
    fi
}

changed_product_paths() {
    local allowed="$1"
    local turn_base="$2"
    local source_head="$3"
    local prefixes=""
    local path=""
    local prefix=""
    prefixes="$(product_prefixes)"
    {
        git diff --name-only --no-renames "$turn_base" "$source_head" --
        git diff --name-only --no-renames "$source_head" --
        git ls-files --others --exclude-standard
    } | sort -u | while IFS= read -r path; do
        [[ "$path" == "$allowed" || "$path" != *.py || "$path" == tests/* ]] && continue
        [[ "$path" == */_vendor/* || "$path" == */__pycache__/* ]] && continue
        while IFS= read -r prefix; do
            if [[ "$path" == "$prefix"* ]]; then
                printf '%s\n' "$path"
                break
            fi
        done <<<"$prefixes"
    done
}

latest_red_test_file() {
    awk '
        /^##[[:space:]]+red([[:space:]]|$)/ { in_red = 1; latest = ""; next }
        /^##[[:space:]]/ { in_red = 0 }
        in_red && /^(Red test file|Test file):[[:space:]]*/ {
            value = $0
            sub(/^(Red test file|Test file):[[:space:]]*/, "", value)
            sub(/^`/, "", value)
            sub(/`$/, "", value)
            sub(/::.*/, "", value)
            latest = value
        }
        END { print latest }
    ' "$1"
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

append_verdict() {
    local handoff="$1"
    local status="$2"
    local output="$3"
    local cause="${4:-}"
    {
        printf '\n## commit_red\n\n'
        printf 'Exit status: %s\n' "$status"
        if [[ -n "$cause" ]]; then
            printf 'Cause: %s\n' "$cause"
        fi
        if (( status != 0 )) && [[ -z "$cause" ]] && [[ -f "$output" ]]; then
            append_failure_details "$output"
        fi
    } >> "$handoff"
}

# The fold leaves HEAD on the dispatch base, so the refused turn's product
# change is discarded by returning the index and working tree to it. The
# handoff and verdict files live in the git directory, so both survive.
return_to_dispatch_base() {
    git reset --hard HEAD >/dev/null
    git clean -fd >/dev/null
}

restore_carried_changes() {
    local dispatch_base="$1"
    local source_head="$2"
    local test_file="$3"
    if ! git diff --quiet "$dispatch_base" "$source_head" -- . ":(exclude)$test_file"; then
        git diff --binary --no-ext-diff "$dispatch_base" "$source_head" -- . ":(exclude)$test_file" \
            | git apply --whitespace=nowarn
    fi
}

restore_patch() {
    local patch="$1"
    if [[ -s "$patch" ]]; then
        git apply --whitespace=nowarn "$patch"
    fi
    rm -f -- "$patch"
}

main() {
    local handoff=""
    local output=""
    local test_file=""
    local product_paths=""
    local source_head=""
    local turn_base=""
    local dispatch_base=""
    local test_snapshot=""
    local working_changes=""
    local status=0
    handoff="$(git rev-parse --git-path "$HANDOFF_NAME")"
    output="$(git rev-parse --git-path "$OUTPUT_NAME")"
    test_file="$(latest_red_test_file "$handoff" 2>/dev/null || true)"
    if [[ -z "$test_file" ]]; then
        : > "$output"
        append_verdict "$handoff" 2 "$output" "latest red section names no test file"
        printf '%s\n' "commit_red: latest red section names no test file" >&2
        return 2
    fi
    source_head="$(git rev-parse HEAD)"
    turn_base="$(red_turn_base)" || {
        printf '%s\n' "commit_red: current engine run id is unknown" >&2
        return 2
    }
    product_paths="$(changed_product_paths "$test_file" "$turn_base" "$source_head")"
    dispatch_base="$(fold_checkpoints)"
    if [[ -n "$product_paths" ]]; then
        : > "$output"
        append_verdict "$handoff" 3 "$output" \
            "red turn changed product paths: ${product_paths//$'\n'/ }"
        printf '%s\n' "commit_red: red turn changed product paths: ${product_paths//$'\n'/ }" >&2
        return_to_dispatch_base
        return 3
    fi
    working_changes="$(mktemp "$(git rev-parse --git-path livespec-commit-red-working.XXXXXX)")"
    git diff --binary --no-ext-diff "$source_head" -- . ":(exclude)$test_file" > "$working_changes"
    test_snapshot="$(mktemp "$(git rev-parse --git-path livespec-commit-red-test.XXXXXX)")"
    cp -- "$test_file" "$test_snapshot"
    git reset --hard HEAD >/dev/null
    mkdir -p "$(dirname "$test_file")"
    cp -- "$test_snapshot" "$test_file"
    rm -f -- "$test_snapshot"
    git reset
    git add -- "$test_file"
    set +e
    # bd-ib-eyhjwr: the repository's commit-msg hook fails open, so a sandbox where its
    # gate cannot run commits the Red with no Factory-Run-Id trailer and commit_green then
    # cannot find its own Red. This command knows the run id, so it records it itself; a
    # hook that stamps the same trailer adds nothing (identical neighbouring trailer).
    local factory_run_id=""
    local -a run_id_args=()
    factory_run_id="$(git config --local --get livespec.factoryRunId 2>/dev/null || true)"
    if [[ -n "$factory_run_id" ]]; then
        run_id_args=(-m "Factory-Run-Id: $factory_run_id")
    fi
    git commit -m "feat: red" ${run_id_args[@]+"${run_id_args[@]}"} >"$output" 2>&1
    status=$?
    set -e
    cat "$output"
    restore_carried_changes "$dispatch_base" "$source_head" "$test_file"
    restore_patch "$working_changes"
    append_verdict "$handoff" "$status" "$output"
    return "$status"
}

main "$@"
