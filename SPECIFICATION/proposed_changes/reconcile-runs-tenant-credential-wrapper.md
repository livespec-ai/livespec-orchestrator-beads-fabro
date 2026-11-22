---
topic: reconcile-runs-tenant-credential-wrapper
author: claude-opus-5-5
created_at: 2026-11-15T11:11:00Z
---

## Proposal: A reconcile-runs pass mints its GitHub credential through the tenant repository's committed credential_wrapper

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The tenant-scoped GitHub credential clause of §"Self-contained plugin dispatch" lists the in-container fresh clones, the in-sandbox PR leg, the merge-poll and the post-merge refresh as the dispatch-path GitHub operations that MUST mint from the App environment the dispatch target's own credential_wrapper injects. It does not name the reconcile-runs pass, which also performs GitHub writes on the dispatch path (it completes handed-off merges) and which runs on a clock from a host systemd timer as well as inside dispatch and loop. This proposal names every reconcile-runs pass, whether a dispatch preamble, a loop tick, an operator or the host timer drives it, among those operations, and requires the pass to resolve its wrapper from the reconciled repository's committed .livespec.jsonc at run time: no declared wrapper runs under the default family wrapper /usr/local/bin/with-livespec-env.sh; a declared wrapper that IS the family wrapper runs under it directly; any other declared wrapper runs nested inside the family wrapper with BEADS_DOLT_PASSWORD unset between the two; an unreadable key refuses the pass rather than falling back. It adds Scenario 377 to exercise the host-timer case.

### Motivation

Work item bd-ib-ft426g ("A reconcile-runs pass mints its GitHub App token through the tenant's committed credential_wrapper") was classified spec-change tier because the ratified clause does not cover the pass, so its implementation cannot be dispatched until this text exists. Plan seat central-credential-service, under throughput-plans-coordinator's assignment. Today orchestrator-image/services/reconcile-runs/reconcile-runs.service fixes its ExecStart as `/usr/local/bin/with-livespec-env.sh -- /usr/bin/python3 .../dispatcher.py reconcile-runs ...`, so the wrapper is decided at unit-install time, not read from the repository. The Dispatcher's bootstrap self-heal re-execs through the committed credential_wrapper only when a required credential is MISSING, and the family wrapper always injects SOME GitHub App pair, so nothing ever corrects a wrong-but-present App. Measured 2026-11-15 during the livespec-ai organization cutover: a bare with-livespec-env.sh projected the PERSONAL GitHub App pair (app 3668528), whose installation reaches 293 thewoolleyman repositories and no livespec-ai repository, while the same mint under the tenant's route C credential_wrapper (orchestrator PR #5361, open as a draft) reached installation 182016479 and 11 livespec-ai repositories. The value-free proof is recorded on livespec-dev-tooling-xowhol at 10:48:58Z. The fix was installed by hand as an override-then-backfill systemd drop-in on vmi3006760 at 10:49:30Z, so the committed unit and the host now disagree until the implementation lands. A timer-driven pass is the case nothing dispatches, so a wrong App there fails silently: merges handed off by a dispatch are never completed for a repository the projected App cannot reach. The three-case wrapper resolution, the nesting with BEADS_DOLT_PASSWORD unset, and the refusal on an unreadable key mirror the ratified tenant-credential-wrapper rule for fleet launchers in §"Provisional fleet launch scripts", so the fleet carries one wrapper-resolution rule rather than two. The unreadable-key refusal is a resolved sub-decision taken from that precedent; revise MAY drop it if it prefers the three cases alone. Scenario number 377 is chosen above every number master (375), the pending proposals (highest 374) and the open v382 revise PR #5354 (376) hold; revise MAY renumber it.

### Proposed Changes

#### contracts.md — §"Self-contained plugin dispatch", the paragraph beginning "The factory's GitHub credential is likewise self-contained and tenant-scoped"

Replace the sentence fragment

> Every automated GitHub operation on the dispatch path — the in-container fresh clones, the in-sandbox PR leg, the merge-poll, the post-merge refresh — MUST authenticate

with

> Every automated GitHub operation on the dispatch path — the in-container fresh clones, the in-sandbox PR leg, the merge-poll, the post-merge refresh, and every GitHub read and write a reconcile-runs pass performs, including completing a handed-off merge — MUST authenticate

Every other sentence of that paragraph is unchanged.

#### contracts.md — new paragraph immediately after that paragraph

