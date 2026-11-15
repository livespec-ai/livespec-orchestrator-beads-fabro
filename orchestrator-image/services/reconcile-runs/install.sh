#!/usr/bin/env bash
# Install the `reconcile-runs` systemd service + timer, and the tenant
# credential wrapper the service runs through, on a dispatching host.
#
# The refusal below is the whole point of having an installer rather than a
# `cp`. `bd` reads the tenant password from a bare `BEADS_DOLT_PASSWORD` that
# only the project env wrapper injects; a unit installed without a resolvable
# wrapper does not fail loudly, it fails as "Access denied" / "no beads database
# found" every ten minutes forever, which reads as a missing tenant rather than
# as a missing credential. Refusing at install time is the one moment an
# operator is present to read the reason.
#
# Usage:
#   sudo ./install.sh --repo <primary-checkout> [--plugin-root <dir>] [--user <name>]
#
# Environment overrides (all optional, all for testing or a non-standard host):
#   LIVESPEC_ENV_WRAPPER  family wrapper path to require AND to write into the
#                         installed tenant wrapper (default: the path the
#                         committed tenant-wrap.sh already names)
#   LIVESPEC_TENANT_WRAP  where the tenant wrapper is installed, AND the path
#                         written into ExecStart (default: the path the
#                         committed unit already names)
#   UNIT_DIR              where the units are written (default /etc/systemd/system)
#   DRY_RUN=1             render and write the units, but run no systemctl

set -euo pipefail

readonly EX_CONFIG=78
readonly EX_USAGE=64

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly HERE
readonly SERVICE_TEMPLATE="${HERE}/reconcile-runs.service"
readonly TIMER_TEMPLATE="${HERE}/reconcile-runs.timer"
readonly TENANT_WRAP_SOURCE="${HERE}/tenant-wrap.sh"
# The override this installer's committed unit replaces (bd-ib-ft426g). Its
# ExecStart pinned a plugin root and repository at the time it was written, so
# leaving it in place would keep overriding every later install.
readonly SUPERSEDED_DROP_IN="reconcile-runs.service.d/60-tenant-wrap.conf"

# Both paths are read OUT of the committed files rather than repeated here: a
# second copy of a path is a second thing to keep in sync, and the one that
# drifts is always the one nobody reads.
#
# The tenant wrapper's install path: the command the committed unit's ExecStart
# runs.
default_tenant_wrap() {
  sed -n 's|^ExecStart=\([^ ]*\) --.*|\1|p' "${SERVICE_TEMPLATE}" | sed -n '1p'
}

# The family wrapper the tenant wrapper runs everything inside.
default_env_wrapper() {
  sed -n 's|^FAMILY_WRAPPER=\(.*\)$|\1|p' "${TENANT_WRAP_SOURCE}" | sed -n '1p'
}

# Write the tenant wrapper with the family wrapper's path substituted, through a
# temporary file renamed into place: bash reads a running script as it goes, so
# rewriting the file a pass is executing in place could corrupt that pass.
install_tenant_wrap() {
  local env_wrapper="$1" dest="$2" tmp
  mkdir -p "$(dirname "${dest}")"
  tmp="$(mktemp "${dest}.XXXXXX")"
  sed -e "s|^FAMILY_WRAPPER=.*\$|FAMILY_WRAPPER=${env_wrapper}|" \
    "${TENANT_WRAP_SOURCE}" >"${tmp}"
  chmod 0755 "${tmp}"
  mv -f "${tmp}" "${dest}"
}

usage() {
  printf 'usage: %s --repo <primary-checkout> [--plugin-root <dir>] [--user <name>]\n' \
    "${BASH_SOURCE[0]}" >&2
}

main() {
  local repo='' plugin_root='' run_as_user=''
  while (($#)); do
    case "$1" in
      --repo) shift; repo="${1:-}" ;;
      --plugin-root) shift; plugin_root="${1:-}" ;;
      --user) shift; run_as_user="${1:-}" ;;
      -h|--help) usage; return 0 ;;
      *) printf 'unknown argument: %s\n' "$1" >&2; usage; return "${EX_USAGE}" ;;
    esac
    shift || true
  done

  if [[ -z "${repo}" ]]; then
    printf 'ERROR: --repo <primary-checkout> is required\n' >&2
    usage
    return "${EX_USAGE}"
  fi
  if [[ ! -d "${repo}" ]]; then
    printf 'ERROR: --repo %s is not a directory\n' "${repo}" >&2
    return "${EX_CONFIG}"
  fi

  local env_wrapper template_tenant_wrap tenant_wrap
  env_wrapper="${LIVESPEC_ENV_WRAPPER:-$(default_env_wrapper)}"
  template_tenant_wrap="$(default_tenant_wrap)"
  tenant_wrap="${LIVESPEC_TENANT_WRAP:-${template_tenant_wrap}}"
  if [[ ! -x "${env_wrapper}" ]]; then
    printf 'ERROR: project env wrapper not executable: %s\n' "${env_wrapper}" >&2
    printf 'The timer would run `bd` without BEADS_DOLT_PASSWORD and fail every pass as\n' >&2
    printf 'an absent tenant rather than an absent credential. Install the wrapper (or set\n' >&2
    printf 'LIVESPEC_ENV_WRAPPER to where this host keeps it) and re-run.\n' >&2
    return "${EX_CONFIG}"
  fi

  : "${plugin_root:=${HERE%/orchestrator-image/services/reconcile-runs}/.claude-plugin}"
  : "${run_as_user:=$(id -un)}"
  local unit_dir="${UNIT_DIR:-/etc/systemd/system}"
  mkdir -p "${unit_dir}"

  install_tenant_wrap "${env_wrapper}" "${tenant_wrap}"
  printf 'installed %s\n' "${tenant_wrap}"
  sed \
    -e "s|@PLUGIN_ROOT@|${plugin_root}|g" \
    -e "s|@PRIMARY_REPO@|${repo}|g" \
    -e "s|@RUN_AS_USER@|${run_as_user}|g" \
    -e "s|^ExecStart=${template_tenant_wrap} |ExecStart=${tenant_wrap} |" \
    "${SERVICE_TEMPLATE}" >"${unit_dir}/reconcile-runs.service"
  cp "${TIMER_TEMPLATE}" "${unit_dir}/reconcile-runs.timer"
  printf 'installed %s/reconcile-runs.{service,timer}\n' "${unit_dir}"
  if [[ -e "${unit_dir}/${SUPERSEDED_DROP_IN}" ]]; then
    rm -f "${unit_dir}/${SUPERSEDED_DROP_IN}"
    rmdir "${unit_dir}/reconcile-runs.service.d" 2>/dev/null || true
    printf 'removed superseded drop-in %s/%s\n' "${unit_dir}" "${SUPERSEDED_DROP_IN}"
  fi

  if [[ "${DRY_RUN:-}" == "1" ]]; then
    printf 'DRY_RUN=1: skipping systemctl daemon-reload / enable --now\n'
    return 0
  fi
  systemctl daemon-reload
  systemctl enable --now reconcile-runs.timer
  systemctl list-timers reconcile-runs.timer --no-pager
}

main "$@"
