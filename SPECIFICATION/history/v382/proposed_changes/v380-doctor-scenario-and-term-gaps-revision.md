---
proposal: v380-doctor-scenario-and-term-gaps.md
decision: accept
revised_at: 2026-11-15T07:32:43Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

ACCEPT as proposed, all four proposals. They close doctor objective findings O1, O2, O3 and O5 on v380, ruled by legacy-coordinator-agent under R301. Three scenarios are added (a Scenario 331 refusal for a cited CI attempt that did not conclude success, and two Scenario 285 cases: commit_red's refusal of conflicting Red test file and Test file lines, and the test-wrong return from a seed's open Red commit). The release-commit CI run's required CI workflow is named as ci.yml, whose ci-green job is master's required check. The contracts.md sentence is re-wrapped to the bullet's fill; its words are as proposed. No heading changes. legacy-coordinator-agent approved this revise slot (livespec-orchestrator-beads-fabro#5339). Decided under delegated revise_decision_mode; spec-led, not drift-origin; no design record is contradicted.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T07:26:00Z
verdict: NO BLOCKERS
proposal_stem: v380-doctor-scenario-and-term-gaps
content_digest: c84eee899d9de8c79dd28509ca006c394bab279a122d9242b71b48250d250bde
