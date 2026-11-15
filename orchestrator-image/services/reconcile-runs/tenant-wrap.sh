#!/bin/bash
# livespec tenant credential wrapper for the `reconcile-runs` timer pass.
#
# `install.sh` in this directory installs this file to the path the committed
# `reconcile-runs.service` names in its ExecStart. Usage:
#
#   tenant-wrap.sh -- <command> [args...]
#
# Why it exists (bd-ib-ft426g): a bare `/usr/local/bin/with-livespec-env.sh`
# projects the family's default GitHub App pair, and after the livespec-ai org
# transfer repositories in that org refuse it. The repository therefore names
# the wrapper its own commands must run under in `.livespec.jsonc`
# (`credential_wrapper`), and the pass has to honour that choice at RUN time,
# exactly as the dispatcher's tenant wrapper does, rather than a path frozen
# into the unit at install time. The same resolution is `resolve_tenant_wrapper`
# in fleet-launch/launch-lib.sh.
#
# The tenant repository is TW_REPO when set, otherwise the working directory;
# the unit's WorkingDirectory is the primary checkout. Three outcomes:
#
#   - no readable credential_wrapper: run under the family wrapper;
#   - the credential_wrapper IS the family wrapper (by basename): run it as
#     declared;
#   - any other credential_wrapper: run it nested INSIDE the family wrapper,
#     with the family's BEADS_DOLT_PASSWORD unset so the tenant's own wrapper
#     injects the tenant password. The family wrapper still supplies everything
#     else the pass needs.
#
# Argv elements are passed through intact, including elements that contain
# whitespace (a `/bin/sh -c '<script>' sh` wrapper is one such argv): the
# parser prints one element per line and `mapfile` reads one element per line.
# That holds as long as no element contains a NEWLINE; such an element would be
# split in two. No committed credential_wrapper contains one.
#
# This is a deliberately permissive twin of the dispatcher's resolution: a
# credential_wrapper that cannot be parsed falls back to the family wrapper
# rather than refusing, because the timer has no operator present to read a
# refusal and the next tick asks the same question again.
#
# FAMILY_WRAPPER is the family wrapper's path. `install.sh` reads it from this
# file and rewrites it when LIVESPEC_ENV_WRAPPER names another path, so keep it
# a single unquoted assignment on its own line.
set -u
FAMILY_WRAPPER=/usr/local/bin/with-livespec-env.sh
[ "${1:-}" = "--" ] && shift
R=${TW_REPO:-$PWD}
mapfile -t cw < <(python3 - "$R" <<'PY' 2>/dev/null
import json, re, sys
try:
    t = open(sys.argv[1] + "/.livespec.jsonc", encoding="utf-8").read()
    m = re.search(r'"credential_wrapper"\s*:\s*(\[[^\]]*\])', t)
    for a in json.loads(re.sub(r"//[^\n]*", "", m.group(1))): print(a)
except Exception:
    pass
PY
)
if [ ${#cw[@]} -eq 0 ] || [ "$(basename "${cw[0]}")" = with-livespec-env.sh ]; then
  [ ${#cw[@]} -eq 0 ] && cw=("$FAMILY_WRAPPER" --)
  exec "${cw[@]}" "$@"
else
  exec "$FAMILY_WRAPPER" -- env -u BEADS_DOLT_PASSWORD "${cw[@]}" "$@"
fi
