---
topic: repoint-owner-to-livespec-ai
author: claude-sonnet-5-5
created_at: 2026-11-16T18:46:11Z
---

## Proposal: Repoint old-owner fleet references in contracts.md to livespec-ai

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Repoint every remaining `thewoolleyman/<fleet-repo>` reference in SPECIFICATION/contracts.md (18 occurrences on lines 1308, 1372, 1380, 2035, 2288, 2290, 2555, 2557, 2636, 2938, 4749, 4824, 4844, 5792, 6294, 6335, 8134, 8336) to `livespec-ai/<fleet-repo>`. No `## ` heading is added, changed or removed.

### Motivation

The fleet repositories moved to the `livespec-ai` organization. Plan stale-base-merge-options (epic livespec-dev-tooling-xowhol) Definition-of-Done assertion 7 requires the committed old-owner grep to count 0 graded references in each fleet repository's master tree. The mechanical class A edits (pyproject.toml, uv.lock, .livespec.jsonc, e2e-skeleton pyproject) ride a separate chore PR; these spec-text references are class S and must go through propose-change and revise. The vendored LICENSE copyright line and proposed_changes files are excluded.

### Proposed Changes

Replace, in SPECIFICATION/contracts.md only, each occurrence matching `thewoolleyman/(livespec-orchestrator-beads-fabro|livespec-orchestrator-git-jsonl|livespec-console-beads-fabro|livespec-driver-claude|livespec-driver-codex|livespec-dev-tooling|livespec-overseer|livespec-driver-pi|livespec-runtime|livespec)` (not followed by a letter, digit, underscore or hyphen) with `livespec-ai/` followed by the same repository name. This includes the two live path/install strings `git:github.com/thewoolleyman/livespec-orchestrator-beads-fabro@release` (line 1308) and `.pi/git/github.com/thewoolleyman/livespec-orchestrator-beads-fabro/` (line 1380), which become `github.com/livespec-ai/livespec-orchestrator-beads-fabro`, and the design-record citations such as repo `thewoolleyman/livespec`. Every other word is unchanged. `tests/heading-coverage.json` needs no co-edit.
