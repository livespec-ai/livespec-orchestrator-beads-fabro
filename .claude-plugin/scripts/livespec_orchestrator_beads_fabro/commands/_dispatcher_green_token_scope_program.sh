#!/usr/bin/env bash
# A green token is a tree verdict, not an unconditional cache entry. The shared
# utility records only `tree_hash`; this adapter stores the excluded targets too.
# Its `scope` operation is the one declaration both the janitor and pre-push use
# for targets their respective aggregate paths intentionally omit.

set -euo pipefail

operation=${1:-}
if [[ "$operation" != write && "$operation" != check && "$operation" != scope && "$operation" != delegated ]]; then
    exit 2
fi
shift

if [[ "$operation" == scope ]]; then
    [[ "$#" -eq 0 ]] || exit 2
    # Pre-push always omits the same-repository live picker acceptance. A
    # sandbox additionally omits the environmental master-CI check.
    printf '%s\n' check-codex-skill-picker
    if [[ "$(git config --get --bool livespec.sandboxExempt || printf 'false')" == true ]]; then
        printf '%s\n' check-master-ci-green
    fi
    exit 0
fi

targets=("$@")
for target in "${targets[@]}"; do
    [[ "$target" =~ ^[a-z0-9][a-z0-9-]*$ ]] || exit 2
done
if [[ ${#targets[@]} -gt 0 ]] && [[ $(printf '%s\n' "${targets[@]}" | LC_ALL=C sort -u | wc -l) -ne ${#targets[@]} ]]; then
    exit 2
fi

git_dir=$(git rev-parse --absolute-git-dir)
tree_hash=$(git rev-parse 'HEAD^{tree}')
token_path="${git_dir}/livespec-green-token.json"

if [[ "$operation" == write ]]; then
    python3 - "$token_path" "$tree_hash" "${targets[@]}" <<'PY'
import json
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
path.write_text(json.dumps({"tree_hash": sys.argv[2], "skipped_targets": sys.argv[3:]}), encoding="utf-8")
PY
    exit 0
fi

[[ -z $(git status --porcelain) ]] || exit 1
python3 - "$token_path" "$tree_hash" "$operation" "${targets[@]}" <<'PY'
import json
import pathlib
import sys

PICKER = "check-codex-skill-picker"
try:
    token = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, ValueError):
    raise SystemExit(1)
if not isinstance(token, dict) or token.get("tree_hash") != sys.argv[2]:
    raise SystemExit(1)
requested = sys.argv[4:]
stored = token.get("skipped_targets")
if stored is None:
    if (
        token.get("mode") != "normal"
        or token.get("scope") != "full-suite"
        or "pre_commit_aggregate" in token
        or PICKER not in requested
    ):
        raise SystemExit(1)
    raise SystemExit(0)
if sys.argv[3] == "delegated":
    raise SystemExit(1)
if (
    not isinstance(stored, list)
    or not all(isinstance(one, str) for one in stored)
    or len(stored) != len(set(stored))
    or set(stored) != set(requested)
):
    raise SystemExit(1)
PY
