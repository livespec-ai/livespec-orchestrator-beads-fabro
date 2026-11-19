---
topic: a-credential-re-exec-relabels
author: central-credential-service
created_at: 2026-11-16T18:04:27Z
---

## Proposal: A credential_wrapper re-exec passes the child's exit code and stderr through

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

When a plugin entry point re-execs itself through the configured credential_wrapper, the re-executed command's exit code and stderr reach the caller unchanged, and the 'credential_wrapper could not run in this environment' diagnostic is emitted only when the wrapper itself fails to start or the required secrets are demonstrably absent after the hop.

### Motivation

Measured 2026-11-16 (work-item bd-ib-32jkpv): dispatcher reconcile-merged, re-execed through the tenant credential_wrapper, exited 3 four times with 'credential_wrapper could not run in this environment', while a direct probe through the same wrapper delivered BEADS_DOLT_PASSWORD, GITHUB_APP_ID and GITHUB_PRIVATE_KEY. The cause is in the bin bootstrap (scripts/bin/_bootstrap.py, _self_heal_credentials), identical in v0.328.0, v0.333.2 and v0.334.0: the re-executed child runs with its output captured, and when it exits non-zero with empty stdout the bootstrap prints wrapper_launch_failure's message and discards the child's stderr. Any ordinary non-zero exit that writes only to stderr, such as a reconcile-merged refusal, is therefore relabelled as a credential-projection failure and its real reason is lost, which hid the real blocker from the operator for hours. The specification states no rule for this hop: Scenario 303 covers only the launch-time preflight under a PATH-resetting wrapper, so nothing today requires the child's stderr or exit code to survive a re-exec. Fleet scope: every bin entry point that self-heals credentials (reconcile-merged, accept and the rest) in every tenant.

### Proposed Changes

In contracts.md, under the section "## Worker credential projection", insert, after its final paragraph (the one ending "The behavior is exercised by Scenario 18, Scenario 19 and Scenario 228 in `scenarios.md`.") and before the heading "## Proof credential projection", a new paragraph headed **Credential re-exec passthrough.** stating: when a plugin entry point finds its required secrets absent and re-execs through the configured credential_wrapper, the re-executed command's exit code is the entry point's exit code, and everything the re-executed command writes to stderr and stdout reaches the caller unchanged. The diagnostic 'credential_wrapper could not run in this environment' MUST be emitted only when the wrapper itself failed to start, or when a required secret is demonstrably still absent after the hop, and it MUST name the wrapper and the still-missing secret names and never a secret value; a non-zero exit from the re-executed command with the secrets present MUST NOT be reported as a credential failure and MUST NOT suppress the command's own stderr.

In scenarios.md, add after Scenario 378 (the number 379 is a placeholder: the revise takes the next free scenario number at cut time, because numbering is order-based like versions):

## Scenario 379 — A credential re-exec passes the child's exit code and stderr through

```gherkin
Feature: A credential_wrapper re-exec does not relabel or swallow the child's failure
  Scenario: A re-executed command that refuses with the secrets present reports its own refusal
    Given a plugin entry point whose required secrets are absent from its environment
    And a credential_wrapper that delivers those secrets to the command it execs
    When the entry point re-execs through the wrapper and the re-executed command exits non-zero writing only a refusal message to stderr
    Then the entry point exits with that same non-zero exit code
    And the refusal message appears on the entry point's stderr
    And the output does not say the credential_wrapper could not run
  Scenario: The could-not-run diagnostic names a wrapper that failed to start or secrets still absent
    Given a plugin entry point whose required secrets are absent from its environment
    And a credential_wrapper that fails to start or delivers none of the required secrets
    When the entry point re-execs through the wrapper
    Then the output says the credential_wrapper could not run in this environment
    And it names the wrapper and the still-missing secret names and never a secret value
```

The revise COMMIT MUST add the new scenario's tests/heading-coverage.json TODO row, with a reason naming 'integration tier or above' and "work_item": "bd-ib-32jkpv", and MUST stage the regenerated heading-coverage debt register (this repository carries both: tests/heading-coverage.json and the check-heading-coverage-debt-register gate).
