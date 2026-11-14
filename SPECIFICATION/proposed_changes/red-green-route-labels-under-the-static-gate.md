---
topic: red-green-route-labels-under-the-static-gate
author: claude-opus-5-5
created_at: 2026-11-14T21:45:00Z
---

## Proposal: The red and green nodes' routed labels fall under the static routing-directive gate

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The `red` and `green` ACP nodes route on labels they emit: `red -> already_satisfied` on `preferred_label=already-satisfied`, and `green -> test_wrong_reset` on `preferred_label=test-wrong`. The static routing-directive gate (tests/integration/test_routing_schema_nodes_emit_a_directive.py) covers only `output_schema="routing"` command nodes, whose scripts it reads, so a label these agent nodes never emit can name an edge no run takes. State that every `preferred_label` edge leaving `red` or `green` names a label that node's prompt directs the agent to emit, that the node's output schema declares `preferred_next_label`, and that the static gate fails, naming the node and the label, when either does not hold.

### Motivation

Split out of bd-ib-vspyye by legacy-coordinator-agent's ruling on 2026-11-14 ~21:3xZ. vspyye's routing-test bullets were released on **Canary coverage.**, and this bullet was not stated anywhere. legacy-dispatcher-agent's v0.332.0 canary review (2c53c5e1) found that `red` and `green`, which emit `already-satisfied` and `test-wrong`, sit outside the static gate that covers the 8 routing command nodes. It does not gate the v0.332.0 roll.

### Proposed Changes

1. In SPECIFICATION/contracts.md, paragraph "**The implement stage runs Red and Green as separate nodes.**", immediately before its closing sentence "Scenario 285 in `scenarios.md` exercises this paragraph and the next.", insert:

"Every edge leaving the `red` or the `green` node whose condition routes on a `preferred_label` value MUST name a label that the node's prompt directs the agent to emit as its `preferred_next_label`, and the node's output schema MUST declare `preferred_next_label`. The repository's static routing-directive gate MUST cover the `red` and `green` nodes alongside the routing-schema command nodes, and MUST fail, naming the node and the label, when such an edge names a label the node's prompt does not direct the agent to emit or when the node's output schema does not declare `preferred_next_label`."

2. In SPECIFICATION/scenarios.md, under "## Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node", inside the existing gherkin block, append:

```gherkin
  Scenario: A routed label the red or green prompt never asks for fails the static gate
    Given the committed implement-work-item workflow graph
    And an edge leaving the green node routes on preferred_label=test-wrong
    And the green prompt does not direct the agent to emit test-wrong as its preferred_next_label
    When the static routing-directive gate runs
    Then it fails naming the green node and the test-wrong label

  Scenario: A red or green output schema without preferred_next_label fails the static gate
    Given the committed implement-work-item workflow graph
    And the red node's output schema does not declare preferred_next_label
    When the static routing-directive gate runs
    Then it fails naming the red node
```

No H2 heading is added, so tests/heading-coverage.json is unchanged.
