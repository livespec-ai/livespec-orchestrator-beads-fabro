#!/usr/bin/env bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch's resume helper.
#
# This stopgap's first-class replacements are the livespec console application
# and the committed launch-loop tool bd-ib-jr6w7v (see README.md). resume-capped.sh
# starts every resume through this script once its caller-side gates have passed;
# it runs `dispatcher.py resume --item <item>` in the target repository, on the
# installed plugin build that repository is bound to, under that repository's
# committed credential wrapper (a non-family tenant's bd gets its own password),
# with the target factory's dev token exported for the Dispatcher's factory read.
#
# Usage: resume-repo.sh <repo-path> <item-id>
set -u
FLEET_LAUNCH_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=fleet-launch/config.sh
. "$FLEET_LAUNCH_DIR/config.sh"
REPO=$(realpath -e "${1:?usage: resume-repo.sh <repo-path> <item-id>}") || { echo "resume-repo: repository path $1 does not resolve" >&2; exit 2; }
ITEM=${2:?usage: resume-repo.sh <repo-path> <item-id>}
# shellcheck source=fleet-launch/launch-lib.sh
. "$FLEET_LAUNCH_DIR/launch-lib.sh"
OUT=$FLEET_LAUNCH_STATE_DIR
FACTORY=$FLEET_LAUNCH_RESUME_FACTORY

if ! resolve_tenant_wrapper; then
  echo "resume-repo: the credential wrapper of $REPO cannot be read; refusing" >&2
  exit 2
fi
build=$(installed_build)
[ -n "$build" ] || { echo "resume-repo: no installed plugin build is registered for $REPO; refusing" >&2; exit 2; }
plugin="$FLEET_LAUNCH_PLUGIN_CACHE/$build"
token=$(ssh -o BatchMode=yes "$FLEET_LAUNCH_GMK_SSH" cat "$FLEET_LAUNCH_GMK_SERVER_ENV" 2>/dev/null | sed -n 's/^FABRO_DEV_TOKEN=//p' | tail -n 1)
if [ -n "$token" ]; then export "FABRO_DEV_TOKEN__${FACTORY}=$token"; fi
echo "=== $(date -u +%FT%TZ) RESUME start: dispatcher.py resume --repo $REPO --item $ITEM --factory $FACTORY (build $build, wrapper: $(wrapper_description))"
(cd "$REPO" && wrap -- env LIVESPEC_FACTORY_READ_WRAPPER="$FLEET_LAUNCH_DEFAULT_WRAPPER" python3 "$plugin/scripts/bin/dispatcher.py" resume --repo "$REPO" --item "$ITEM" --factory "$FACTORY" --invoker "$FLEET_LAUNCH_RESUME_INVOKER" --json) > "$OUT/$ITEM-resume.json" 2> "$OUT/$ITEM-resume.stderr"
rc=$?
echo "$(date -u +%FT%TZ) RESUME rc=$rc"
if grep -q "resume refused" "$OUT/$ITEM-resume.stderr" 2>/dev/null; then
  echo "RESUME REFUSED: $(grep -v 'bd exited' "$OUT/$ITEM-resume.stderr" | grep -A2 'resume refused' | tr '\n' ' ' | cut -c1-500)"
fi
exit "$rc"
