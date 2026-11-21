---
proposal: a-factory-commit-that-reaches.md
decision: accept
revised_at: 2026-11-21T11:14:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: legacy-dispatcher-agent
---

## Decision and Rationale

ACCEPTED as filed under delegated decision mode, per the order recorded in the plan handoff (legacy-coordinator-agent, R301, accepted in advance): a published run commit must carry a conventional-commit subject so release-please sees it, fail-closed in publish_draft with LIVESPEC_PUBLISH_DRAFT_SUBJECT_NOT_CONVENTIONAL. Independent review: NO BLOCKERS; no H2 heading changes. Reviewer noted non-blocking follow-ups: the older "keeps its existing behaviour" sentence for republish pushes reads slightly misleading now, and "names another conventional type" points at no defined work-item field.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-21T11:14:52Z
verdict: NO BLOCKERS
proposal_stem: a-factory-commit-that-reaches
content_digest: 9131c48254dfd4c36e93c9539524e504ca33a1b01045f62f5d2d1a6806ccffe2
