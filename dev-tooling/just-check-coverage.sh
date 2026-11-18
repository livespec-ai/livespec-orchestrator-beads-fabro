#!/usr/bin/env bash
set -euo pipefail

producer_rc=0
verdict_files=(
    .coverage-gates/per-file.status
    .coverage-gates/per-file.log
    .coverage-gates/per-file.provenance
)
missing_verdict_files=()
for verdict_file in "${verdict_files[@]}"; do
    [[ -f "$verdict_file" ]] || missing_verdict_files+=("$verdict_file")
done

if [[ ${#missing_verdict_files[@]} -ne 0 ]]; then
    if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
        echo "::error::check-coverage: missing canonical per-file verdict: ${missing_verdict_files[*]}" >&2
        exit 1
    fi
    echo ":: check-coverage: no canonical per-file verdict; running the suite"
    set +e
    bash dev-tooling/just-check-per-file-coverage.sh
    producer_rc=$?
    set -e
    if [[ "$producer_rc" -ne 0 && ! -f .coverage-gates/per-file.status ]]; then
        exit "$producer_rc"
    fi
else
    if [[ "${GITHUB_ACTIONS:-}" == "true" ]]; then
        expected_commit=$(git rev-parse HEAD)
        expected_uid=$(id -u)
        actual_commit=$(sed -n 's/^commit=//p' .coverage-gates/per-file.provenance)
        actual_uid=$(sed -n 's/^uid=//p' .coverage-gates/per-file.provenance)
        if [[ "$actual_commit" != "$expected_commit" || "$actual_uid" != "$expected_uid" ]]; then
            echo "::error::check-coverage: canonical per-file verdict provenance mismatch: expected commit=$expected_commit uid=$expected_uid; got commit=$actual_commit uid=$actual_uid" >&2
            exit 1
        fi
    fi
    echo ":: check-coverage: reading the canonical per-file verdict"
    cat .coverage-gates/per-file.log >&2
fi

status=$(<.coverage-gates/per-file.status)
# Consume the coverage data and its canonical verdict together so a later
# standalone invocation cannot report from stale evidence.
rm -f .coverage .coverage-gates/per-file.log .coverage-gates/per-file.status .coverage-gates/per-file.provenance
rmdir .coverage-gates 2>/dev/null || true

# A standalone run owns its own suite, so a suite failure fails it as before.
[ "$producer_rc" -eq 0 ] || exit "$producer_rc"
[ "$status" -eq 0 ] || exit "$status"
