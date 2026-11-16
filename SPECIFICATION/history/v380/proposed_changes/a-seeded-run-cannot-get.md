---
topic: a-seeded-run-cannot-get
author: claude-opus-5-5
created_at: 2026-11-15T02:24:37Z
---

## Proposal: A seeded run enters the split implement stage from its seed: commit_red judges only the red turn's changes, an open Red commit is completed, and carried work that already meets the Definition of Done is published

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The ratified text of the split implement stage (contracts.md §"Self-contained plugin dispatch", paragraph "The implement stage runs Red and Green as separate nodes") and Scenario 285 describe only a run that starts from the dispatch base. They say nothing about a run routed `seeded` whose sandbox starts from a preserved tree carrying an earlier run's work, and the literal text actively breaks such a run: `commit_red` compares product files against the dispatch base, so the earlier run's product changes read as product changes of the current red turn and refuse every Red commit; a seed that ends in an open Red commit has no route except a second Red commit on top of it; and a red turn that finds the Definition of Done already met by the carried work can only declare already-satisfied, which ends the run without publishing that work. This proposal adds one paragraph, directly after "An implement turn that reports completion with no diff ends as already satisfied", that states four seeded-run behaviours as MUST text, and adds five Scenario 285 cases that exercise them.

### Motivation

Measured 2026-11-15: the v0.332.1 canary sample bd-ib-st4obs (run 01M7EDXXCG4A, seeded from needs-human/5050cbf4) failed deterministically at commit_red. The same entry failed on every seeded re-dispatch of the split graph on 0.287.0, which is why the fix bd-ib-lmwyfj (576bbb732) was written and then reverted with the graph by #4454. Work item bd-ib-u5r2oz re-lands that fix, and its Definition of Done requires exactly these behaviours; the spec-change tier record of 2026-11-15T02:11:12Z (spec v379, verdict partial, generalization target `## Self-contained plugin dispatch`) holds it until the ratified spec states them, and legacy-coordinator-agent ruled on 2026-11-15 that neither Scenario 285 nor contracts.md states any of them today. The orchestrator release roll is blocked until bd-ib-u5r2oz ships. Carrier: bd-ib-u5r2oz. Fleet scope: livespec-orchestrator-beads-fabro only.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch": add one paragraph

Insert the following paragraph immediately after the paragraph that begins "**An implement turn that reports completion with no diff ends as already satisfied.**" and before the paragraph that begins "**Scripted publication and proof-head integrity.**". No other sentence of the section changes.

