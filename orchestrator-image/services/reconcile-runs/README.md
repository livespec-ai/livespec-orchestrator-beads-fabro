# `reconcile-runs` host timer

Committed unit TEXT for the periodic reconciliation of every declared factory's
non-terminal run inventory against the ledger. Installing it on a host is a
separate operator action; nothing in this repository installs it.

## Why a timer, when the dispatch path already reconciles

`dispatch_preamble` runs one reconciliation pass at the head of every
`dispatcher.py dispatch` and every `loop` tick. That covers the host while it is
dispatching, and only while it is dispatching. A host whose queue has drained
still holds every orphaned Fabro run it launched, and an orphan holds a
scheduler slot until something looks at it — so the interval with no dispatches
is exactly the interval with nobody watching. The timer is what closes it.

## One pass collects every dispatching repository's ended runs

The pass also deletes, through the provider, every ended run whose work-item is
closed in the ledger of the repository that dispatched it. It reaches the other
repositories through the host's plugin install registry
(`~/.claude/plugins/installed_plugins.json`): each registered repository's own
dispatch journal and ledger attribute and grade its runs, so a repository's runs
do not depend on a timer of that repository's own, and a repository that has never
collected (livespec-console-beads-fabro) is collected by this one. A run whose
work-item is open, blocked, needs-human or unreadable in its repository's ledger is
left in place; the pass journals each collection (`ended-run-collected`) and each
refusal (`ended-run-collection-refused`) with the run id, the dispatching
repository, the work-item id and the status read, and journals a standing refusal
once. The one-time sweep of already-leaked workspaces is a host operation, not part
of this timer.

## The pass runs under the tenant's committed credential wrapper

The service's `ExecStart` runs the pass through `tenant-wrap.sh`, which
`install.sh` installs at `/usr/local/libexec/livespec-tenant-wrap.sh`. At run
time it reads `credential_wrapper` from the `.livespec.jsonc` of the tenant
repository (the unit's working directory, or `TW_REPO` when set) and resolves it
the way the dispatcher's tenant wrapper does:

- no `.livespec.jsonc`, or no `credential_wrapper` key: the pass runs under the
  family wrapper `/usr/local/bin/with-livespec-env.sh`;
- a `credential_wrapper` whose command is the family wrapper: the pass runs
  under it as declared;
- any other `credential_wrapper`: it runs nested inside the family wrapper with
  `BEADS_DOLT_PASSWORD` unset, so the tenant wrapper injects its own password.
- a `.livespec.jsonc` that cannot be read, or a `credential_wrapper` that is not
  a non-empty array of non-empty strings: the pass REFUSES with exit 78 and a
  `credential-wrapper-unreadable` line naming the file, and runs nothing. A
  wrapper that is not an executable file also refuses. It never falls back to
  the family wrapper, because that fallback mints the wrong GitHub App.

livespec-dev-tooling's Ansible role `reconcile_runs` installs its own copy of
this wrapper at the same path, so the two are kept identical apart from comments
and the `credential-wrapper-unreadable` cause in the refusal text.

A bare family wrapper is not enough on its own: it projects the family's default
GitHub App pair, which livespec-ai repositories refuse (bd-ib-ft426g). This
replaces the host override `reconcile-runs.service.d/60-tenant-wrap.conf`, which
`install.sh` removes when it finds it.

## Install

```bash
sudo ./install.sh --repo "$HOME/workspace/livespec-orchestrator-beads-fabro"
```

`--plugin-root` defaults to this repository's `.claude-plugin/`; `--user`
defaults to the invoking user. `install.sh` REFUSES (exit 78) when the family
env wrapper named in `tenant-wrap.sh` is not an executable file on the host:
without it `bd` runs with no `BEADS_DOLT_PASSWORD` and every pass fails as
`Access denied` / `no beads database found`, which reads as an absent tenant
rather than an absent credential.

Set `LIVESPEC_ENV_WRAPPER` when a host keeps the family wrapper somewhere other
than the path `tenant-wrap.sh` names; the installer both requires that path and
writes it into the installed tenant wrapper. Set `LIVESPEC_TENANT_WRAP` to
install the tenant wrapper somewhere other than the path the committed unit
names; the installer writes that path into `ExecStart`. `UNIT_DIR` and
`DRY_RUN=1` exist for rehearsal and for this repository's own tests. `DRY_RUN=1`
still writes the units and the tenant wrapper; it only skips `systemctl`.

## Verify

```bash
systemctl list-timers reconcile-runs.timer --no-pager
journalctl -u reconcile-runs.service -n 50 --no-pager
```

Each pass also appends one `reconcile-runs-pass` record to the repository's
dispatch journal (`tmp/fabro-dispatch-journal.jsonl`) naming the factories
surveyed, the orphans found and reconciled, and the errors — so a pass that
found nothing is distinguishable from a pass that never ran.
