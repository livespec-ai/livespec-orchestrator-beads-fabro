---
proposal: a-release-canary-coverage-record.md
decision: accept
revised_at: 2026-11-23T12:32:37Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Accepted under legacy-coordinator-agent's R301 ruling of 2026-11-23 on bd-ib-ozxhs4: a release canary coverage record that cannot see a split revert-and-reland pair let 0.346.1 roll half of a pair, so the roll gate is extended beside the ratified Canary coverage clause. The proposal's clause and scenarios are applied verbatim. The pending proposals factory-canary-record-one-line and red-green-route-labels-under-the-static-gate concern the canary fixture and the pre-merge static gate and are not folded in; no other pending proposal is about roll gating. No H2 heading is added, removed or changed, so tests/heading-coverage.json is unchanged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-23T12:31:07Z
verdict: NO BLOCKERS
proposal_stem: a-release-canary-coverage-record
content_digest: b29b4131fb7990f0a0f53d6b5fb3317bf8edab360c25e8ab142f60124a1f994c