> **A seeded run enters the implement stage from its seed.** This paragraph governs the implement stage of a run whose recovery route is `seeded`; on any other run it changes nothing. A seeded run's SEED HEAD is the commit its sandbox checked out at the run's start, which is the seed's immutable commit or its reseed commit as "A seed is moved onto the current default branch before its run starts" decides. Its CARRIED CHANGES are the difference between the dispatch base and the seed head. Its SEED CHECKPOINT COMMITS are the commits after the dispatch base, up to and including the seed head, whose subjects begin `fabro(`, the engine checkpoint commits of an earlier run as "publish_draft publishes a run's work under its authored commit, never under engine checkpoint or merge commits" defines them. Where this paragraph and "The implement stage runs Red and Green as separate nodes" or "An implement turn that reports completion with no diff ends as already satisfied" differ, this paragraph governs a seeded run.
>
> - *commit_red judges only the current red turn's changes.* When `commit_red` checks the working tree and the index for changed product files before it stages anything, a seeded run's check MUST compare against the seed head's tree, with this run's engine checkpoint commits already folded, and MUST NOT compare against the dispatch base. A product change that the carried changes hold, including one that a seed checkpoint commit made, MUST NOT refuse the Red commit; only a product file that the current run's `red` turn created, changed or deleted refuses it, and the refusal's handoff section MUST name only such files. A re-entered `red` turn of a seeded run MUST start from the seed head rather than the dispatch base, with the handoff file carrying what the earlier laps learned, so that the carried changes survive every re-entry.
> - *The seed's work reaches publication under replay evidence.* Before it commits, `commit_red` MUST fold into the index every seed checkpoint commit and, when the run started from a reseed commit, that reseed commit, together with this run's engine checkpoint commits, so that the Red commit sits directly on the dispatch base. The Red commit MUST stage the one Red test file and no other path, whatever the carried changes hold, and every carried change it does not hold MUST remain in the working tree. While the Red commit's hook runs, every product file MUST hold its dispatch-base content, so that a Red test the carried changes already satisfy still fails at Red; `commit_red` MUST put every carried change back in the working tree after the commit, whether the hook accepted or refused it, and MUST NOT pass `--no-verify`, set any variable that skips or relaxes a check, or change the severity of any hook to do so. The restore source of the carried changes MUST be the seed head commit together with this run's engine checkpoint commits: `commit_red` MUST put the carried changes back from those commits, and MUST NOT hold any carried change only in the working tree or in a copy outside the repository's committed objects while the hook runs, so that a hook killed mid-run leaves the tree restorable from committed objects. `commit_green` MUST stage, beside the implementation, every carried change that the Red commit does not hold, so that the commit its amend leaves holds the Red test, the implementation, every carried change and both trailer sets. The branch a seeded run publishes MUST carry every change the seed checkpoint commits held, and no commit on it may lack the red-green-replay trailer evidence that the repository's pre-push range check requires of a commit touching a product-implementation path.
> - *An open Red commit in the seed is completed, not repeated.* When the seed head is, after the seed checkpoint commits, a commit that carries `TDD-Red-*` trailers and no `TDD-Green-*` trailers, the run MUST take that commit as the Red commit that `commit_green` amends and MUST NOT make a second Red commit above it. Before `green` starts, the handoff file MUST name that commit and the Red test file its Red trailers name, and `green` MUST then start exactly as it does after a `commit_red` that committed; `commit_green` folds this run's engine checkpoint commits above that commit and amends it as for any Red commit. The seed checkpoint commits below it then reach publication through `publish_draft`'s fold of one authored commit, which keeps the amended commit's full message and so both trailer sets. When a `green` turn in that run declares the test wrong, the run MUST return to that commit's parent, keeping that commit's changes in the working tree as carried changes, so that the next `commit_red` makes the run's one Red commit under the rules above.
> - *Carried work that already meets the Definition of Done is published.* A seeded run's `red` turn MUST judge whether the work item's Definition of Done is already satisfied against the dispatch base, not against the seed head. When the carried changes meet the Definition of Done and the dispatch base does not, the `red` turn MUST NOT declare the already-satisfied outcome; it MUST write the Red test the Definition of Done needs, which fails at the Red commit because that commit's hook runs against the dispatch base's product files, and the run MUST take the carried changes through `green` and `commit_green` to publication. A `green` turn in that case MAY change nothing beyond the carried changes and end with its completion field reporting the work complete. Such a run MUST NOT end at the already-satisfied ending of "An implement turn that reports completion with no diff ends as already satisfied", nor at any variant of that ending that reports the outcome unprovable.
>
> Measured 2026-11-15: the v0.332.1 canary sample bd-ib-st4obs, run 01M7EDXXCG4A, seeded from `needs-human/5050cbf4`, failed deterministically at `commit_red`; on 0.287.0 every seeded re-dispatch of the split graph failed at `commit_red` because the seed checkpoint commits' product changes read as the red turn's. Scenario 285 in `scenarios.md` exercises this paragraph.

### 2. `SPECIFICATION/scenarios.md`: add five cases to Scenario 285

Under "## Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node", inside the existing gherkin block, append the following scenarios after the last existing scenario and before the closing fence. The heading does not change, so `tests/heading-coverage.json` MUST NOT change.

```gherkin
  Scenario: A seeded run's carried product changes do not refuse the Red commit
    Given a run seeded from a preserved tree whose head carries an earlier run's Fabro checkpoint commits that changed a product file
    And the current run's red turn wrote a failing test and changed no product file
    When commit_red runs
    Then commit_red makes the Red commit directly on the dispatch base
    And the Red commit holds the Red test file and no product file
    And the product change the checkpoint commits carried is still in the working tree

  Scenario: A seeded run's red turn that changes a product file is refused naming only its own change
    Given a run seeded from a preserved tree whose carried changes include a product file
    And the current run's red turn changed a different product file
    When commit_red runs
    Then commit_red makes no commit
    And the handoff file's newest section names the product file the red turn changed and not the carried one
    And the re-entered red turn starts from the seed head

  Scenario: A seeded run publishes every carried change under replay evidence
    Given a run seeded from a preserved tree whose head carries an earlier run's Fabro checkpoint commits
    When the run passes commit_green and publish_draft pushes its branch
    Then the published branch holds every change the seed's checkpoint commits held
    And every commit on the published branch that touches a product-implementation path carries both the Red and the Green trailer sets

  Scenario: A seed that ends in an open Red commit is completed, not repeated
    Given a run seeded from a preserved tree whose Fabro checkpoint commits are followed by a commit carrying Red trailers and no Green trailers
    When the run passes the implement stage
    Then no second Red commit is made
    And commit_green amends that commit with the repository's commit hooks running
    And the commit publish_draft pushes carries both trailer sets

  Scenario: A seed whose carried changes already meet the Definition of Done is published
    Given a run seeded from a preserved tree whose carried changes meet the work item's Definition of Done
    And the dispatch base does not meet it
    When the red turn ends
    Then the red turn has written a Red test and has not declared the already-satisfied outcome
    And that test fails at commit_red against the dispatch base's product files
    And while that hook runs every carried change is restorable from the seed head commit and this run's engine checkpoint commits
    And the run passes green and commit_green and publishes the carried changes
    And the run does not end at the already-satisfied ending or at an unprovable variant of it
```

