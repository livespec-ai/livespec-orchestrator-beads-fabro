---
proposal: publish-draft-republish-after-fix-turn-rebuilt-published-head.md
decision: modify
revised_at: 2026-11-21T06:53:40Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: legacy-dispatcher-agent
---

## Decision and Rationale

MODIFIED and ratified by legacy-coordinator-agent under R301 (2026-11-21), delegated decision mode. Original acceptance: 'ACCEPT topic publish-draft-republish-after-fix-turn-rebuilt-published-head as written', recorded as 'accepted by legacy-coordinator-agent under R301, 2026-11-21 ~06:1xZ' (relayed also by throughput-plans-coordinator). DECISION 1 (R301, 06:5xZ, MODIFY): the first independent ratification review found a resumed-run contradiction (the proposal gated republication on 'the run has completed a publish_draft push' while the retained text established the head from validated resume provenance, scenarios.md ~6697-6710), so the gate became 'the run has an established previously published head, from its own record or from its validated resume provenance'; the safety core stays explicit: a lease against exactly that established head, a foreign or unestablishable tip fails closed, no bare force; the hooks-run step was added to the second new sub-scenario; the descriptive clauses at ~4030 and ~5211 were to be left alone. DECISION 2 (R301, 06:5xZ, APPLY (i)(ii)(iii)): the second review found that scoping the lead-in to runs with an established head made the 'head cannot be established -> fail closed with divergent-prior-run, no push' clause vacuous, so the rules apply on EVERY publish_draft visit, the lease arm stays conditional on the tip equalling the established head, the explicit fail-closed rule is restored for a run with no established head, and a new Scenario 176 sub-scenario covers it. DECISION 3 (R301, round cap reached): the fifth review's one wording-only finding, that the Publish repair paragraph (~4030) used 'follows a refresh-repair round' after the sentence that defined it was removed, was fixed by rewording to 'is governed by the paragraph that begins "On every publish_draft visit"'. Two further wording-only fixes (Scenario 142/143 Given reworded to first publication or an absent or ancestor tip; 'repaired head' -> 'head to publish' and 'a repair that rebased' -> 'a rebuild or rebase of the run's own commits') came from reviews 3 and 4. Sixth and final review on these exact bytes: NO BLOCKERS. Basis: legacy-coordinator-agent cross-session messages 2026-11-21 (R301 ACCEPT; MODIFY; APPLY (i)(ii)(iii); (a) apply the ~4030 rewording). Doctor LLM phase run before the cut: no blockers; informational only. Heading-coverage: no '## ' heading added, renamed or removed (H2 sets equal), so tests/heading-coverage.json is unchanged.

## Modifications

Relative to the filed proposal: (1) the lease-guarded republication is admitted on EVERY publish_draft visit whichever route led to it, keyed on the run's ESTABLISHED previously published head (own record, else validated resume provenance) rather than on a completed push of its own; (2) the fail-closed rule for a foreign or unestablishable tip and for a run with no established head is explicit and reachable; (3) 'repaired head' wording replaced by 'head to publish' and the Publish repair paragraph cross-references the new rule; (4) Scenario 176 gains four sub-scenarios (fix-turn rebuild; review-fix republish with hooks; foreign tip whichever route; no established head) and Scenario 142/143's Given is narrowed to a first publication or an absent or ancestor tip.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-21T06:50:53Z
verdict: NO BLOCKERS
proposal_stem: publish-draft-republish-after-fix-turn-rebuilt-published-head
content_digest: 3a6a7f2ca1d3fb01e913e9d1e2905bcc2c7880c5aed6b71f0d2337f5621e56e2
