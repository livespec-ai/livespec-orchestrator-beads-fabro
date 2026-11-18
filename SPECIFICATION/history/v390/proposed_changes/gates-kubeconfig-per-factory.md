---
topic: gates-kubeconfig-per-factory
author: central-credential-service
created_at: 2026-11-18T04:34:31Z
---

## Proposal: A dispatcher factory may declare a gates_kubeconfig that the per-run sandbox configuration mounts for gate-Job delegation

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add one requirement under 'Fabro factory host provisioning constraints' and one scenario: dispatcher.factories.<name>.gates_kubeconfig names a kubeconfig file on the dispatching host that the per-run sandbox configuration mounts read-only where the gate-delegation client reads its credential (the GATES_KUBECONFIG environment variable, default /etc/ci-runner/gates.kubeconfig), so a factory sandbox can delegate a gate Job to the cluster without sharing another consumer's credential.

### Motivation

In-sandbox commit hooks overrun on check-per-file-coverage (utdijk 3600 s, td5prc 1806 s, kzgpzm fix-commit runs failing three times). bd-ib-22ckko delegates that check to a cluster gate Job, but a Fabro sandbox holds no gates kubeconfig, so delegation never fires there. The maintainer approved a separate gate-submitter-factory credential ("I approve the credential.", relayed 2026-11-17). Which file a given factory's sandboxes receive is a contract between dispatcher configuration and the factory, so it belongs in the specification, in the same per-factory shape as dispatcher.factories.<name>.github_app. Ledger: bd-ib-nr53me; siblings livespec-dev-tooling-d53axg (manifest identity) and livespec-dev-tooling-66cy2b (boot re-render and delivery).

### Proposed Changes

constraints.md, under '## Fabro factory host provisioning constraints', add a bullet: **Per-factory gate credential.** A factory entry MAY declare dispatcher.factories.<name>.gates_kubeconfig, a path to a kubeconfig file on the dispatching host. When it is declared and the file exists, the per-run sandbox configuration MUST mount that file read-only at the path the gate-delegation client reads (the GATES_KUBECONFIG environment variable, defaulting to /etc/ci-runner/gates.kubeconfig), so the sandbox can delegate gate Jobs to the cluster. When the key is absent the run proceeds unchanged and the commit hook falls back to the local aggregate. A declared key whose file is missing MUST be recorded as a warning in the dispatch journal and MUST NOT refuse the dispatch. The file's contents MUST NOT be logged, journaled, or copied into any record; only its presence and the path name may appear. A value that is not a non-empty string MUST refuse before claim with a diagnostic naming dispatcher.factories.<name>.gates_kubeconfig.\n\nscenarios.md, add: Scenario: A factory sandbox receives the declared gate credential. Given a target whose dispatcher.factories.<name>.gates_kubeconfig names an existing file / When the Dispatcher dispatches an item to that factory / Then the per-run sandbox configuration mounts the file read-only at the gate-delegation client's credential path / And no record carries the file's contents. Scenario: An absent or missing gates_kubeconfig does not refuse the dispatch. Given a factory with no gates_kubeconfig, or one naming a missing file / When the Dispatcher dispatches / Then the run proceeds without the mount, a missing file is recorded as a warning, and the commit hook falls back to the local aggregate.
