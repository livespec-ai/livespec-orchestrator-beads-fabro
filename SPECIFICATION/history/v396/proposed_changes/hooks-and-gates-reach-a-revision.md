---
proposal: hooks-and-gates-reach-a.md
decision: accept
revised_at: 2026-11-21T09:26:25Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: legacy-dispatcher-agent
---

## Decision and Rationale

ACCEPTED as filed by legacy-coordinator-agent under R301 (2026-11-21), delegated decision mode. Decision recorded verbatim from its cross-session message: 'legacy-coordinator-agent REVISE DECISION under R301, made in advance: topic hooks-and-gates-reach-a (livespec-orchestrator-beads-fabro#5634) is ACCEPTED as filed. It adds one constraints.md bullet under "## Factory sandbox credential constraints" and two Scenario 202 sub-scenarios, with no contracts.md text and no new H2.' Safety core preserved: a legitimate hook pushes only through the credential helper, and no hook or gate can read a forge token or App key. Independent ratification review on these exact bytes: NO BLOCKERS (one non-blocking wording observation on the second new scenario's last Then step, left unchanged because it matches contracts.md). Doctor LLM phase to be run after the cut. Heading-coverage: no '## ' heading added, renamed or removed, so tests/heading-coverage.json is unchanged.

## Resulting Changes

- constraints.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-21T09:26:22Z
verdict: NO BLOCKERS
proposal_stem: hooks-and-gates-reach-a
content_digest: b027907ca664e81963fae0ced06ef1eaa0d1f96fd17133060f4534729274fe4f
