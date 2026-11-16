---
topic: central-factory-selection-consumer
author: claude-opus-5-5:central-credential-service
created_at: 2026-11-16T07:37:21Z
---

## Proposal: A dispatcher MAY take its Claude slot from the central factory selection instead of ranking slots locally

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

dispatcher.claude_credential_policy gains a committed `selection` field: `local-ranking` (today's whole-pool headroom ranking, and the default) or `central-factory-selection`. Under `central-factory-selection` the Dispatcher takes the slot named by the central account rotation's FACTORY selection record (livespec-overseer contracts.md "Factory selection record") instead of ranking the pool. It still assesses that one slot's headroom, never chooses another slot locally, and leaves covered candidates without a credential when the record is absent, stale, names no account, or names a slot that is not declared and injected. The account-selection process's INTERACTIVE selection remains unread in every mode.

### Motivation

Local whole-pool ranking (Scenario 278) never sees the protection floors the central account rotation keeps. Between 2026-10-31 and 2026-11-14 it chose the anthropic-0 slot 1520 times, up to 99% weekly utilization, past that account's 10% protection floor and into the maintainer's paid extra usage (livespec-overseer overseer-kzmmn7). livespec-overseer's plan central-credential-service (epic overseer-iyfjbo, line 6; carrier overseer-shojan) therefore makes the central rotation decide one factory account per pass, under the same eligibility, floors, reserve and ranking as the interactive decision, never the interactive account, and publish it as a factory selection record on every listed host (livespec-overseer PR #3112). Each dispatcher must read that record in place of local ranking, so one central decision protects every account for every factory. The mode is a committed field defaulting to today's behaviour, so no dispatcher refuses before the publisher is deployed on its host. A repository flips only once the record is being published there, confirming the reader before the writer.

### Proposed Changes

1. In SPECIFICATION/contracts.md, in the paragraph beginning **The dispatcher declares its Claude credential policy.**, append:

The policy MAY carry `selection`, whose value MUST be exactly `local-ranking` or `central-factory-selection`; when it is absent, `local-ranking` applies. Under `local-ranking`, the slot is chosen by the whole-pool ranking of the "Admission filters candidates by projected Claude session headroom" paragraph, unchanged. `central-factory-selection` MUST be accepted only under mode `numbered-slots`; any other combination MUST be a configuration refusal naming `dispatcher.claude_credential_policy` and the defect. The policy MAY also carry `central_selection_max_age_minutes`, an integer from 1 through 1440 inclusive, default 60.

2. In the same file, insert after that paragraph:

**Under `central-factory-selection`, the central factory selection names the slot.** The CENTRAL FACTORY SELECTION RECORD is the identity-only file `factory-selected-account.json` that livespec-overseer's account rotation publishes, and that its enrolled-host delivery service writes onto every listed host, in the dispatching user's `~/.local/state/caam-usage-rotate/` directory (livespec-overseer contracts.md "Factory selection record"). Its fields are `profile`, `account_uuid`, `written_at` and `reason`. Under `central-factory-selection`, at each admission evaluation the Dispatcher MUST read that record and derive the NAMED SLOT `CLAUDE_CODE_OAUTH_TOKEN__<PROFILE>`, where `<PROFILE>` is `profile` upper-cased with each hyphen replaced by an underscore. The named slot is the ONLY pool slot for that evaluation: the Dispatcher MUST assess it under the headroom paragraph exactly as any pool slot, including the floor, the seven-day skip, the seven-day floor skip and the projection skip. It MUST project it when it qualifies, and MUST NOT assess, rank or choose any other slot. When the record is absent or unreadable, does not parse, names no account (its `profile` is `null`), was written more than `central_selection_max_age_minutes` before the evaluation, or names a slot that the policy does not declare or that the credential wrapper does not inject non-empty, covered candidates MUST be skipped with a `no-central-factory-selection` skip. That skip MUST carry the record's `reason`, or which of those conditions held, and has exactly the semantics of a floor skip: it is ephemeral and candidate-local, per-node selection continues to an uncovered fallback, an emptied admission-required node leaves a ready item ready without a claim, and reevaluation follows the existing scheduling rule. The named slot failing its own headroom assessment MUST likewise skip covered candidates and MUST NOT cause another slot to be chosen. The credential-usability probe, Worker credential projection and the host judgement MUST use the slot this paragraph chooses, and MUST refuse rather than fall back when it is unusable. The journal record of each such evaluation MUST name the record's `profile`, its `written_at`, the derived slot's opaque credential identity, and the outcome. Every read of the account-selection process's INTERACTIVE published selection remains forbidden in every mode; the central factory selection record is a different record and is the only one this paragraph reads.

3. In the "Admission filters candidates by projected Claude session headroom" paragraph, replace the sentence that begins "An account-selection process outside the Dispatcher continues to own which account INTERACTIVE spend uses;" with:

An account-selection process outside the Dispatcher continues to own which account INTERACTIVE spend uses. That selection MUST NOT change which pool slot a factory dispatch projects, and the Dispatcher MUST NOT read that process's interactive selection, trigger or readings to choose a slot. Under `selection: central-factory-selection` the Dispatcher reads only that process's separate central factory selection record, as the paragraph "Under `central-factory-selection`, the central factory selection names the slot" defines. Under `local-ranking` the factory takes its own allocation within the pool.

4. In SPECIFICATION/scenarios.md, add after Scenario 376 (numbered by the repository's convention):

## Scenario 377 — A central-factory-selection dispatcher projects only the centrally selected slot

```gherkin
Feature: Factory credential from the central factory selection
  As an operator whose accounts are protected by the central account rotation's floors
  I want every factory dispatch to use the account the central rotation selected for factories
  So that no local ranking can spend an account past the floor the central rotation keeps

  Background:
    Given dispatcher.claude_credential_policy declares mode numbered-slots with slots CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_4 and CLAUDE_CODE_OAUTH_TOKEN__ANTHROPIC_5 and selection central-factory-selection
    And both declared slots are injected non-empty
    And an item whose implement node's candidate is covered by the admission session-headroom clause

  Scenario: The named slot qualifies and is the only slot assessed
    Given the central factory selection record names profile anthropic-5, written 5 minutes ago
    And slot ANTHROPIC_5 qualifies under the headroom paragraph
    And slot ANTHROPIC_4 reads more headroom than slot ANTHROPIC_5
    When the Dispatcher evaluates admission
    Then slot ANTHROPIC_5 is projected
    And slot ANTHROPIC_4 is neither assessed nor projected

  Scenario: A record naming no account leaves covered candidates without a credential
    Given the central factory selection record names no account with reason "no account qualifies"
    When the Dispatcher evaluates admission
    Then covered candidates are skipped with a no-central-factory-selection skip carrying that reason
    And the item remains ready without a claim
    And no declared slot is assessed or projected

  Scenario: A stale record is not followed
    Given dispatcher.claude_credential_policy central_selection_max_age_minutes is 60
    And the central factory selection record names profile anthropic-5, written 90 minutes ago
    When the Dispatcher evaluates admission
    Then covered candidates are skipped with a no-central-factory-selection skip naming the stale record

  Scenario: A named slot that fails its own headroom does not move the dispatch to another slot
    Given the central factory selection record names profile anthropic-5, written 5 minutes ago
    And slot ANTHROPIC_5's five-hour remaining headroom is below the floor
    And slot ANTHROPIC_4 qualifies
    When the Dispatcher evaluates admission
    Then covered candidates are skipped by a floor skip
    And slot ANTHROPIC_4 is neither assessed nor projected

  Scenario: A covered primary with an uncovered fallback continues when no central selection is usable
    Given the central factory selection record is absent
    And an admission-required node offers a claude-acp primary and a codex-acp fallback
    When the Dispatcher evaluates admission
    Then selection continues to the codex-acp fallback

  Scenario: The interactive selection is never read
    Given the account-selection process's interactive published selection names anthropic-4
    And the central factory selection record names profile anthropic-5, written 5 minutes ago
    When the Dispatcher evaluates admission
    Then slot ANTHROPIC_5 is projected
    And the Dispatcher did not read the interactive published selection

  Scenario: Absent selection keeps local ranking
    Given dispatcher.claude_credential_policy declares mode numbered-slots with no selection
    When the Dispatcher evaluates admission
    Then the slot is chosen by the whole-pool ranking of Scenario 278
```
