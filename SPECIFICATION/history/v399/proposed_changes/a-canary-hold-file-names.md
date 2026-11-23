---
topic: a-canary-hold-file-names
author: claude-sonnet-5-5
created_at: 2026-11-23T11:33:28Z
---

## Proposal: A canary repository hold file may name the orchestrator build it guards, and a launch that resolves to another build is not held by it

### Target specification files

- SPECIFICATION/contracts.md

### Summary

In "## Provisional fleet launch scripts", the "Canary repository hold" bullet gains an optional build-identity line. A canary repository hold file MAY carry a first non-blank line of the form `build: <orchestrator build identifier>`. When the line is present, a launcher resolves the orchestrator build its launch will use from the target repository's installed plugin registry and is held by the canary repository hold only when that resolved build equals the named build. A launch that resolves to any other build is not held by it, and the launcher's log line for that launch says the hold names another build. When the file has no build-identity line, or the launcher cannot resolve the build, the hold applies to every launch exactly as today. The canary exemption list, the held-launch log-line requirement and the rule that the hold applies to every launch kind are unchanged. Every fleet-launch launcher applies the rule, the petri and hl launchers included.

### Motivation

Work item bd-ib-soy2m4 (plan throughput-plans-coordinator, epic livespec-dev-tooling-r7iuj6), raised by legacy-coordinator-agent 2026-11-23. The factory build a run uses comes from the TARGET repository's installed plugin registration. From about 08:45Z the 0.346.1 canary hold held every launch, including items in repositories still registered at 0.345.0 (livespec-overseer, probably hetzner-xubuntu-info), which it never needed to protect, so fleet slots sat idle for about 2.5 h. The current clause names only a repository, so a hold on an unproven build cannot say which builds it guards. Narrowing a safety hold is a safety-guarantee change, so it is ratified here (legacy-coordinator-agent R301 ruling, 2026-11-23). Failing closed on a missing line or an unresolvable build keeps today's protection wherever the new line cannot be trusted.

### Proposed Changes

In SPECIFICATION/contracts.md, "## Provisional fleet launch scripts", bullet "Canary repository hold", insert after the sentence "The canary repository hold applies to every launch kind; a `kinds:` line has no effect on it." the following text.

A canary repository hold file MAY carry a *build-identity line*: its first non-blank line, of the form `build: <orchestrator build identifier>`, naming the orchestrator build the hold guards. When that line is present, a launcher MUST resolve the orchestrator build its launch will use from its target repository's installed plugin registry, and the canary repository hold MUST hold that launch only when the resolved build equals the named build. A launch whose resolved build is another build MUST NOT be held by the canary repository hold, and the launcher's log line for that launch MUST say that the hold names another build. When the hold file carries no build-identity line, or the launcher cannot resolve the build, the canary repository hold MUST apply to the launch exactly as it does without the line. Every fleet-launch launcher, including the petri and hl launchers, MUST apply this rule. It changes nothing in the canary exemption list, in the log-line requirement for a held launch, or in the rule that the hold applies to every launch kind.
