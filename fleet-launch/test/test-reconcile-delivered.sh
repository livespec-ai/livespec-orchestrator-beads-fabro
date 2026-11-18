#!/usr/bin/env bash
# Hermetic coverage for the fleet-level delivery reconciliation report.
set -eu
TEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
RECONCILE="$TEST_DIR/../reconcile-delivered.sh"
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
git init -q --bare "$T/origin.git"
git init -q "$T/repo"
git -C "$T/repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "$T/repo" remote add origin "$T/origin.git"
git -C "$T/repo" push -q origin HEAD:refs/heads/master
git -C "$T/repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m 'fix: deliver bd-ib-open'
delivery=$(git -C "$T/repo" rev-parse HEAD)
git -C "$T/repo" push -q origin HEAD:refs/heads/master
git -C "$T/repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m 'fix: deliver bd-ib-open-extra'
git -C "$T/repo" push -q origin HEAD:refs/heads/master
git -C "$T/repo" -c user.email=t@t -c user.name=t commit -q --allow-empty -m 'fix: deliver trailer-only item' -m 'Work-Item: bd-ib-trailer'
trailer_delivery=$(git -C "$T/repo" rev-parse HEAD)
git -C "$T/repo" push -q origin HEAD:refs/heads/master
mkdir "$T/bin"
cat > "$T/bin/bd" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' '[{"id":"bd-ib-open","status":"active"},{"id":"bd-ib-trailer","status":"active"},{"id":"bd-ib-done","status":"done"},{"id":"bd-ib-unrelated","status":"ready"}]'
STUB
cat > "$T/wrapper" <<'STUB'
#!/usr/bin/env bash
[ "$1" = -- ] && shift
exec "$@"
STUB
chmod +x "$T/bin/bd" "$T/wrapper"
out=$(env PATH="$T/bin:$PATH" WRAPPER="$T/wrapper" bash "$RECONCILE" "$T/repo")
case "$out" in
  *"item=bd-ib-open status=active commit=$delivery source=origin/master reason=delivery-commit-names-open-item"*) ;;
  *) echo "FAIL delivered open item was not reported: $out" >&2; exit 1 ;;
esac
case "$out" in
  *"item=bd-ib-trailer status=active commit=$trailer_delivery source=origin/master reason=delivery-commit-names-open-item"*) ;;
  *) echo "FAIL trailer-named open item was not reported: $out" >&2; exit 1 ;;
esac
case "$out" in
  *bd-ib-done*|*bd-ib-unrelated*) echo "FAIL closed or unmentioned item was reported: $out" >&2; exit 1 ;;
esac
case "$out" in *"DELIVERED-OPEN-SUMMARY count=2"*) ;; *) echo "FAIL report summary: $out" >&2; exit 1 ;; esac
echo "ok   delivered open items are reported with their origin/master commits"
