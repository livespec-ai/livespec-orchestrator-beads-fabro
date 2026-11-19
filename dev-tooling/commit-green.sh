#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
exec "$script_dir/../.claude-plugin/scripts/livespec_orchestrator_beads_fabro/commands/_dispatcher_commit_green_program.sh" "$@"
