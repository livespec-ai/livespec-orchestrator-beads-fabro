---
proposal: gates-kubeconfig-per-factory.md
decision: accept
revised_at: 2026-11-18T07:32:16Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: central-credential-service
---

## Decision and Rationale

accepted on throughput-plans-coordinator's R301 decision, 2026-11-18. A per-factory dispatcher.factories.<name>.gates_kubeconfig key is a contract between dispatcher config and each factory, so it belongs in the specification. Accepted as written; the resulting files add the constraints.md clause, Scenario 381, and its heading-coverage TODO row owned by bd-ib-nr53me, plus one wording fix so the host-name sentence stays true for three bullets.

## Resulting Changes

- constraints.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-18T07:31:39Z
verdict: NO BLOCKERS
proposal_stem: gates-kubeconfig-per-factory
content_digest: d87ceb7d2fda5871d3736758a2baada763650c9408cb9679a9a017c0ac4661fc
