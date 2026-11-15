---
proposal: the-factory-merge-verifies-the-head-rollup-and-honours-holds.md
decision: accept
revised_at: 2026-11-15T05:52:33Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

ACCEPT as proposed. Carrier bd-ib-x73d36 (stop-the-line, ratify route ruled by legacy-coordinator-agent 2026-11-15): the shared factory merge path merges only on a non-empty all-passing head rollup read from the forge (SUCCESS, SKIPPED, NEUTRAL pass), refuses a target requiring no status checks, re-reads the merge-hold label and every active merge-time hold before every direct merge and auto-merge arming, and never reports a refused merge green; fleet-scoped through the one shared merge path. Evidence: mi-homelab/homelab#1190 merged red on a protection-less target and mi-homelab/homelab#1192 merged directly while merge-hold:on, both reported rc=0. Scenario 375 exercises the paragraph (375 is free; 374 is claimed by a pending proposal). legacy-coordinator-agent graded the proposal PASS (livespec-orchestrator-beads-fabro#5342). Decided under delegated revise_decision_mode; spec-led, not drift-origin; no design record is contradicted. The new H2 gets a TODO row in tests/heading-coverage.json owned by bd-ib-x73d36, co-edited in the revise commit.

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
proposal_stem: the-factory-merge-verifies-the-head-rollup-and-honours-holds
content_digest: 651670d73f7e7ab4aa950b67ebd5ab916b52dc5f4fccc3688aa74778048c2ec8
