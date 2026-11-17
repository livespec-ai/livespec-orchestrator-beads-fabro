#!/usr/bin/env bash
# Hermetic tests for bd-remote.sh and the guard's opt-in routing to it
# (livespec-dev-tooling-tbhqye). A stub `ssh` on PATH records its arguments,
# decodes the wire format and echoes the decoded argv; a stub bd-real marks
# local runs; a real unix socket stands in for the ControlMaster socket.
set -uo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd -P)"
GUARD="${SCRIPT_DIR}/../bd-guard.sh"
REMOTE="${SCRIPT_DIR}/../bd-remote.sh"

WORK="$(mktemp -d)"
SOCK_PID=""
cleanup() { [ -n "$SOCK_PID" ] && kill "$SOCK_PID" 2>/dev/null; rm -rf "$WORK"; }
trap cleanup EXIT

# Repo layout: ${WORK}/repos/demo-repo (git root with .beads) and a worktree-like
# sibling checked out of it, plus a plain dir that is not a git repo.
mkdir -p "${WORK}/bin" "${WORK}/repos/demo-repo/.beads" "${WORK}/plain"
git -C "${WORK}/repos/demo-repo" init -q
git -C "${WORK}/repos/demo-repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "${WORK}/repos/demo-repo" worktree add -q "${WORK}/wt-branch" -b wtb 2>/dev/null
mkdir -p "${WORK}/wt-branch/.beads"

cat >"${WORK}/bin/ssh" <<'STUB'
#!/bin/sh
case " $* " in
    *" -O check "*)
        echo check >>"$STUB_SSH_CHECKLOG"
        exit "${STUB_CHECK_EXIT:-0}" ;;
