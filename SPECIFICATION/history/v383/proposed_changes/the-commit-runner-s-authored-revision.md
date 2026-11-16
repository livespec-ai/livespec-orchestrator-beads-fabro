---
proposal: the-commit-runner-s-authored.md
decision: accept
revised_at: 2026-11-16T04:13:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5 (sandbox-commit-gate-follow-ups f29dd5)
---

## Decision and Rationale

Accept as proposed. Pins the commit runner's authored-subject rule to the shipped trailer pattern, keeps a refusal inside a stopped rebase from ending the rebase, and requires the in-turn wait report and the fix and review_fix stage prompts to name git commit -C REBASE_HEAD and git commit -m, never --no-edit. Adds Scenario 377 with its heading-coverage and debt rows for bd-ib-vpvdn4. Decided under the coordinator's R301 delegation citing its grade-fix commits 484ed363f and 4573aed87; its author plan has no live seat and its code owner plan is paused by the 2026-11-14 drain. Non-blocking review note: the following paragraph 'A commit run outlives a node-timeout cut.' says 'The preceding paragraph's end-of-turn rule', which referred to 'A commit leg completes past one tool call.' and now has this paragraph between; a later wording fix may name that paragraph explicitly.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-16T04:12:14Z
verdict: NO BLOCKERS
proposal_stem: the-commit-runner-s-authored
content_digest: c4f4f175149dbb77d1ff9b08f88986f2a99f6c9e89d3ff5e417e345db91c0bad
