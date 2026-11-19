---
proposal: affected-tests-selection-by-recorded-coverage.md
decision: accept
revised_at: 2026-11-19T04:05:38Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Accepted on throughput-plans-coordinator's recorded accept (R301), as the owning session's handoff directs. The measured over-selection (93% of test modules for one dispatcher module) is the ratified behaviour of the import-graph clause, so narrowing it is a spec change. The coverage-execution map keeps every test that executes the module; the import-graph selection stays as the fallback. No H2 heading changes, so tests/heading-coverage.json needs no co-edit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-19T04:04:07Z
verdict: NO BLOCKERS
proposal_stem: affected-tests-selection-by-recorded-coverage
content_digest: 4d64a0ff1b21fcad91d213e3611586c4ba37adc3508cc3232443998acd2c7ac7