esac
printf '%s\n' "$@" >"$STUB_SSH_ARGS"
if [ -n "${STUB_SSH_EXIT:-}" ]; then exit "$STUB_SSH_EXIT"; fi
for last in "$@"; do :; done
b64=${last##* }
printf '%s' "$b64" | base64 -d | tr '\0' '\n' >"$STUB_SSH_DECODED"; echo >>"$STUB_SSH_DECODED"
[ -n "${STUB_SSH_STDIN:-}" ] && cat >"$STUB_SSH_STDIN"
printf 'remote-ran\n'
exit "${STUB_SSH_REMOTE_RC:-0}"
STUB
cat >"${WORK}/real-bd" <<'STUB'
#!/bin/sh
printf '%s\n' "$@" >"$STUB_REAL_ARGS"
printf 'local-ran\n'
exit "${STUB_REAL_RC:-0}"
STUB
chmod +x "${WORK}/bin/ssh" "${WORK}/real-bd"

python3 - "${WORK}/ctl.sock" <<'PY' &
import socket, sys, time, os
s = socket.socket(socket.AF_UNIX); s.bind(sys.argv[1]); s.listen(1)
time.sleep(600)
PY
SOCK_PID=$!
for _ in $(seq 1 100); do [ -S "${WORK}/ctl.sock" ] && break; sleep 0.05; done

printf 'CONTROL_SOCKET=%s\nSSH_TARGET=vps-ctl\n' "${WORK}/ctl.sock" >"${WORK}/remote.conf"

export PATH="${WORK}/bin:${PATH}"
export LIVESPEC_BD_REAL="${WORK}/real-bd"
export LIVESPEC_BD_REMOTE_CONF="${WORK}/remote.conf"
export LIVESPEC_BD_REMOTE_BIN="$REMOTE"
export LIVESPEC_BD_REMOTE_LOG="${WORK}/remote.log"
export LIVESPEC_BD_GUARD_OTLP=off
export LIVESPEC_BD_GUARD_MODE_FILE="${WORK}/no-such-mode-file"
export LIVESPEC_BD_GUARD_MODE=warn
export STUB_SSH_ARGS="${WORK}/ssh-args" STUB_SSH_DECODED="${WORK}/decoded" STUB_REAL_ARGS="${WORK}/real-args" STUB_SSH_CHECKLOG="${WORK}/checklog"

PASS=0; FAIL=0
pass() { PASS=$((PASS + 1)); echo "  ok:   $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL: $1" >&2; }

# run CWD ARGV... -> OUT ERR RC (via the guard, as installed `bd` would be)
run() {
    local cwd="$1"; shift
    rm -f "$STUB_SSH_ARGS" "$STUB_SSH_DECODED" "$STUB_REAL_ARGS" "$STUB_SSH_CHECKLOG"
    OUT=$(cd "$cwd" && "$GUARD" "$@" 2>"${WORK}/err"); RC=$?
    ERR=$(cat "${WORK}/err")
}
ran_remote() { [ -f "$STUB_SSH_ARGS" ]; }
ran_local()  { [ -f "$STUB_REAL_ARGS" ]; }
REPO="${WORK}/repos/demo-repo"

# 1. remote path: exact ssh argv and decodable argv.
run "$REPO" show demo-1 --json
if ran_remote && ! ran_local && [ "$OUT" = "remote-ran" ] && [ "$RC" -eq 0 ] \
    && [ "$(tr '\n' ' ' <"$STUB_SSH_ARGS")" = "-S ${WORK}/ctl.sock -o ControlMaster=no -o BatchMode=yes -o ConnectTimeout=5 -T vps-ctl in demo-repo bd $(printf 'show\0demo-1\0--json' | base64 | tr -d '\n') " ]; then
    pass "remote: sends exactly 'in demo-repo bd <b64>' over the control socket"
else
    fail "remote exact ssh argv ($(tr '\n' '|' <"$STUB_SSH_ARGS" 2>/dev/null))"
fi

# 2. awkward args round-trip byte for byte.
# shellcheck disable=SC2016
run "$REPO" comments add demo-1 'a "quoted" $(touch /tmp/x) `id` it'"'"'s' '' 'two  spaces'
# shellcheck disable=SC2016
printf '%s\n' comments add demo-1 'a "quoted" $(touch /tmp/x) `id` it'"'"'s' '' 'two  spaces' >"${WORK}/exp"
if ran_remote && cmp -s "${WORK}/exp" "$STUB_SSH_DECODED"; then
    pass "remote: spaces, quotes, \$(...), backticks and an empty arg survive the encoding"
else
    fail "argv round trip: $(cat "$STUB_SSH_DECODED" 2>/dev/null)"
fi

# 3. worktree names the repository, not the branch directory.
run "${WORK}/wt-branch" list --json
if ran_remote && grep -q '^in demo-repo bd ' "$STUB_SSH_ARGS"; then
    pass "remote: a worktree resolves the repository name (not the branch dir)"
else
    fail "worktree repo name ($(tail -1 "$STUB_SSH_ARGS" 2>/dev/null))"
fi

# 4. host-path / connection flags stay local.
for f in "--db=/x" "--db" "--database=x" "--dolt-port=1" "--host" "--port=3" "--file=a" "--body-file" \
         "--design-file=a" "-f" "--path=p" "--dir" "--config=c" "--output=o" "-o" "--jsonl=j"; do
    run "$REPO" show t "$f" v
    if ran_local && ! ran_remote && [ "$OUT" = "local-ran" ]; then :; else fail "flag $f did not stay local (rc=$RC out=$OUT err=$ERR remote=$(ran_remote && echo y) local=$(ran_local && echo y))"; fi
done
pass "local: all denied host-path/connection flags (and =value forms) stay local"

# 5. leading flag and help/version/completion/send-metrics stay local.
for v in --version -h help version completion send-metrics; do
    run "$REPO" "$v"
    if ran_local && ! ran_remote; then :; else fail "$v did not stay local"; fi
done
pass "local: leading flag, help, version, completion, send-metrics stay local"

# 6. no git repo / no .beads stays local.
run "${WORK}/plain" list
if ran_local && ! ran_remote; then pass "local: outside a git repository"; else fail "plain dir"; fi
mkdir -p "${WORK}/nobeads"; git -C "${WORK}/nobeads" init -q
run "${WORK}/nobeads" list
if ran_local && ! ran_remote; then pass "local: git root without .beads"; else fail "no .beads"; fi

# 7. no config / socket absent / not a socket = today's behaviour (guard calls bd-real directly).
LIVESPEC_BD_REMOTE_CONF="${WORK}/absent.conf" run "$REPO" list
if ran_local && ! ran_remote && [ "$OUT" = "local-ran" ]; then pass "no config file: local, as today"; else fail "no config"; fi
printf 'CONTROL_SOCKET=%s\nSSH_TARGET=vps-ctl\n' "${WORK}/missing.sock" >"${WORK}/c2.conf"
LIVESPEC_BD_REMOTE_CONF="${WORK}/c2.conf" run "$REPO" list
if ran_local && ! ran_remote; then pass "socket absent: local, as today"; else fail "socket absent"; fi
: >"${WORK}/regular"
printf 'CONTROL_SOCKET=%s\nSSH_TARGET=vps-ctl\n' "${WORK}/regular" >"${WORK}/c3.conf"
LIVESPEC_BD_REMOTE_CONF="${WORK}/c3.conf" run "$REPO" list
if ran_local && ! ran_remote; then pass "control path is not a socket: local, as today"; else fail "not a socket"; fi

# 8. liveness check fails: nothing sent, local run, logged to stderr and file.
rm -f "$LIVESPEC_BD_REMOTE_LOG"
STUB_CHECK_EXIT=255 run "$REPO" list --json
if ! ran_remote && ran_local && [ "$OUT" = "local-ran" ] && [ "$RC" -eq 0 ] && [ -f "$STUB_SSH_CHECKLOG" ] \
    && grep -q 'falling back to local bd' <<<"$ERR" && grep -q 'falling back to local bd' "$LIVESPEC_BD_REMOTE_LOG"; then
    pass "check fails: nothing sent, local bd runs, fallback logged to stderr and the log file"
else
    fail "check-fail fallback (rc=$RC err=$ERR)"
fi

# 8b. check ok, then ssh 255: never re-run locally, one clear error, exit 255.
STUB_SSH_EXIT=255 run "$REPO" create --title x
if ran_remote && ! ran_local && [ "$RC" -eq 255 ] \
    && [ "$ERR" = "bd-remote: connection to the VPS failed after the command was sent; not retried" ]; then
    pass "check ok then ssh 255: no local run, exit 255, one error line"
else
    fail "post-send 255 (rc=$RC err=$ERR local=$(ran_local && echo y || echo n))"
fi

# 9. a remote nonzero is returned and NOT retried locally.
STUB_SSH_REMOTE_RC=3 run "$REPO" close demo-1
if ran_remote && ! ran_local && [ "$RC" -eq 3 ]; then
    pass "remote bd status 3: returned as is, never retried locally"
else
    fail "remote nonzero (rc=$RC local=$(ran_local && echo y || echo n))"
fi
STUB_SSH_EXIT=126 run "$REPO" close demo-1
if ! ran_local && [ "$RC" -eq 126 ]; then pass "server denial (126) is returned, not retried"; else fail "126 handling"; fi

# 10. stdin passes through ssh.
rm -f "${WORK}/stdin-seen"
OUT=$(cd "$REPO" && printf 'piped body' | STUB_SSH_STDIN="${WORK}/stdin-seen" "$GUARD" comments add demo-1 2>/dev/null)
if [ "$(cat "${WORK}/stdin-seen" 2>/dev/null)" = "piped body" ]; then pass "stdin passes straight through to ssh"; else fail "stdin"; fi

# 10b. a fallback after a failed check still receives the original stdin.
rm -f "$STUB_REAL_ARGS"
cat >"${WORK}/real-bd-stdin" <<'STUB'
#!/bin/sh
cat >"$STUB_REAL_STDIN"
STUB
chmod +x "${WORK}/real-bd-stdin"
(cd "$REPO" && printf 'fallback body' | STUB_CHECK_EXIT=255 STUB_REAL_STDIN="${WORK}/real-stdin" \
    LIVESPEC_BD_REAL="${WORK}/real-bd-stdin" "$GUARD" comments add demo-1 >/dev/null 2>&1)
if [ "$(cat "${WORK}/real-stdin" 2>/dev/null)" = "fallback body" ]; then
    pass "check fails: the local fallback still receives the original stdin"
else
    fail "stdin on fallback"
fi

# 10c. verb allowlist / flag denylist mirror of the server: denied runs local.
for argv in "sql select 1" "export" "edit x" "init" "import" "config set k v" "config" \
            "show x -C /tmp" "show x -c /tmp" "show x --global" "show x --GLOBAL" "show x --Db=/p" \
            "show x --profile p" "show x --directory d" "show x --description-file f" "show x --credentials-file f"; do
    # shellcheck disable=SC2086
    run "$REPO" $argv
    if ran_local && ! ran_remote && [ "$OUT" = "local-ran" ]; then :; else fail "'$argv' did not run local"; fi
done
pass "local: sql, export, edit, init, import, config set/bare, and -C/--global/--profile/--directory/... (case-insensitive) run local"
for argv in "config get k" "config list" "show x" "comment x hi"; do
    # shellcheck disable=SC2086
    run "$REPO" $argv
    if ran_remote && ! ran_local; then :; else fail "'$argv' did not go remote"; fi
done
pass "remote: config get/list, show, comment go remote"

# 11. guard create post-processing still works over the remote path.
run "$REPO" create --title "x"
if ran_remote && [ "$OUT" = "remote-ran" ] && [ "$RC" -eq 0 ]; then
    pass "guard create path: remote stdout is replayed unchanged"
else
    fail "create over remote (out=$OUT rc=$RC)"
fi

echo ""
echo "bd-remote tests: ${PASS} passed, ${FAIL} failed"
[ "$FAIL" -eq 0 ]
