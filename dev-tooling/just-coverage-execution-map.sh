#!/usr/bin/env bash
# bd-ib-uvx5l7: regenerate the committed coverage-execution map the affected-tests
# gate (dev-tooling/checks/_affected_tests_selection.py) selects tests from.
#
# Runs the whole suite once under coverage with `--cov-context=test`, so every
# executed line is attributed to the pytest node id that ran it, then hands that
# data to dev-tooling/checks/_coverage_execution_map.py, which writes
# `dev-tooling/coverage-execution-map.json`: each product module mapped to the
# sorted test modules that executed a line of it, tied to the merge base with
# origin/master. Commit the result. Re-run it when the suite or the modules'
# reach drift apart; a stale record only costs the gate a wider coverage retry,
# and a module the map does not list falls back to the import-graph selection.
#
# LIVESPEC_COVERAGE_EXECUTION_MAP_DATA names a saved coverage data file to read
# instead of running the suite; LIVESPEC_COVERAGE_EXECUTION_MAP_OUT overrides the
# output path. A failing suite leaves the existing map alone.
set -euo pipefail

output=${LIVESPEC_COVERAGE_EXECUTION_MAP_OUT:-dev-tooling/coverage-execution-map.json}
data=${LIVESPEC_COVERAGE_EXECUTION_MAP_DATA:-}

if [[ -z "$data" ]]; then
    scratch=$(mktemp -d)
    trap 'rm -rf "$scratch"' EXIT
    data="$scratch/coverage.dat"
    workers=$(bash dev-tooling/just-test-nprocs.sh)
    echo ":: coverage-execution-map: running the suite once; pytest-xdist workers=${workers}"
    if ! env COVERAGE_FILE="$data" uv run pytest \
        -n "$workers" \
        --basetemp="${TMPDIR:-/tmp}/pytest" \
        -p no:cacheprovider \
        --cov --cov-branch --cov-config=pyproject.toml --cov-context=test \
        --cov-report= --cov-fail-under=0; then
        echo ":: coverage-execution-map: the suite failed; its coverage is not trusted, map unchanged" >&2
        exit 1
    fi
fi

uv run python dev-tooling/checks/_coverage_execution_map.py "$data" "$output"
echo ":: coverage-execution-map: wrote ${output}"
