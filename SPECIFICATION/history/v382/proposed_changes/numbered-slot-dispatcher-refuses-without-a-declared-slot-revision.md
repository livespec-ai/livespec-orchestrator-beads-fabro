---
proposal: numbered-slot-dispatcher-refuses-without-a-declared-slot.md
decision: modify
revised_at: 2026-11-15T07:32:43Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

MODIFY. Both proposals are accepted in substance, with one change. The new scenario heading is numbered to the repository's convention: '## Scenario: a numbered-slot dispatcher...' becomes '## Scenario 376 — A numbered-slot dispatcher...', with the first word capitalized. 376 is the next free number: 374 is claimed by the pending the-pre-dispatch-screen-admits, 375 is ratified, and no open spec pull request claims 376. The paragraph's cross-reference therefore reads 'Scenario 376 in `scenarios.md` exercises this paragraph.' The scenario is appended after Scenario 375, in numeric order, rather than after Scenario 288. The policy key keeps the proposed name dispatcher.claude_credential_policy. Plan epic overseer-iyfjbo R02/R10 (central credential service). It was graded by legacy-coordinator-agent and fixed per the grade at 8c73f209 (livespec-orchestrator-beads-fabro#5346). The new H2 gets a TODO row in tests/heading-coverage.json owned by the R01 implementation item filed in this tenant. Decided under delegated revise_decision_mode; spec-led, not drift-origin; no design record is contradicted. The revise's LLM doctor phases ran before the cut, and the defects they found in this proposal's own text are fixed under Modifications.

## Modifications

The new scenario heading is numbered: '## Scenario: a numbered-slot dispatcher refuses rather than fall back to the unnumbered Claude credential' becomes '## Scenario 376 — A numbered-slot dispatcher refuses rather than fall back to the unnumbered Claude credential'. It is placed after Scenario 375, in numeric order, rather than after Scenario 288. The new paragraph's closing sentence becomes 'Scenario 376 in `scenarios.md` exercises this paragraph.' The text is otherwise as proposed. Doctor fixes. The revise's LLM doctor phases (objective and subjective) found these defects in this proposal's own text, and they are fixed here before the cut: (1) The list of operations governed by the policy adds the operator's credential-status probe (`claude-cred-status`), which resolves the same factory credential. (2) When no declared slot is injected, covered candidates are ineligible and per-node selection continues to an uncovered fallback, as the headroom filter's skip does. `no-declared-slot-injected` refuses the dispatch only when an admission-required node is left with no eligible candidate. A Scenario 376 case covers the mixed node. (3) The 'every consumer MUST use the slot admission chose' rule is limited to consumers that run after admission. The pre-admission judgement uses the slot admission would choose at that moment. (4) The negated MAY becomes MUST NOT. (5) A configuration refusal and `no-declared-slot-injected` on a hand-picked dispatch report exit code 3 (precondition) under Dispatcher exit codes, with no code added. A drain or loop pass leaves the item ready without a claim. (6) The host judgement is excluded from the configuration refusal. It does not run, as the judgement paragraph states, and the dispatch is refused at admission when it needs a Claude credential. (7) Under numbered-slots, the engine LLM credential that The dispatch credential set requires is the declared slots, and the missing-variable diagnostics and preflight name them, not the unnumbered variable. This is stated in the new paragraph, and the pre-existing sentence is unchanged. (8) 'Only when no declared numbered slot is usable' drops 'Only', because an absent or invalid policy also stops the judgement, and the Scenario 174 outline title follows. (9) Scenario 376 gains four cases: the mixed-node fallback, an invalid-policy outline naming the defect with exit code 3, a downstream probe refusal, and a missing policy that keeps the host judgement from running. One subjective suggestion is declined: splitting the judgement's three policy branches into their own paragraph is prose structure only.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T07:32:29Z
verdict: NO BLOCKERS
proposal_stem: numbered-slot-dispatcher-refuses-without-a-declared-slot
content_digest: ea4a160c9971165a4f2eedbc21995628d8f19c3b5e4c1cc6ed8a98919b6de1d8
