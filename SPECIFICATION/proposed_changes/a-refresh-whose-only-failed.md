---
topic: a-refresh-whose-only-failed
author: claude-sonnet-5-5
created_at: 2026-11-18T01:13:40Z
---

## Proposal: A refreshed head passes a generated record file the default branch already carries out of generator order

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A refreshed head whose committed generated record file differs from its generator's output over that head still fails as `generated-record-file:<path>`, EXCEPT when the default branch the stage refreshed onto already carries that same difference. In that case the stage MUST pass the head, MUST name the target and the default-branch commit it compared against in the run's output for that stage, and MUST NOT count a refresh-repair round. A difference the pull request's own change causes still fails and takes the refresh-repair route.

### Motivation

Two factory runs ended `refresh-repair-exhausted` on the same gate target, `generated-record-file:tests/heading-coverage-debt.json`, because origin/master's own copy of that register was not in its generator's order: bd-ib-eogs2t run 01M7M30KY0ZK (its green pull request sat 5.5 h as a draft) and bd-ib-6wmrob run 01M7MVRB9BT1. A repair regenerates the register, the next refresh restores the default branch's bytes, and each round repeats the whole janitor, proof and review tail (measured 75 to 90 minutes per round), so the loop cannot converge while the default branch itself carries the drift. The unconditional MUST in "A refreshed head carries its generated record files as generated" forbids the stage from passing such a head. IMPL-AHEAD-OF-SPEC GAP: livespec-orchestrator-beads-fabro#5489 (work item bd-ib-myvlqz) already implements this exception, hand-landed under the coordinator's R301 decision, so the code currently exceeds the ratified clause and Scenario 238; this proposal brings the spec up to the code. The same change also leaves an exhausted `pr_refresh` pull request ready for review and labelled do-not-merge, and records each round's failed gate target in the ended-run reason; both were ruled internal (the "Refresh-repair accounting" clause fixes only the `needs_human` ending, the cause and the pointer) and are NOT part of this proposal.

### Proposed Changes

Two edits. No `## ` heading is added, changed or removed, so `tests/heading-coverage.json` needs no co-edit.

**Edit 1 - `SPECIFICATION/contracts.md`.** In the paragraph that begins **A refreshed head carries its generated record files as generated.**, replace its last two sentences with this text. The preceding sentences are unchanged.

> A file whose committed bytes differ from its generator's output MUST fail the stage as a failed gate target named `generated-record-file:<path>`, which takes the refresh-repair route with that target in the brief, EXCEPT when the difference is the default branch's own. The difference is the default branch's own exactly when all three hold: the file's committed bytes at the head are identical to its bytes at the default-branch commit the stage refreshed onto, the generator run over that default-branch commit's tree does not reproduce those bytes, and the generator run over that tree produces the same bytes as the generator run over the head. In that case the stage MUST NOT fail the head for that file, MUST NOT count a refresh-repair round for it, and MUST name the target `generated-record-file:<path>` and that default-branch commit in the run's output for that stage. A difference that the pull request's own change causes, a file the pull request edited by hand, and any comparison the stage cannot complete, MUST still fail as above. A head that passes this check therefore carries every row its generator derives from the merged source, including rows the default branch added while the run was in flight, apart from a difference the default branch already carries. Scenario 238 in `scenarios.md` exercises this paragraph.

**Edit 2 - `SPECIFICATION/scenarios.md`, section "Scenario 238 - A refresh resolves a conflicted generated record file by running its generator".** Append these two scenarios to the end of that scenario's Gherkin block, inside the same fenced block, after the scenario "A refreshed head whose generated file was edited by hand fails before the gate". The heading is unchanged.

```gherkin
  Scenario: A generated file the default branch already carries out of generator order passes the head check
    Given a refreshed head whose committed generated record file is byte-identical to that file at the default-branch commit the stage refreshed onto
    And the generator over that default-branch commit does not reproduce that file
    And the generator over the head produces the same bytes as the generator over that default-branch commit
    When the stage checks the head before the repository-declared gate
    Then the stage does not fail the head for that file and counts no refresh-repair round
    And the stage's output names generated-record-file followed by that file's path and the default-branch commit it compared against

  Scenario: A difference the pull request's own change causes still fails the head check
    Given a refreshed head whose committed generated record file differs from its generator's output over that head
    And the generator over the default-branch commit the stage refreshed onto produces different bytes from the generator over the head
    When the stage checks the head before the repository-declared gate
    Then the stage fails with a failed gate target named generated-record-file followed by that file's path
```