## Proposal: commit_red reads the Red test file from a Test file line exactly as from a Red test file line, and the red prompt spells out the line

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The handoff paragraph says the `red` section MUST name the Red test file, but nothing states the field line that names it, so the shipped red prompt tells the agent to name "the Test file" while `commit_red` reads only a `Red test file: <path>` line, and a red section that follows the prompt is refused with "commit_red: latest red section names no test file". This proposal adds one paragraph, directly after the seeded-entry paragraph of the first proposal, that makes `commit_red` accept a `Test file: <path>` line exactly as a `Red test file: <path>` line and makes the red prompt's handoff instruction spell out the exact line `commit_red` reads, plus two Scenario 285 cases.

### Motivation

Measured 2026-11-15: the v0.332.1 canary sample bd-ib-st4obs (run 01M7EDXXCG4A, seeded from needs-human/5050cbf4) failed deterministically at commit_red with "commit_red: latest red section names no test file". On master the red prompt (`.claude-plugin/.fabro/workflows/implement-work-item/prompts/red.md`) says to append a `## red` section "that names the Test file", while the commit_red program (`_dispatcher_commit_red_program.sh` and `dev-tooling/commit-red.sh`) matches only `^Red test file:`. These are the last two Definition of Done bullets of bd-ib-u5r2oz, held at spec-change tier on this topic (record 2026-11-15T02:11:12Z, spec v379, verdict partial). Carrier: bd-ib-u5r2oz. Fleet scope: livespec-orchestrator-beads-fabro only.

### Proposed Changes

### 1. `SPECIFICATION/contracts.md` §"Self-contained plugin dispatch": add one paragraph

Insert the following paragraph immediately after the paragraph "**A seeded run enters the implement stage from its seed.**" that the first proposal of this file adds (and so before "**Scripted publication and proof-head integrity.**"). It governs every run, seeded or not.

> **commit_red reads the Red test file from either field line, and the red prompt spells it out.** `commit_red` MUST take the Red test file from the latest `red` section of the handoff file, from a line that begins `Red test file:` or a line that begins `Test file:`, followed by the path. It MUST accept a `Test file: <path>` line exactly as a `Red test file: <path>` line, with the same whitespace and path handling, and MUST stage the file it names exactly as it would for the other line. When that section carries both lines and they name different paths, `commit_red` MUST refuse without committing, and its handoff section MUST name both paths. When that section carries neither line, `commit_red` MUST refuse with the cause that the latest red section names no test file. The `red` prompt's handoff instruction MUST spell out the exact field line `commit_red` reads, written as the literal `Red test file: <path>`, and MUST NOT name the test file only in prose. Measured 2026-11-15: run 01M7EDXXCG4A (bd-ib-st4obs) failed at `commit_red` with `commit_red: latest red section names no test file`, because the red prompt asked for a section "that names the Test file" while `commit_red` read only a `Red test file:` line. Scenario 285 in `scenarios.md` exercises this paragraph.

### 2. `SPECIFICATION/scenarios.md`: add two cases to Scenario 285

Under "## Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node", inside the existing gherkin block, append the following scenarios after the cases the first proposal adds and before the closing fence. The heading does not change, so `tests/heading-coverage.json` MUST NOT change.

```gherkin
  Scenario: commit_red accepts a Test file line as the Red test file
    Given the latest red section of the handoff file names its test file on the line "Test file: tests/test_example.py" and carries no "Red test file:" line
    When commit_red runs
    Then commit_red stages tests/test_example.py exactly as it would for the line "Red test file: tests/test_example.py"
    And commit_red does not refuse with "latest red section names no test file"

  Scenario: The red prompt spells out the field line commit_red reads
    Given the red prompt of the implement-work-item workflow
    When its handoff instruction is read
    Then it spells out the literal field line "Red test file: <path>"
```
