---
topic: numbered-slot-dispatcher-refuses-without-a-declared-slot
author: claude-opus-5-5
created_at: 2026-11-15T05:28:27Z
---

## Proposal: A numbered-slot dispatcher declares its Claude slots and never falls back to the unnumbered credential

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Today the factory credential pool silently becomes the unnumbered CLAUDE_CODE_OAUTH_TOKEN whenever no numbered slot is injected, so a dispatcher whose numbered slots go missing keeps dispatching on a credential nobody chose for it. This proposal adds a committed, non-secret dispatcher.claude_credential_policy with mode numbered-slots or legacy-independent. Under numbered-slots the pool is only the declared, non-empty, injected slots; missing, empty or undeclared slots, or a missing policy, refuse before claim, and no consumer substitutes the unnumbered credential. The explicit legacy-independent mode keeps today's behaviour for independently configured adopters.

### Motivation

Plan epic overseer-iyfjbo (central credential service), coordinator-approved cross-repo change plan v4, Wave 1 entries R02 (SPECIFICATION/scenarios.md) and R10 (SPECIFICATION/contracts.md), filed as one propose-change because R01 (the fail-closed numbered-slot selector in commands/_dispatcher_factory_account_selector.py) implements whatever this revise ratifies. The applicability rule below is the normative proposal R01 carries for R02/R10. livespec core has ratified the fleet-secrets change these entries sit beside (livespec v248/v249, livespec#3252: Parameter Store is the single canonical source, /usr/local/bin/with-livespec-env.sh keeps its name and calling convention and changes backend only at each host's conversion, no dual-backend fallback). No host has converted. The dispatcher rule here is independent of any conversion and is not a deployment receipt. Two gates sit outside this specification and are not decided by it: the D03 bare-token consumer census (dolt-server still copies the unnumbered CLAUDE_CODE_OAUTH_TOKEN from the wrapper, so ratifying this does not authorize deleting that token anywhere), and R01's per-dispatcher slot census release gate, which must pass before any release or fleet pin promotion of the implementation. R10 asks that the admission clause stop treating the unnumbered credential as a pool slot in the governed numbered-slot fleet mode, with a named refusal before claim or projection, while preserving independent-adopter modes explicitly. The policy key name dispatcher.claude_credential_policy is chosen here because the plan names the declaration but not its key; revise MAY rename it.

### Proposed Changes

#### contracts.md — §"Admission filters candidates by projected Claude session headroom"

Replace the sentence

> The factory credential pool is every non-empty `CLAUDE_CODE_OAUTH_TOKEN__<SLOT>` credential the dispatch target's credential wrapper injects into the Dispatcher's environment, and the unnumbered `CLAUDE_CODE_OAUTH_TOKEN` is the sole pool slot only when no numbered slot is injected.

with

> The factory credential pool is governed by the dispatcher's Claude credential policy, `dispatcher.claude_credential_policy`, defined in the paragraph "The dispatcher declares its Claude credential policy" below. Under the `numbered-slots` policy, the pool is every slot the policy declares whose `CLAUDE_CODE_OAUTH_TOKEN__<SLOT>` variable the dispatch target's credential wrapper injects into the Dispatcher's environment non-empty. A numbered variable the policy does not declare is not a pool slot, and the unnumbered `CLAUDE_CODE_OAUTH_TOKEN` is never a pool slot, whether or not it is present. Under the `legacy-independent` policy, the pool is every non-empty `CLAUDE_CODE_OAUTH_TOKEN__<SLOT>` credential the wrapper injects, and the unnumbered `CLAUDE_CODE_OAUTH_TOKEN` is the sole pool slot only when no numbered slot is injected.

Every other sentence of that paragraph is unchanged.

#### contracts.md — new paragraph immediately after that paragraph

> **The dispatcher declares its Claude credential policy.** `dispatcher.claude_credential_policy` is a committed-only, non-secret object. It is NOT declared API-configurable, and is therefore committed-only per §"Orchestrator-owned attention facts" → "The declared-API-configurable class". Its `mode` MUST be exactly one of `numbered-slots` or `legacy-independent`. Under `numbered-slots`, its `slots` MUST be a non-empty array of distinct environment variable names, each matching `^CLAUDE_CODE_OAUTH_TOKEN__[A-Z0-9_]+$`; under `legacy-independent`, `slots` MUST be absent. The policy MUST carry variable names only, never a credential value, a digest of one, or any other secret-derived figure.
>
> The `numbered-slots` policy applies when, and only when, the declared mode is `numbered-slots` AND the operation requires a Claude Code OAuth credential. Those operations are: admission of a covered candidate under the paragraph above, a credential-usability probe of such a candidate, Worker credential projection of the chosen slot, and the host Definition-of-Done judgement's Claude model. The policy applies whatever secret backend the credential wrapper reads and whichever variables happen to be present. An operation that requires no Claude Code OAuth credential, including admission and dispatch of a candidate the paragraph above does not cover, MUST NOT acquire that requirement from the policy.
>
> When an operation that requires a Claude Code OAuth credential runs and `dispatcher.claude_credential_policy` is absent or invalid, the Dispatcher MUST refuse it before any claim as a configuration refusal naming the key and the defect. It MUST NOT infer `legacy-independent` from the absence of a policy or from the absence of numbered slots.
>
> Under `numbered-slots`, when the pool holds no slot because every declared slot is absent or empty, the Dispatcher MUST refuse the dispatch before any claim with a named `no-declared-slot-injected` refusal. The refusal MUST name each declared slot and whether it was absent or empty, and MUST NOT carry any credential value. When the pool holds slots but none qualifies, covered candidates are skipped exactly as the paragraph above prescribes. In neither case MAY admission, a credential-usability probe, Worker credential projection or the host judgement substitute the unnumbered `CLAUDE_CODE_OAUTH_TOKEN` or any undeclared numbered variable. Every consumer of the admitted credential in one dispatch, the probe, the projection and the judgement alike, MUST use the slot admission chose. When that slot is absent or empty at a downstream consumer, that consumer MUST refuse before any further claim or launch rather than choose another credential.
>
> A fleet member's dispatcher MUST declare `numbered-slots`. `legacy-independent` is an explicit compatibility mode for an independently configured adopter and MUST NOT serve as a fleet fallback. Declaring either policy does not authorize removing the unnumbered credential from any credential wrapper, which consumers outside the Dispatcher MAY still read. The scenario headed "a numbered-slot dispatcher refuses rather than fall back to the unnumbered Claude credential" in `scenarios.md` exercises this paragraph.

#### scenarios.md — new scenario heading

Add, after Scenario 288:

````
## Scenario: a numbered-slot dispatcher refuses rather than fall back to the unnumbered Claude credential

```gherkin
Feature: A fleet dispatcher's Claude credential is always a declared numbered slot
  As an operator running Claude-routed factory nodes
  I want a dispatcher with missing or unusable numbered slots to refuse
  So that no dispatch ever runs on a credential nobody chose for the factory

  Scenario: No declared slot injected refuses even when the unnumbered credential is present
    Given dispatcher.claude_credential_policy declares mode numbered-slots with slots CLAUDE_CODE_OAUTH_TOKEN__A and CLAUDE_CODE_OAUTH_TOKEN__B
    And neither declared slot variable is present in the Dispatcher's environment
    And the unnumbered CLAUDE_CODE_OAUTH_TOKEN is present
    When the Dispatcher evaluates admission for an item with a covered claude-acp candidate
    Then the dispatch is refused before any claim with a no-declared-slot-injected refusal naming both declared slots as absent
    And no claim is taken, no factory run is created and no credential is projected

  Scenario: An empty declared slot is not a pool slot
    Given dispatcher.claude_credential_policy declares mode numbered-slots with slot CLAUDE_CODE_OAUTH_TOKEN__A
    And CLAUDE_CODE_OAUTH_TOKEN__A is present but empty
    And the unnumbered CLAUDE_CODE_OAUTH_TOKEN is present
    When the Dispatcher evaluates admission for an item with a covered claude-acp candidate
    Then the dispatch is refused before any claim with a no-declared-slot-injected refusal naming CLAUDE_CODE_OAUTH_TOKEN__A as empty

  Scenario: An undeclared numbered variable cannot satisfy the policy
    Given dispatcher.claude_credential_policy declares mode numbered-slots with slot CLAUDE_CODE_OAUTH_TOKEN__A
    And CLAUDE_CODE_OAUTH_TOKEN__A is absent
    And an undeclared CLAUDE_CODE_OAUTH_TOKEN__C is present and non-empty
    When the Dispatcher evaluates admission for an item with a covered claude-acp candidate
    Then the dispatch is refused before any claim with a no-declared-slot-injected refusal
    And CLAUDE_CODE_OAUTH_TOKEN__C is neither assessed nor projected

  Scenario: No qualifying slot skips covered candidates without touching the unnumbered credential
    Given dispatcher.session_headroom_floor_percent is 20
    And dispatcher.claude_credential_policy declares mode numbered-slots with slot CLAUDE_CODE_OAUTH_TOKEN__A
    And CLAUDE_CODE_OAUTH_TOKEN__A is present and its five-hour remaining headroom is below the floor
    And the unnumbered CLAUDE_CODE_OAUTH_TOKEN is present
    When the Dispatcher evaluates admission for an item whose only admission-required candidates are covered
    Then the covered candidates are skipped by a floor skip and the item remains ready without a claim
    And the unnumbered credential is neither assessed nor projected

  Scenario: A downstream consumer refuses when the admitted slot is gone
    Given dispatcher.claude_credential_policy declares mode numbered-slots with slots CLAUDE_CODE_OAUTH_TOKEN__A and CLAUDE_CODE_OAUTH_TOKEN__B
    And admission chose CLAUDE_CODE_OAUTH_TOKEN__A for a dispatch
    And CLAUDE_CODE_OAUTH_TOKEN__A is absent when Worker credential projection runs
    When the Dispatcher projects the dispatch's Claude credential
    Then the projection refuses and no factory run is launched
    And neither CLAUDE_CODE_OAUTH_TOKEN__B nor the unnumbered credential is projected

  Scenario: A missing policy refuses instead of inferring legacy-independent
    Given dispatcher.claude_credential_policy is absent
    And no numbered slot is injected and the unnumbered CLAUDE_CODE_OAUTH_TOKEN is present
    When the Dispatcher evaluates admission for an item with a covered claude-acp candidate
    Then the dispatch is refused before any claim with a configuration refusal naming dispatcher.claude_credential_policy

  Scenario: The explicit legacy-independent policy keeps the unnumbered credential as the sole slot
    Given dispatcher.claude_credential_policy declares mode legacy-independent
    And no numbered slot is injected and the unnumbered CLAUDE_CODE_OAUTH_TOKEN is present
    When the Dispatcher evaluates admission for an item with a covered claude-acp candidate
    Then the unnumbered credential is the sole pool slot and is assessed under the headroom paragraph

  Scenario: A candidate that needs no Claude credential is unaffected by the policy
    Given dispatcher.claude_credential_policy declares mode numbered-slots and no declared slot is injected
    And every admission-required node of an item offers only codex-acp candidates
    When the Dispatcher evaluates admission for the item
    Then no no-declared-slot-injected refusal applies and admission proceeds under its other conditions
```
````

Revise MUST add a `tests/heading-coverage.json` entry for this new heading in the same change (the `test` MAY be `"TODO"` with a reason naming the R01 implementation work), per this repository's revise co-edit discipline.


## Proposal: Under the numbered-slots policy the host judgement does not run rather than fall back to the unnumbered credential

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The pre-admission and pre-dispatch Definition-of-Done judgements currently fall back to the unnumbered Claude credential, with a stderr line, when no pool slot qualifies or no numbered slot is injected. This proposal keeps that fallback only under the explicit legacy-independent policy. Under numbered-slots the judgement does not run, says so on stderr naming the reason, and is recorded and routed as any judgement that cannot be run. The Scenario 174 fallback outline is split to match.

### Motivation

Plan epic overseer-iyfjbo (central credential service), coordinator-approved cross-repo change plan v4, Wave 1 entries R02 (SPECIFICATION/scenarios.md) and R10 (SPECIFICATION/contracts.md), filed as one propose-change because R01 (the fail-closed numbered-slot selector in commands/_dispatcher_factory_account_selector.py) implements whatever this revise ratifies. The applicability rule below is the normative proposal R01 carries for R02/R10. livespec core has ratified the fleet-secrets change these entries sit beside (livespec v248/v249, livespec#3252: Parameter Store is the single canonical source, /usr/local/bin/with-livespec-env.sh keeps its name and calling convention and changes backend only at each host's conversion, no dual-backend fallback). No host has converted. The dispatcher rule here is independent of any conversion and is not a deployment receipt. Two gates sit outside this specification and are not decided by it: the D03 bare-token consumer census (dolt-server still copies the unnumbered CLAUDE_CODE_OAUTH_TOKEN from the wrapper, so ratifying this does not authorize deleting that token anywhere), and R01's per-dispatcher slot census release gate, which must pass before any release or fleet pin promotion of the implementation. R10 asks that the host-judgement clause be revised to the same no-usable-numbered-slot rule as admission. R02 asks that the fallback scenarios be revised so that the governed numbered-slot fleet mode produces a named did-not-run rather than an unnumbered-token fallback, preserving the independent-adopter mode.

### Proposed Changes

#### contracts.md — the "Judged before admission" paragraph

Replace

> it MUST authenticate with the Claude subscription credential the Dispatcher selects for a dispatch it would launch at that moment, which is the pool slot the Dispatcher's admission would choose for a dispatch at that moment under the "Admission filters candidates by projected Claude session headroom" paragraph, and, when no pool slot qualifies or no numbered slot is injected, the unnumbered credential. It MUST NOT read the account-selection process's selection to choose the credential. When it falls back to the unnumbered credential, it MUST say so on stderr, naming the reason.

with

> it MUST authenticate with the Claude subscription credential the Dispatcher selects for a dispatch it would launch at that moment, which is the pool slot the Dispatcher's admission would choose for a dispatch at that moment under the "Admission filters candidates by projected Claude session headroom" paragraph. Under the `legacy-independent` policy of `dispatcher.claude_credential_policy`, when no pool slot qualifies or no numbered slot is injected, it MUST authenticate with the unnumbered credential, and when it does so it MUST say so on stderr, naming the reason. Under the `numbered-slots` policy, when no declared slot is injected or no pool slot qualifies, the judgement MUST NOT run its Claude model and MUST NOT authenticate with the unnumbered credential or with any undeclared numbered variable; it MUST say on stderr that it did not run, naming the reason, and it is then a judgement that cannot be run, recorded and routed exactly as this paragraph and the "Judged again before dispatch" paragraph record and route one. When the policy is absent or invalid, the judgement MUST NOT run, and its stderr line and did-not-run record MUST name the configuration defect. It MUST NOT read the account-selection process's selection to choose the credential.

The trailing sentence "The same rule governs the pre-dispatch judgement of the paragraph that follows." is unchanged.

#### scenarios.md — Scenario 174

Replace the Scenario Outline "The judgement falls back to the unnumbered credential and says so" and its Examples with:

```gherkin
  Scenario Outline: Under the legacy-independent policy the judgement falls back to the unnumbered credential and says so
    Given dispatcher.claude_credential_policy declares mode legacy-independent
    And <selection state>
    And the unnumbered Claude credential is present in the environment
    When the <phase> judgement runs its Claude model on the host
    Then the judge is started with the unnumbered Claude credential
    And one stderr line names that fallback and its reason

    Examples:
      | phase         | selection state              |
      | pre-admission | no numbered slot is injected |
      | pre-dispatch  | no numbered slot is injected |
      | pre-admission | no pool slot qualifies       |
      | pre-dispatch  | no pool slot qualifies       |

  Scenario Outline: Under the numbered-slots policy the judgement does not run rather than fall back
    Given dispatcher.claude_credential_policy declares mode numbered-slots
    And <selection state>
    And the unnumbered Claude credential is present in the environment
    When the <phase> judgement would run its Claude model on the host
    Then no judge is started and the unnumbered Claude credential is not used
    And one stderr line says the judgement did not run and names the reason
    And the item records that the <phase> judgement did not run and why

    Examples:
      | phase         | selection state              |
      | pre-admission | no declared slot is injected |
      | pre-dispatch  | no declared slot is injected |
      | pre-admission | no pool slot qualifies       |
      | pre-dispatch  | no pool slot qualifies       |
```

Scenario 174's heading is unchanged, so this edit MUST NOT add or remove any `tests/heading-coverage.json` entry.

