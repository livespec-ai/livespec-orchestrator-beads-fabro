---
proposal: central-factory-selection-consumer.md
decision: modify
revised_at: 2026-11-16T15:51:31Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified under delegated decision mode (spec_governance.revise_decision_mode: delegated). The proposal adds the committed dispatcher.claude_credential_policy selection field (local-ranking default, central-factory-selection only under numbered-slots) and central_selection_max_age_minutes (1-1440, default 60). It also adds a paragraph defining how the central factory selection record names the single pool slot, and rewords the interactive-selection sentence in the headroom paragraph. One central decision then protects every account for every factory, and the default keeps today behaviour. The new behaviour carries BCP14 clauses and a scenario. All proposed text is applied exactly. The new scenario is numbered 378 and appended after Scenario 377, because Scenario 377 already exists on master and the proposal directs numbering by the repository convention. A minimal modification resolves a contradiction that the LLM doctor objective pass found between the new paragraph and the unchanged host-judgement paragraph (see Modifications). There is no design-record contradiction and no drift origin. The independent sonnet reviewer returned NO BLOCKERS for these exact final bytes.

## Modifications

In contracts.md, in the host-judgement paragraph ("When that judgement runs a Claude model on the host"), two minimal edits resolve a contradiction with the new paragraph "Under `central-factory-selection`, the central factory selection names the slot". That paragraph requires the host judgement to use the centrally named slot. The host-judgement paragraph required the same ranking and forbade reading the account-selection process selection, unqualified. (a) "the same qualification and the same ranking" gains: ", or, under `selection: central-factory-selection`, the same single named slot that the paragraph \"Under `central-factory-selection`, the central factory selection names the slot\" chooses". (b) "It MUST NOT read the account-selection process selection to choose the credential" now reads "INTERACTIVE selection", matching the proposal own wording that only the interactive published selection stays forbidden. The new scenario is numbered 378 rather than 377, because 377 is taken on master.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-16T15:51:00Z
verdict: NO BLOCKERS
proposal_stem: central-factory-selection-consumer
content_digest: 48d1c0ae97aa02aabb08063e48cba4a888f949d66af1fde779e8d221eb1487df
