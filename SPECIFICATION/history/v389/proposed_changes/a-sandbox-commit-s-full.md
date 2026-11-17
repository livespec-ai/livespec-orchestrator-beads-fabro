---
topic: a-sandbox-commit-s-full
author: claude-implement-test-performance
created_at: 2026-11-17T08:24:02Z
spec_commitments:
  impl_followups:
    - id_hint: sandbox-commit-coverage-delegation
      description: |
        bd-ib-22ckko: delegate check-per-file-coverage in a sandbox commit's hook to a cluster gate Job with the verdict semantics the amended clause states.
---

## Proposal: A sandbox commit's hook may delegate check-per-file-coverage to a cluster gate Job

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Amend the 'A commit leg completes past one tool call' paragraph (under '## ACP node timeouts') so a commit run's repository hook MAY delegate its check-per-file-coverage member to a cluster gate Job over the same committed tree, with the same verdict semantics as an in-sandbox run.

### Motivation

Measured 2026-11-17 on factory run 01M7M30KY0ZK (bd-ib-eogs2t): commit_green@1 took 1714 s, of which check-per-file-coverage took 1690 s on a CPU-contended sandbox. Earlier measurements (research note 010 of dev-host-test-gate-load) put the check at a median 38.2 min and a max 46.0 min in a gate Job, against a 60-minute commit-run settle bound shared with the agent's CPUs. A commit whose hook outlasts the bound ends no-verdict, which defeats the plan assertion that a commit completes with the hook's own verdict. Work item bd-ib-22ckko carries the implementation and cannot be approved until the clause permits it.

### Proposed Changes

In the paragraph 'A commit leg completes past one tool call', add: a commit run's repository hook MAY obtain its check-per-file-coverage verdict from a cluster gate Job run over the same committed tree instead of running that member inside the sandbox. The verdict a commit run records for that member MUST be the verdict of that check over the committed tree, wherever it ran. A delegated member that returns no verdict within its own bound MUST make the commit run's state no-verdict, never passed. A delegated member's failure MUST name its failed target and its uncovered file and line rows in the commit run's recorded output, as an in-sandbox failure does. Delegation MUST NOT pass --no-verify, set any variable that skips or relaxes a check, or change a hook's severity.
