---
topic: a-factory-commit-that-reaches
author: claude-sonnet-5-5
created_at: 2026-11-21T09:14:05Z
---

## Proposal: a-published-run-commit-carries-a-conventional-commit-subject

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A commit a factory run publishes carries a conventional-commit subject (fix for a bug item, feat otherwise, unless the item names another type) followed by the change description, and publish_draft refuses a head commit whose subject has no conventional type prefix, naming the commit and the subject.

### Motivation

Release-please finds no releasable commit when a run's commit is rebase-merged under a bare work-item title: livespec-driver-claude#1175 and #1176 needed a hand-authored Release-As pull request, and commits remain stranded in the orchestrator and driver-codex. The spec has no rule on a published commit's subject; the only subject rule (an authored subject, Scenario 377) accepts any non-empty, non-trailer line, and the Scenario 368 paragraph keeps the authored commit's message without constraining it. bd-ib-lzx7t2 replaced the bare 'feat: red' placeholder with the change description but added no type prefix. Per the tier record of bd-ib-d5avjp (spec-version 395, partial, generalization target Scenario 368). Fleet scope: every release-please repository the factory serves. Filed at throughput-plans-coordinator's request; legacy-coordinator-agent decides the revise.

### Proposed Changes

1. SPECIFICATION/contracts.md: insert this new paragraph immediately after the paragraph that begins '**publish_draft publishes a run's work under its authored commit, never under engine checkpoint or merge commits.**' (the one ending 'Scenario 368 in `scenarios.md` exercises this paragraph.'):

**A published run commit carries a conventional-commit subject.** Every repository this factory serves releases through release-please, which derives a release only from commits whose subject begins with a conventional type, so a commit that reaches the default branch under a bare work-item title is invisible to it. The commit a factory run publishes MUST carry a conventional-commit subject: a type prefix followed by `: ` and the work item's change description. The type is `fix` when the work item's type is `bug`, `feat` otherwise, unless the work item names another conventional type, which then governs. `publish_draft` MUST, on every push it makes (including the one that follows a fold and the unchanged-head push), read the subject of the head commit it is about to push and, when that subject has no conventional type prefix, MUST NOT push and MUST fail closed with `LIVESPEC_PUBLISH_DRAFT_SUBJECT_NOT_CONVENTIONAL`, naming the run, the commit and its subject. A conventional type prefix is a lowercase alphabetic type token, optionally followed by a parenthesised scope and an optional `!`, then `: `; a subject beginning `fabro(` or a hyphenated trailer token is not one. Measured 2026-11-21: livespec-driver-claude#1175 (07cb620) and #1176 (079cfa6) were rebase-merged under the bare work-item title, release-please found no releasable commit, and a hand-authored `fix: ... Release-As: 0.21.2` pull request was needed; commits stranded since the last tag include orchestrator 02767c979, 2300bede3 and 6c2f95527, and driver-codex 1fbb1a0 (`root-fix:`). Scenario 368 in `scenarios.md` exercises this paragraph.

2. SPECIFICATION/scenarios.md, '## Scenario 368 — publish_draft publishes a run's work under its authored commit, never under engine checkpoint or merge commits': append these three scenarios at the end of the existing gherkin block:

  Scenario: A published run commit carries a conventional-commit subject derived from its work item
    Given a bug work item whose run's one authored commit has the subject "fix: refuse a stale lease"
    When publish_draft publishes the run
    Then the pushed head's subject begins with a conventional type prefix
    And the subject's type is fix and its text follows the colon

  Scenario: The type is feat for a non-bug work item and the item's own named type governs
    Given a feature work item with no named type and a work item naming the type perf
    When publish_draft publishes each run
    Then the first pushed head's subject begins with feat: and the second's begins with perf:

  Scenario: A head commit whose subject has no conventional type prefix is refused
    Given a janitor-passed run head whose authored commit's subject is the bare work-item title
    When publish_draft prepares to push it
    Then publish_draft pushes nothing
    And it fails closed with LIVESPEC_PUBLISH_DRAFT_SUBJECT_NOT_CONVENTIONAL naming the run, the commit and its subject

3. No '## ' heading is added, changed or removed, so tests/heading-coverage.json needs no entry.
