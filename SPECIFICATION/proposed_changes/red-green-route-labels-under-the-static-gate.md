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

The `red` and `green` ACP nodes route on labels they emit: `red -> already_satisfied` on `preferred_label=already-satisfied`, `red -> green_admission` on `preferred_label=seeded-open-red`, `green -> test_wrong_reset` on `preferred_label=test-wrong`, and, since bd-ib-crvt34, `preferred_label=needs-human` to a route that rests the run and a catch-all edge to a route that refuses every other label. The static routing-directive gate (tests/integration/test_routing_schema_nodes_emit_a_directive.py) covers only `output_schema="routing"` command nodes, whose scripts it reads, so a label these agent nodes never emit can name an edge no run takes, and a label a prompt invites can name an edge no node carries. State that every `preferred_label` edge leaving `red` or `green` names a label that node's prompt directs the agent to emit, that every label the prompt invites has an edge that reads it, that neither node declares a JSON-Schema `output_schema`, and that the static gate fails, naming the node and the label, when any of these does not hold.

**Amended 2026-11-15 (bd-ib-crvt34, PR #5372).** The 2026-11-14 draft of this proposal required the red and green output schema to *declare* `preferred_next_label`. The engine contradicts that: a JSON-Schema `output_schema` makes the engine store the turn's final object only as `output.structured`, and it never writes `output.preferred_label`, the key every `preferred_label=` edge condition reads, nor applies a directive's `outcome` (petri `ac0b9fb`, `crates/attractor/steps/src/contract.rs` and `agent.rs`; the key lowering is `frontend/src/condition.rs`). The v0.333.0 canary measured it on bd-ib-st4obs run 01M7GDPBANKE14DXX4HE4TVZVD: every red turn's `seeded-open-red` label was parsed into `output.structured` and the run still fell through `red -> commit_red` three times. A JSON-Schema `output_schema` on a node with a `preferred_label` edge is therefore the defect the gate exists to catch, not the conformance it requires. The amended clauses below require its absence.

### Motivation

Split out of bd-ib-vspyye by legacy-coordinator-agent's ruling on 2026-11-14 ~21:3xZ. vspyye's routing-test bullets were released on **Canary coverage.**, and this bullet was not stated anywhere. legacy-dispatcher-agent's v0.332.0 canary review (2c53c5e1) found that `red` and `green`, which emit `already-satisfied` and `test-wrong`, sit outside the static gate that covers the 8 routing command nodes. It does not gate the v0.332.0 roll.

### Proposed Changes

1. In SPECIFICATION/contracts.md, paragraph "**The implement stage runs Red and Green as separate nodes.**", immediately before its closing sentence "Scenario 285 in `scenarios.md` exercises this paragraph and the next.", insert:

"Every edge leaving the `red` or the `green` node whose condition routes on a `preferred_label` value MUST name a label that the node's prompt directs the agent to emit as its `preferred_next_label`, and every `preferred_next_label` value the node's prompt directs the agent to emit MUST be read by an edge leaving that node. Neither node declares a JSON-Schema `output_schema`: the engine reads a `preferred_label` edge condition from the routing directive it parses out of a turn's final message only under the no-schema or `routing` contract, and a JSON-Schema contract stores the parsed object without setting the label or applying its outcome. A `red` or `green` turn that ends with the `needs-human` label MUST rest the run at `needs_human` with the turn's final message as the recorded cause, and a turn that ends with any other label the graph does not route MUST be refused with the label named in the handoff file and re-enter the stage through its admission bound, never reaching the stage's commit node as an ordinary ending; the unconditional edge leaving each node is reached only by a turn that set no label. The repository's static routing-directive gate MUST cover the `red` and `green` nodes alongside the routing-schema command nodes, and MUST fail, naming the node and the label, when an edge names a label the node's prompt does not direct the agent to emit, when the prompt invites a label no edge reads, or when the node declares a JSON-Schema `output_schema`."

2. In SPECIFICATION/scenarios.md, under "## Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node", inside the existing gherkin block, append:

```gherkin
  Scenario: A routed label the red or green prompt never asks for fails the static gate
    Given the committed implement-work-item workflow graph
    And an edge leaving the green node routes on preferred_label=test-wrong
    And the green prompt does not direct the agent to emit test-wrong as its preferred_next_label
    When the static routing-directive gate runs
    Then it fails naming the green node and the test-wrong label

  Scenario: A label the red or green prompt invites with no edge that reads it fails the static gate
    Given the committed implement-work-item workflow graph
    And the red prompt directs the agent to emit needs-human as its preferred_next_label
    And no edge leaving the red node routes on preferred_label=needs-human
    When the static routing-directive gate runs
    Then it fails naming the red node and the needs-human label

  Scenario: A red or green node that declares a JSON-Schema output schema fails the static gate
    Given the committed implement-work-item workflow graph
    And the red node declares a JSON-Schema output_schema
    When the static routing-directive gate runs
    Then it fails naming the red node, because the engine never sets preferred_label from a JSON-Schema contract

  Scenario: A red turn that ends with a label the graph does not route is refused, not committed
    Given a red turn whose final message ends with preferred_next_label publish_draft
    When the run routes the turn
    Then it enters the red refusal route, which names publish_draft in the handoff file and re-enters red through its admission bound
    And commit_red is not entered

  Scenario: A red turn that ends with the needs-human label rests the run
    Given a red turn whose final message ends with preferred_next_label needs-human
    When the run routes the turn
    Then it rests at needs_human with the turn's final message as the recorded cause
```

No H2 heading is added, so tests/heading-coverage.json is unchanged.
