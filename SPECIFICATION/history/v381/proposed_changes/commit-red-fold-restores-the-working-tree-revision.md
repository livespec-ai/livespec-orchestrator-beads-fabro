---
proposal: commit-red-fold-restores-the-working-tree.md
decision: modify
revised_at: 2026-11-15T05:52:33Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

ACCEPT as proposed, then MODIFIED by the doctor fixes under Modifications. Resolves doctor objective finding O4 on v380 (internal contradiction between folding the seed checkpoint commits 'into the index' and a Red commit that stages only the one Red test file): commit_red folds the checkpoint, reseed and engine checkpoint commits out of history onto the dispatch base and restores their changes to the working tree, unstaged; Scenario 285's carried-changes case gains the not-staged assertion. Ruled by legacy-coordinator-agent under R301 on the v380 post-steps and graded PASS on livespec-orchestrator-beads-fabro#5338. Decided under delegated revise_decision_mode; spec-led, not drift-origin; no design record is contradicted. No H2 heading changes.

## Modifications

One doctor fix, on legacy-coordinator-agent's grade of livespec-orchestrator-beads-fabro#5347 (2026-11-15), PASS on the condition that the revise's LLM doctor phases run before the PR is readied and that findings in v381's own new text are fixed in the PR: the objective and subjective phases both found that the proposed first sentence ('MUST restore those commits' changes to the working tree' before the commit) collided with the unchanged sentence that every product file holds its dispatch-base content while the Red commit's hook runs. The new sentences now state the order: the fold leaves no carried change staged in the index, the Red commit stages only the one Red test file, and once the commit is made, whether the hook accepted or refused it, every carried change the Red commit does not hold is in the working tree and not in the index. The hook-duration rule and the restore source are unchanged. Scenario 285's added line is unchanged. The text is otherwise as proposed.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T05:52:16Z
verdict: NO BLOCKERS
proposal_stem: commit-red-fold-restores-the-working-tree
content_digest: f09a0711c9f7db97624c288a1d0f8ddb93fa0f559f5206fbae85c025e3e72dfe
