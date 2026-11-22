---
topic: fleet-declared-factory-slot-pool
author: codex
created_at: 2026-11-22T12:30:08Z
---

## Proposal: A fleet-owned declaration supplies the factory Claude slot pool

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Replace the ten repository-local copies of the factory Claude slot allow-list with one non-secret, fleet-owned declaration that every Dispatcher reads from the centrally delivered factory credential state. The central-factory selection remains a per-admission choice of one slot from that declared set; it does not become the declaration itself.

### Motivation

The current dispatcher.claude_credential_policy.slots array is copied in all ten fleet repositories, so changing the factory pool requires ten reviewed configuration pull requests and previously also required changing a literal-tuple test. The pool is fleet-wide state, whereas central-factory-selection is an ephemeral per-admission choice. This proposal records the source-of-truth design before implementation; it neither opens a lane tonight nor changes the 15 percent narrowing trigger.

### Proposed Changes

## Candidate designs

1. **fleet-level declaration.** A fleet-owned, identity-only factory credential-pool record declares the permitted numbered environment-variable names once. The livespec-overseer delivery service writes that record to every listed factory host; every Dispatcher reads it at credential-policy resolution. This is the chosen design.

2. **central-factory-selection carrying the pool.** Extend the existing central-factory-selection record with the declared pool. This is rejected: that record answers which one already-declared slot is selected for one admission evaluation, and may be absent, stale, or name no account. Conflating it with the durable allow-list would blur the contract between declared eligibility and a transient selection, and would make local-ranking consumers depend on a selection record they do not use.

3. **generated per-repository file.** Generate the policy slots into each repository's .livespec.jsonc. This is rejected: it keeps ten committed copies as deployment artifacts, still creates ten repository changes per pool change, and adds generator/version skew without giving dispatchers a direct common source.

## Chosen design

Under **## Dispatcher policy settings**, replace the repository-local numbered `slots` array with a committed declaration that the numbered-slot policy uses the fleet-level declaration. The declaration is one identity-only, non-secret factory credential-pool record, owned and atomically published by the fleet account-rotation service beside the existing central factory selection record. It contains only distinct `CLAUDE_CODE_OAUTH_TOKEN__<SLOT>` variable names and a monotonically identifiable revision; it MUST contain neither credentials nor credential-derived data. Every Dispatcher MUST read the same delivered record when resolving a numbered-slot policy. A missing, malformed, stale, or unreadable record MUST be a configuration refusal before claim, rather than silently falling back to repository-local slots, the unnumbered token, or an undeclared numbered variable.

`selection: central-factory-selection` remains unchanged in purpose: at each admission it names one slot from the fleet-declared pool, and the Dispatcher MUST reject a selected slot that is outside that pool. `local-ranking` evaluates the fleet-declared pool. The ratification must add a scenario beside Scenario 378 that proves both selections consume the same delivered declared pool and that a central selection outside it refuses.

## Tier and follow-on work

This is **spec-change tier**: it changes where the contract-bearing factory slot allow-list is declared, how every Dispatcher obtains it, and the configuration-refusal semantics. This file is the propose-change for **## Dispatcher policy settings**. After ratification, file these implementation work items, each explicitly referencing **## Dispatcher policy settings**:

- **Deliver the fleet factory credential-pool record** in livespec-overseer: own, validate, revision, and atomically deliver the identity-only pool record to every listed factory host.
- **Resolve the factory slot pool from the fleet declaration** in livespec-orchestrator-beads-fabro: make the policy loader and every credential consumer read that record; preserve central-factory-selection as a one-slot choice within it; add the Scenario 378 coverage.
- **Migrate fleet dispatcher configuration to the declaration** across all ten repositories: remove the copied `slots` arrays only after the shared record and reader are deployed, while retaining the local selection mode and other repository policy settings.

## Delivery and test migration

A pool change is made once at the fleet-owned record. Its owner validates and publishes a new revision, and the delivery service atomically writes that revision to **all ten repositories**' listed factory hosts. Each Dispatcher reads the delivered revision on its normal policy-resolution path, so a pool widening or narrowing reaches every repository without ten configuration pull requests. The rollout item must define the record-version compatibility order: publish reader support first, then the fleet declaration, then remove repository arrays; rollback keeps the last valid delivered record.

The existing committed **literal-tuple pin test** must be deleted or converted into a source-of-truth invariant test. It MUST stop pinning literal slot names from this repository. Its successor verifies that this repository declares the fleet source rather than a `slots` array, and that the policy reader uses a fixture fleet record; fleet-record contents are tested in the owner repository.

The ratified contract change MUST update `SPECIFICATION/contracts.md` under **## Dispatcher policy settings**, add the stated Scenario 378-adjacent behavior in `SPECIFICATION/scenarios.md`, and update `tests/heading-coverage.json` with the scenario's exercising test when the H2 is added.
