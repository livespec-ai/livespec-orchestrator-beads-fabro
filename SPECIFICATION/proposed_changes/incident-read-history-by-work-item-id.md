---
topic: incident-read-history-by-work-item-id
author: claude-sonnet-5-5:expedited-incident-response-flag
created_at: 2026-11-20T08:30:00Z
---

## Proposal: The incident authority CLI's read-history reads an incident's whole history from its work-item id alone and reports the closed generation's outstanding obligations as a computed field

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph to contracts.md §"Expedited incident lifecycle", immediately after the paragraph that defines `read-head`, and one scenario. It defines the item-only invocation of `read-history` (the repository and the incident item id, nothing else), its reply (every retained generation of every attempt, oldest first, plus a computed `outstanding` list on the closed generation), the named refusal for an item with no incident authority, and states that the existing full-identity invocation is unchanged.

### Motivation

bd-ib-l4dowx (the carrier for livespec-dev-tooling-bqnzcm.2, plan expedited-incident-response-flag) failed on 2026-11-20 at implement_amendment_route: its Definition of Done asks for a read-history that returns every generation of every attempt and the closed generation with its outstanding list, but the governing heading defines neither an item-only `read-history` invocation nor its JSON reply. Shipped `commands/incident_authority.py` requires `--item`, `--attempt`, `--phase`, `--generation`, `--operation` and `--owner` even for `read-history`, so an operator holding only the work-item id cannot inspect an incident (evidence: incident livespec-dev-tooling-t26bbr, closed at generation 19, whose read-history exposed only the current attempt). The ratified text says only that inspection reports the item's attempts and obligations "by the canonical incident item id". The plugin's `read_history` reader already returns every committed attempt of the whole retained chain, oldest first, and refuses a missing chain with `incident-authority-missing`; what is missing is the invocation and the reply shape. `outstanding` is not a retained attempt field: the completion obligations are computed from forge and ledger evidence by the completion rules, so the reply recomputes it at read time and no authority record stores it. legacy-coordinator-agent and the plan seat decided that this is a real spec change rather than a narrowing of the Definition of Done.

### Proposed Changes

### contracts.md

In `SPECIFICATION/contracts.md`, section `## Expedited incident lifecycle`, insert the following paragraph immediately AFTER the paragraph that begins "The incident authority writer's command-line interface MUST offer an item-only head read, `read-head`":

> The incident authority writer's command-line interface MUST offer an item-only history read: `read-history` invoked with the repository and an incident item id and with no attempt id, incident phase, generation, operation id or owner. It MUST reply `verified` with a `result` carrying the repository, the item id and `generations`, one entry for every retained generation of every attempt of the item's canonical incident authority chain, oldest first, never only the current attempt. Each entry MUST carry that generation's attempt id, incident phase, generation, operation id and owner and the rest of the attempt's canonical record. When the item's head is `closed`, the last entry MUST also carry `outstanding`, the named obligations the completion rules still find outstanding for that generation, an empty list when none; `outstanding` MUST be recomputed from current evidence at every read, MUST NOT be stored in any authority record, and MUST NOT appear on any other entry. A completion evidence source that cannot be read MUST refuse with the named reason `incident-completion-unreadable` and never report an empty `outstanding`. An item with no incident authority genesis, an unknown item and an item that is not an incident MUST each refuse with the named reason `incident-authority-missing`; every other chain fault MUST remain the named refusal the canonical reader returns, and an unreadable authority store MUST refuse with `incident-authority-unavailable`. The reply MUST NOT authorize a side effect. An invocation that names some but not all of the attempt id, incident phase, generation, operation id and owner is a usage error, and the `read-history` invocation that names the full fenced identity MUST behave exactly as it did before this paragraph. Scenario <number assigned at revise> in `scenarios.md` exercises this paragraph.

### scenarios.md

Append this new H2 section after the last ratified scenario. The revise assigns its number and writes the same number into the closing sentence of the paragraph above:

## Scenario <number assigned at revise> — An item-only read-history returns every generation of an incident from its work-item id and computes the closed generation's outstanding list

```gherkin
Feature: An incident's whole history is readable from its work-item id
  As an operator inspecting an incident
  I want read-history to answer from the incident work-item id alone
  So that I can see every attempt and generation without reconstructing a fenced identity

  Scenario: Every generation of every attempt is returned oldest first
    Given an incident item with two attempts that together recorded five generations
    When a caller runs read-history with the repository and the item id and nothing else
    Then the reply's status is verified and the process exits 0
    And the result's generations lists all five generations oldest first, each with its attempt id, phase, generation, operation id and owner
    And authorizes_current_effects is false

  Scenario: A closed incident's last generation carries a computed outstanding list
    Given an incident item whose head is closed
    When a caller runs read-history with the repository and the item id
    Then the last generation carries outstanding, recomputed at read time from current evidence
    And no earlier generation carries outstanding
    And no authority record stores an outstanding list

  Scenario: An item with no incident authority is refused by name
    Given a work item that is unknown or is not an incident
    When a caller runs read-history with the repository and that item id
    Then the reply refuses with the named reason incident-authority-missing
    And the reply's status is refused and the process exits 78

  Scenario: The full-identity invocation is unchanged
    Given an incident item with a current head
    When a caller runs read-history naming the full fenced identity
    Then the reply is the same historical reading it returned before the item-only invocation existed
```
