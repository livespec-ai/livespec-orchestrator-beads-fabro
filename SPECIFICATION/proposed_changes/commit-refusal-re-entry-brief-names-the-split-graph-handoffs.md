---
topic: commit-refusal-re-entry-brief-names-the-split-graph-handoffs
author: claude-opus-5-5
created_at: 2026-11-15T07:36:08Z
---

## Proposal: Commit-refusal re-entry brief paragraph names the split graph's commit_red and commit_green handoff sections

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Reword the ratified paragraph "Every commit-refusal re-entry brief names the failing files from the full recorded output" (implemented by bd-ib-b3qjzq) and its two Scenario 179 steps so they name the `commit_red` and `commit_green` handoff sections, which carry a refused commit into the re-entered `red` or `green` turn, instead of the workflow node `implement_hook_route`, which no longer exists. The `fix`/`review_fix` settle briefs and open-Red briefs stay as written. Wording only; no behaviour change.

### Motivation

The paragraph's first governed route is "the brief `implement_hook_route` writes when it re-enters the implement stage after a refused commit". The split Red/Green implement graph (orchestrator commit 3e4d1a2be, "split the implement graph into red and green command stages") removed `implement_hook_route` and `implement_commit_settle`. A refused commit now routes `commit_red -> red_admission -> red` or `commit_green -> green_admission -> green`, and the refusal reaches the re-entered turn through the `## commit_red` / `## commit_green` section that `dev-tooling/commit-red.sh` and `dev-tooling/commit-green.sh` append to the implement handoff file. The sibling paragraph "A purely mechanical commit refusal has its own re-entry budget" already names "the commit node's handoff section in the split graph" as the carrier, so the two paragraphs currently disagree about where a re-entry brief lives, and a reader of this one looks for a node the workflow does not have. Filed as spec-wording drift under legacy-coordinator-agent's ruling; owner: throughput-plans-coordinator.

### Proposed Changes

In `contracts.md`, replace the paragraph that begins **Every commit-refusal re-entry brief names the failing files from the full recorded output.** (under `## ACP node timeouts`) with the text below. Only two sentences change: the first route of the governed-brief list now names the `commit_red` and `commit_green` handoff sections instead of the removed `implement_hook_route` node, and the identity sentence speaks of briefs rather than routes so that it reads correctly over a handoff section. Every other sentence, the `fix`/`review_fix` settle briefs, the open-Red briefs, the 40-file cap, and the closing scope sentences are unchanged.

Current text:

> **Every commit-refusal re-entry brief names the failing files from the full recorded output.** This paragraph governs every re-entry brief that tells a re-entered ACP turn of the implement-work-item workflow why its commit was refused or failed: the brief `implement_hook_route` writes when it re-enters the implement stage after a refused commit, whether that re-entry is ordinary or mechanical; the brief a re-entered `fix` or `review_fix` turn receives after `fix_commit_settle` or `review_fix_commit_settle` settled a commit run as `failed`; and the open-Red brief of `fix_open_red_route` and `review_fix_open_red_route` after such a settle. Each such brief MUST take its failed target names and hook error lines from the commit run's full recorded output, never only from its final lines, so that output ending in the hook's per-target timing table still yields the files that failed. Each such brief MUST carry a failing-file section that names each failing file the failed targets' recorded output reports, with the uncovered lines or measured size that output gives for it, for at most the first 40 such files in that output's order, and when the output reports more it MUST state how many further files it omitted. Given the same recorded output, every one of those routes MUST produce an identical failed-target and failing-file section, so that a change to how that output is read, or to the 40-file cap, changes every route's brief alike. This paragraph adds content to those briefs only: it changes no route a refusal takes, no re-entry budget, and none of what "A settled failed commit run is recorded with its cause" requires the settle node's own output to state. The failing-file requirement of "A purely mechanical commit refusal has its own re-entry budget" is the mechanical-re-entry case of this paragraph. Scenario 179 in `scenarios.md` exercises this paragraph.

Replacement text:

> **Every commit-refusal re-entry brief names the failing files from the full recorded output.** This paragraph governs every re-entry brief that tells a re-entered ACP turn of the implement-work-item workflow why its commit was refused or failed: the handoff section `commit_red` or `commit_green` appends to the run's implement handoff file when the repository's commit hook refuses that node's commit, which the re-entered `red` or `green` turn reads as its re-entry brief, whether that re-entry is ordinary or mechanical; the brief a re-entered `fix` or `review_fix` turn receives after `fix_commit_settle` or `review_fix_commit_settle` settled a commit run as `failed`; and the open-Red brief of `fix_open_red_route` and `review_fix_open_red_route` after such a settle. Each such brief MUST take its failed target names and hook error lines from the commit run's full recorded output, never only from its final lines, so that output ending in the hook's per-target timing table still yields the files that failed. Each such brief MUST carry a failing-file section that names each failing file the failed targets' recorded output reports, with the uncovered lines or measured size that output gives for it, for at most the first 40 such files in that output's order, and when the output reports more it MUST state how many further files it omitted. Given the same recorded output, every one of those briefs MUST carry an identical failed-target and failing-file section, so that a change to how that output is read, or to the 40-file cap, changes every brief alike. This paragraph adds content to those briefs only: it changes no route a refusal takes, no re-entry budget, and none of what "A settled failed commit run is recorded with its cause" requires the settle node's own output to state. The failing-file requirement of "A purely mechanical commit refusal has its own re-entry budget" is the mechanical-re-entry case of this paragraph. Scenario 179 in `scenarios.md` exercises this paragraph.

In `scenarios.md`, under `## Scenario 179 — A sandbox commit whose hook outlasts one tool call completes with the hook's own verdict`, make these line replacements (the H2 heading is unchanged, so `tests/heading-coverage.json` needs no edit):

- Replace
  `Given an implement turn whose commit was refused by a hook whose recorded output names check-lint and check-per-file-coverage`
  with
  `Given a green turn whose amend commit_green's hook refused with recorded output naming check-lint and check-per-file-coverage`
- Replace
  `When implement_hook_route re-enters implement spending its ordinary re-entry`
  with
  `When the run re-enters green spending its ordinary re-entry, with commit_green's handoff section as the re-entry brief`
- Replace
  `When implement_hook_route, a fix re-entry after fix_commit_settle and review_fix_open_red_route each build a re-entry brief from that output`
  with
  `When commit_green's handoff section, a fix re-entry after fix_commit_settle and review_fix_open_red_route each build a re-entry brief from that output`
- Replace
  `Scenario: An ordinary implement re-entry after a refused commit names the failing files`
  with
  `Scenario: An ordinary green re-entry after a refused amend names the failing files`

No behaviour is added, removed or narrowed: the set of briefs the paragraph governs is the same set the split Red/Green graph actually writes, and the requirements on each brief are unchanged.
