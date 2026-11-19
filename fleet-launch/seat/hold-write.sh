#!/bin/bash
# PROVISIONAL / EXPERIMENTAL — fleet-launch seat helper that writes hold files.
# This directory is a stopgap; its first-class replacements are the livespec console
# application and the committed launch-loop tool bd-ib-jr6w7v (see fleet-launch/README.md).
#
# hold-write.sh <hold-file-path> < body      (seat helper, legacy-dispatcher-agent b27237, 2026-11-14; coordinator STRUCTURAL routing tick 3)
# The ONE way a seat or the coordinator writes tmp/petri-canary/hold-item-* (and hold-repo-*) files. Rule HOLD-ENDS-ARE-DRIVEN, enforced:
# REFUSES (exit 2, nothing written) a body that lacks any of
#   OWNER: <seat>                  - who drives the end (never "coordinator" alone, never empty)
#   END CONDITION: <condition>     - what must be true
#   NEXT STEP: <who> <does what>   - the constructible step that fires the end; a natural event alone ("when X merges") is not a step
# An existing file is backed up to <file>.pre-write-<UTC> before it is replaced. Prints WROTE <file> on success.
set -u
f=${1:?usage: hold-write.sh <hold-file-path> < body}
# 2026-11-14 ~20:0xZ (seat ce9c23, coordinator [096f77] ruling): canary-hold-repo-* is a hold file too; the v0.332.0 canary's write was refused here and the adopt ran without a hold.
case "$(basename "$f")" in hold-item-*|hold-repo-*|hold-gmktec*|canary-hold-repo-*) ;; *) echo "REFUSED: $f is not a hold file name" >&2; exit 2;; esac
body=$(cat)
own=$(printf '%s\n' "$body" | sed -n 's/^OWNER:[[:space:]]*//p' | tail -1)
end=$(printf '%s\n' "$body" | sed -n 's/^END CONDITION:[[:space:]]*//p' | tail -1)
step=$(printf '%s\n' "$body" | sed -n 's/^NEXT STEP:[[:space:]]*//p' | tail -1)
bad=()
[ -n "$own" ] || bad+=("no OWNER: line")
case "${own,,}" in coordinator|coordinator.|legacy-coordinator-agent|legacy-coordinator-agent.) bad+=("OWNER names only the coordinator, which is not an owner");; esac
[ -n "$end" ] || bad+=("no END CONDITION: line")
[ -n "$step" ] || bad+=("no NEXT STEP: line (a natural event alone is not a driven end)")
case "${end,,}" in none*|"n/a"*|never*) bad+=("END CONDITION is unconstructible ('$end')");; esac
if [ ${#bad[@]} -gt 0 ]; then printf 'REFUSED %s: %s\n' "$f" "$(IFS='; '; echo "${bad[*]}")" >&2; exit 2; fi
[ -e "$f" ] && cp "$f" "$f.pre-write-$(date -u +%Y%m%dT%H%M%SZ)"
printf '%s\n' "$body" > "$f.tmp.$$" && mv "$f.tmp.$$" "$f" && echo "WROTE $f"
