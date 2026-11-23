---
proposal: orchestrator-factory-admission-the-bypass.md
decision: modify
revised_at: 2026-11-23T18:42:06Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

ACCEPT with one MODIFICATION, as the delegated decision of coordinator ruling R301 (2026-11-23): (1) accepted. (2) Bypass-launcher wording modified to match the code: _dispatcher_credential_env.py checked_credential_env (lines 166-205, policy built only when admission_slot_chooser_registered() is false at lines 183-189) builds its own session-headroom policy only for a launch not admitted through the Dispatcher evaluation, and _weekly_reserve_refusal (lines 208-229) refuses the selected slot below the admission weekly floor naming only the slot env var; the clause now calls the bypass launcher the pre-launch credential check that builds its own session-headroom policy, and Scenario 385 states the target behaviour (names account and floor) as spec-first work. (3) Judge and seat selection has no code home: no implementation exists yet; it stays a stated reader (spec-first) and bd-ib-5vrm34's Definition of Done owns building it. (4) Scenarios numbered 384-387 (highest existing 383) in the repo's Governing-clause plus gherkin form; heading-coverage rows added as spec-first test TODO rows naming the integration tier or above with work_item bd-ib-5vrm34, and the debt register extended.

## Modifications

Reworded the bypass-launcher reader in the new contracts.md paragraph to describe the pre-launch credential check that builds its own session-headroom policy for a launch not admitted through the Dispatcher evaluation; numbered the four scenarios 384-387 and rewrote them in Governing-clause plus gherkin form (Scenario 385 uses the pre-launch credential check as its When).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-23T18:41:33Z
verdict: NO BLOCKERS
proposal_stem: orchestrator-factory-admission-the-bypass
content_digest: 8b9cb22d3e6c367705708d99050e9a8a4a3e7ce0319aa8c5c5e24fb751f33b56
