---
proposal: commit-red-fold-restores-the-working-tree.md
decision: accept
revised_at: 2026-11-15T05:52:33Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

ACCEPT as proposed. Resolves doctor objective finding O4 on v380 (internal contradiction between folding the seed checkpoint commits 'into the index' and a Red commit that stages only the one Red test file): commit_red folds the checkpoint, reseed and engine checkpoint commits out of history onto the dispatch base and restores their changes to the working tree, unstaged; Scenario 285's carried-changes case gains the not-staged assertion. Ruled by legacy-coordinator-agent under R301 on the v380 post-steps and graded PASS on livespec-orchestrator-beads-fabro#5338. Decided under delegated revise_decision_mode; spec-led, not drift-origin; no design record is contradicted. No H2 heading changes.

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
