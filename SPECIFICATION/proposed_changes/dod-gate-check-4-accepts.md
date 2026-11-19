---
topic: dod-gate-check-4-accepts
author: claude-sonnet-5-5
created_at: 2026-11-19T07:52:24Z
---

## Proposal: dod_gate check 4 admits one reading and accepts a recorded internal ruling

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

dod_gate check 4 (coherence) admits exactly one reading, and has exactly one exception. The reading: an assertion whose subject the referenced heading's whole section neither states nor derives is incoherent, even when its subject is repository state an engineer could observe without the specification, and a `kind: unstated` governing-heading verdict is never licence to pass such an assertion. The exception: when the item's newest `livespec-spec-change-tier` record records tier `none` because the item's behaviour is internal, and names the References heading as the nearest heading, check 4 accepts that heading as coherent for the item's assertions, the heading being the nearest topic rather than a governing clause. Without such a record check 4 refuses exactly as today.

### Motivation

Under the fleet rule SPEC-IS-NOT-THE-DEFAULT (maintainer ruling 2026-11-16), internal behaviour (code, tests, roles, tools) ships without a spec heading. Check 4 refuses every internal item whose only citable heading does not govern its assertions, by construction: the filer can name only the nearest topic and check 4 then refuses that citation. Measured 2026-11-19 on livespec-dev-tooling-y53v27 (otel_receiver restart-pending marker), refused at dod_gate check 4, run 01M7S7S3V5WP: its References line names `## Fabro factory host provisioning`, which says nothing about the otel_receiver, and no SPECIFICATION heading in that repository does. Counted the same day in the livespec-dev-tooling tenant under a strict reading: of 180 ready items 111 do not govern and 3 carry no References line; of 156 pending-approval items 96 do not govern, 4 carry none and 2 name a heading that does not exist, so 207 of 336 (62%) would be refused as filed (some are a repairable partial-coverage defect, the rest have no clause to cite). The second half is bd-ib-thudl2: measured 2026-10-31 on li-cyucz7, the SAME subject, the SAME candidate and the SAME rubric returned opposite check-4 verdicts, a hand screen PASS (governing-heading kind `unstated`; it reasoned both assertions were repository state an engineer can check without the spec) and a launch preflight FAIL minutes later (it read every nested H3 of the referenced section and found no governing text). The current rubric licenses both readings, which breaks Scenario 239's promise that a pre-dispatch pass is not refused in-run on unchanged bytes. The two defects meet in one sentence of one rule, so one proposal settles both. Work items: bd-ib-g7g73z (the exception) and bd-ib-thudl2 (the single reading), implemented after revise by editing the dod_gate node's prompt file, whose check 4 every host taking embeds unchanged (Scenario 239), and the check-4 acceptance path. Ruling source for the exception: legacy-coordinator-agent, 2026-11-19, on throughput-plans-coordinator's recommendation. In-flight survey: open spec PR #5394 (dod-preflight-takes-the-governing-heading-judgement) and the pending topics a-host-codex-definition-of and make-the-definition-of-done touch the Definition-of-Done judgement but not check-4 coherence (make-the-definition-of-done states its coherence edit was dropped and would be proposed separately: this is that proposal); relationship: align with all of them.

### Proposed Changes

Two edits: one to `SPECIFICATION/contracts.md` and one to `SPECIFICATION/scenarios.md`. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit. The recorded tier values are `spec-change` and `none`; "internal" is the rubric's name for the class whose tier is `none` (§"Dispatcher admission, WIP cap, and post-merge acceptance" → "An autonomy tier is assigned"), and the edit below uses the recorded value.

**Edit 1 - `contracts.md`, §"Dispatcher admission, WIP cap, and post-merge acceptance", the paragraph beginning `**\`dod_gate\`.**`.** Immediately after the sentence that ends "could not recognise as satisfied or unsatisfied from the referenced scenario is incoherent." insert:

> Coherence admits ONE reading. A referenced heading means its whole section: the named H2 together with every nested heading beneath it, up to the next H2 of that file. An assertion whose subject that whole section neither states nor derives is incoherent, even when its subject is repository state an engineer could observe without the specification, and the node MUST report it as a coherence finding. A governing-heading verdict of kind `unstated` (§"Effective acceptance criteria" → "The spec-stated judgement is one shared component") reports that no heading governs the assertion; it MUST NOT be read as licence to pass the assertion, and it bears on coherence in no other way. The one exception is a recorded internal ruling. When the newest `livespec-spec-change-tier` record of the item is still current under that component's reuse rules, records tier `none`, and names the heading on the item's `References:` line as its `generalization-target` (or, for a record written by the `release-spec-tier` valve, as the heading its attestation names), check 4 MUST accept that reference as coherent for every assertion of the item: the cited heading is then the nearest topic, not a governing clause, and no coherence finding is raised on the ground that it does not govern. A record of tier `spec-change`, a `livespec-spec-change-tier-unavailable` record, a record no longer current, or the absence of any record leaves check 4 exactly as the preceding sentences state; a newer record of another tier replaces an older `none` record. The exception changes check 4 only: the node's other checks, the reference-resolution check and every existing refusal remedy are graded as before, and a reference that does not resolve to an H2 is refused whatever the item's ledger records. Every host taking of the judgement (repository preflight, pre-admission, pre-dispatch) and the node itself MUST apply this reading and this exception identically. Scenario 239 in `scenarios.md` exercises this paragraph.

**Edit 2 - `scenarios.md`, §"Scenario 239 - Every taking of the Definition-of-Done judgement grades one subject by one rubric".** Append these scenarios to the end of that scenario's Gherkin block, inside the same fenced block, leaving the heading unchanged:

```gherkin
  Scenario Outline: A recorded internal ruling makes the nearest cited heading coherent for every taking
    Given an item whose References line names heading H and whose newest livespec-spec-change-tier record is still current, records tier none, and names H as its generalization-target
    And no part of H's whole section states or derives the item's assertions
    When the <taking> judgement is taken
    Then check 4 reports no coherence finding for the item's assertions on the ground that H does not govern them
    And a reference line naming a heading that does not resolve to an H2 is still refused

    Examples:
      | taking                   |
      | repository preflight     |
      | pre-admission            |
      | pre-dispatch             |

  Scenario: Without a recorded internal ruling a non-governing reference is still incoherent
    Given an item whose References line names heading H and whose ledger carries no livespec-spec-change-tier record of tier none naming H
    And no part of H's whole section states or derives the item's assertions
    When the pre-dispatch judgement is taken
    Then check 4 reports the assertions incoherent and names the heading that governs them when the spec-stated judgement returns one
    And the same finding is reported when the item's newest record is of tier spec-change or is unavailable

  Scenario: A governing-heading verdict of kind unstated is not licence to pass an assertion
    Given an item with no recorded internal ruling and an assertion naming repository state an engineer could check without the specification
    And the assertion's governing-heading verdict is of kind unstated and H's whole section, nested headings included, neither states nor derives it
    When the repository preflight judgement and the pre-dispatch judgement are each taken on the unchanged bytes
    Then both report the assertion incoherent
    And neither passes it on the ground that the verdict is unstated

  Scenario: A newer record of another tier replaces an older internal ruling
    Given an item whose older record is tier none naming H and whose newer record is tier spec-change
    When the pre-dispatch judgement is taken
    Then check 4 treats the item as having no recorded internal ruling
```

After revise, the work items bd-ib-g7g73z and bd-ib-thudl2 implement the edit in the dod_gate node's prompt file (check 4) and the check-4 acceptance path; the prompt file's bytes are what every host taking embeds (Scenario 239).
