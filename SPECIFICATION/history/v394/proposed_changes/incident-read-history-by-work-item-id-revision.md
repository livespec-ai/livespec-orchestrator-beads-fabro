---
proposal: incident-read-history-by-work-item-id.md
decision: accept
revised_at: 2026-11-20T09:43:12Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5:expedited-incident-response-flag
---

## Decision and Rationale

Accepted as proposed. It is a real spec change, not a Definition-of-Done narrowing (legacy-coordinator-agent and plan seat confirmed): the governing section defines neither an item-only read-history invocation nor its reply. The paragraph is BCP14, reuses existing refusal names, matches the shipped reader's behaviour, leaves the full-identity invocation unchanged, and is exercised by one new scenario. Heading-coverage co-edit lands in the revise commit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-20T09:42:13Z
verdict: NO BLOCKERS
proposal_stem: incident-read-history-by-work-item-id
content_digest: 10c7e94f1695e9faeeddc492bb8a3bbb938b94aa10ddb2641eba3193ffb6de4d