> **A reconcile-runs pass mints through the tenant repository's committed wrapper.** A reconcile-runs pass MUST obtain its GitHub App environment, and every other credential it consumes, through the `credential_wrapper` that the reconciled repository's own committed `.livespec.jsonc` declares, the repository the pass is run for (its `--repo`). This holds for every driver of a pass: a `dispatch` preamble, a `loop` tick, an operator invocation, and a host timer such as the `reconcile-runs` systemd unit, which runs on a clock when nothing dispatches. A pass driven by a host timer or an operator MUST resolve the wrapper from that `.livespec.jsonc` when the pass starts, never from a wrapper fixed when the timer unit was installed. A pass that runs inside a `dispatch` or a `loop` tick inherits that Dispatcher process's credential environment, which MUST itself have been resolved by these rules. Resolution has exactly these outcomes:
>
> 1. When the repository's `.livespec.jsonc` declares no `credential_wrapper`, the pass MUST run under the default family wrapper `/usr/local/bin/with-livespec-env.sh`.
> 2. When the declared `credential_wrapper` argv names the default family wrapper itself, the pass MUST run under it directly, without nesting.
> 3. When the declared `credential_wrapper` names any other wrapper, the pass MUST run under that wrapper nested inside the default family wrapper, with `BEADS_DOLT_PASSWORD` unset between the two, so that the tenant wrapper supplies the tenant's own credentials, its GitHub App environment included, while every other variable the family wrapper projects stays in the environment. This is the same nesting the tenant credential wrapper rule of §"Provisional fleet launch scripts" prescribes for a launcher.
> 4. When the `credential_wrapper` key is present but cannot be read as a non-empty argv array, the pass MUST NOT fall back to the default family wrapper. It MUST exit non-zero without any GitHub or ledger write, naming the repository and the cause `credential-wrapper-unreadable`.
>
> A GitHub App environment already present in the pass's ambient environment MUST NOT be taken as evidence that it is the tenant's App: the default family wrapper projects an App pair of its own, so presence alone cannot distinguish the tenant's App from the wrong one, and the missing-credential re-exec of the paragraph above does not correct it. The scenario numbered 377 in `scenarios.md` exercises this paragraph.

#### scenarios.md — new scenario, appended after Scenario 375 (and after Scenario 376 if the v382 revise lands first)

````
## Scenario 377 — A reconcile-runs pass mints its GitHub credential through the tenant repository's committed credential_wrapper, whoever drives it

```gherkin
Feature: a reconcile-runs pass authenticates as the tenant it reconciles
  As the operator of a tenant whose GitHub App is not the family App
  I want every reconcile-runs pass, a timer-driven one included, to mint through the tenant's committed credential_wrapper
  So that a handed-off merge is completed under an App that can reach the tenant's repositories

  Scenario: The host timer runs a pass for a tenant whose credential_wrapper is not the family wrapper
    Given a repository whose committed .livespec.jsonc declares a credential_wrapper naming a tenant wrapper that is not /usr/local/bin/with-livespec-env.sh
    And the default family wrapper projects a GitHub App pair different from the one the tenant wrapper injects
    When the host timer runs a reconcile-runs pass for that repository
    Then the pass runs under the tenant wrapper nested inside the default family wrapper
    And BEADS_DOLT_PASSWORD is unset in the environment the tenant wrapper is started with
    And every installation token the pass mints is minted from the GitHub App environment the tenant wrapper injects

  Scenario: The wrapper is read from the repository when the pass starts, not when the timer was installed
    Given a host timer unit installed while the repository declared no credential_wrapper
    And the repository's committed .livespec.jsonc has since been changed to declare a tenant credential_wrapper
    When the host timer next runs a reconcile-runs pass for that repository
    Then the pass runs under the tenant wrapper nested inside the default family wrapper

  Scenario: A repository that declares no credential_wrapper runs under the default family wrapper
    Given a repository whose committed .livespec.jsonc declares no credential_wrapper
    When the host timer runs a reconcile-runs pass for that repository
    Then the pass runs under /usr/local/bin/with-livespec-env.sh

  Scenario: A declared credential_wrapper that names the default family wrapper runs it directly
    Given a repository whose committed .livespec.jsonc declares credential_wrapper ["/usr/local/bin/with-livespec-env.sh", "--"]
    When the host timer runs a reconcile-runs pass for that repository
    Then the pass runs under /usr/local/bin/with-livespec-env.sh without a second, nested wrapper

  Scenario: An unreadable credential_wrapper refuses the pass rather than falling back
    Given a repository whose committed .livespec.jsonc declares a credential_wrapper that is not a non-empty argv array
    When the host timer runs a reconcile-runs pass for that repository
    Then the pass exits non-zero naming the repository and the cause credential-wrapper-unreadable
    And the pass performs no GitHub write and no ledger write
```
````

#### Revise co-edit

The revise pass that accepts this proposal MUST, in the same revise commit, add one `tests/heading-coverage.json` row for the new scenario heading, carried through `resulting_files[]` with the path spelled `../tests/heading-coverage.json` or edited directly in that commit, with `spec_root: "SPECIFICATION"`, `spec_file: "scenarios.md"`, `test: "TODO"`, `work_item: "bd-ib-ft426g"` and a non-empty `reason` naming the tier the owed test runs at, integration or above, and what it drives: a reconcile-runs pass started the way the host timer starts it, against a stub repository for each of the four resolution outcomes, asserting the wrapper chain, the absence of `BEADS_DOLT_PASSWORD` at the tenant wrapper, the App the minted token came from, and the `credential-wrapper-unreadable` refusal with no write. Add the matching `tests/heading-coverage-debt.json` entry in the same commit, carrying `spec_root: "SPECIFICATION"`, `spec_file: "scenarios.md"`, the heading, `work_item: "bd-ib-ft426g"` and `first_seen` set to the revise date. If the revise renumbers Scenario 377, the row, any debt entry and the contracts.md citation MUST carry the renumbered heading text.
