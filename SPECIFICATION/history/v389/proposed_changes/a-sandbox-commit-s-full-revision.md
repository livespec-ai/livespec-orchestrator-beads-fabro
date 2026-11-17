---
proposal: a-sandbox-commit-s-full.md
decision: accept
revised_at: 2026-11-17T09:51:53Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Accepted as proposed. The clause permits a sandbox commit hook to delegate check-per-file-coverage to a cluster gate Job over the same committed tree with unchanged verdict semantics (no-verdict never passed, failure names target and uncovered rows, no relaxation). Per the behavior-needs-scenario split, Scenario 380 is added and the heading-coverage TODO row is co-edited (bd-ib-22ckko). Governing placement is this repo's contracts.md as it is orchestrator realization mechanism.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-17T09:51:37Z
verdict: NO BLOCKERS
proposal_stem: a-sandbox-commit-s-full
content_digest: 4301f1aa602919fa8134cfd876617a85b1720b45588a7f7616a825b2db19aaf5
