---
topic: registered-plugin-root-exits-3
author: claude-opus-5-5 (no-local-agent-memory seat, hetzner-xubuntu)
created_at: 2026-11-14T21:16:14Z
---

## Proposal: A git worktree of a governed project resolves to its primary checkout's registered install

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The registered-root command matches the governed project's path against the installed-plugins record literally. A git worktree of a governed project therefore has no matching entry, and the command exits non-zero. Every operation-prose import bootstrap passes the current directory, so it fails from the worktree that the fleet repository-mutation rule requires sessions to work in. This proposal states that a git worktree, or a subdirectory of a checkout or worktree, resolves to the registered install of the primary checkout that shares its git common directory. That resolution is not a fall-back to another project's install.

### Motivation

Observed 2026-11-14 on hetzner-xubuntu during plan `no-local-agent-memory` (epic `hxi-7ituzy` in hetzner-xubuntu-info). `registered_plugin_root.py --repo ~/.worktrees/hetzner-xubuntu-info/plan-no-local-agent-memory` exited 3 with "no registered install of livespec-orchestrator-beads-fabro for <worktree>". The same command against the primary checkout printed the root. The fleet's repository-mutation rule puts every tracked edit in a dedicated worktree, so a worktree is the normal working location of a plan or implementation session. Work item `bd-ib-cvvwhb` carries the fix, and it is held at spec-change tier because the ratified clause is silent on worktrees and its "MUST NOT fall back to another project's install" could be read as forbidding the fix.

### Proposed Changes

In `contracts.md` §"Self-contained plugin dispatch", in the paragraph that begins "**A session resolves its project's registered build rather than a remembered one.**", insert the following after the sentence ending "MUST NOT fall back to another project's install.":

> A git worktree of a governed project, and any subdirectory of the project's primary checkout or of one of its worktrees, IS that project for this resolution. When the given path matches no install record literally, the command MUST resolve the path's git common directory to the primary checkout that owns it and MUST print the registered install of that primary checkout. This resolution MUST NOT be treated as a fall-back to another project's install, because the worktree and its primary checkout are one project sharing one git repository. When the path is not inside a git repository, or its primary checkout has no registered install, the command MUST exit non-zero and say so, exactly as for an unregistered project.

In `scenarios.md`, under `## Scenario 271 — A session finds its project's registered plugin build and is told when it is stale`, the feature MUST gain these scenarios:

```gherkin
  Scenario: A git worktree of a registered project resolves to the primary checkout's install
    Given a project whose primary checkout has a registered install of this plugin
    And a git worktree of that project at a path with no install record of its own
    When the registered-root command runs for the worktree path
    Then it prints the plugin root of the primary checkout's install
    And it exits zero

  Scenario: A path whose primary checkout has no registered install is still refused
    Given a git worktree whose primary checkout has no install of this plugin in the installed-plugins record
    When the registered-root command runs for the worktree path
    Then it exits non-zero naming the missing install
```

The two existing scenarios in that feature MUST remain unchanged.
