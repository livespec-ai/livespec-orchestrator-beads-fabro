---
topic: hooks-and-gates-reach-a
author: claude-sonnet-5-5
created_at: 2026-11-21T08:46:58Z
---

## Proposal: hooks-and-gates-reach-a-push-through-an-unreadable-credential-helper

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

State, as a constraint and as two Scenario 202 sub-scenarios, that a legitimate pre-push hook or gate of a publication stage reaches its push through an unreadable credential helper and succeeds, and that no hook or gate process finds a forge token or App key in its environment or readable files.

### Motivation

contracts.md already ratifies the mechanism in 'Publication is mechanically confined to the scripted publication stages' (hooks and gates MUST run without the credential and reach a push only through a credential helper they cannot read), and Scenario 202 covers a planted hook failing to merge. Two halves of the guarantee have no constraint statement and no scenario: that a LEGITIMATE hook's push succeeds through the helper, and that a hook or gate process finds no forge credential in env or readable files. Work item bd-ib-b3nosr ('Hooks and gates reach a push only through a credential helper whose secret they cannot read') carries exactly those assertions and its tier screen holds it as spec-change/partial with topic hooks-and-gates-reach-a because no proposal exists. This is a SAFETY guarantee, so it is placed in constraints.md (violation observable to an end user and to the maintainer), with the behaviour carried as scenarios per the Gherkin split. Filed per legacy-coordinator-agent ruling R301 (2). Fleet scope: every factory-served repository.

### Proposed Changes

1. SPECIFICATION/constraints.md, section '## Factory sandbox credential constraints': append this bullet at the end of that section's bullet list, before the next '## ' heading:

- **Repository-controlled hooks and gates of a publication stage reach a push only through an unreadable credential helper, and never see a forge credential.** The FACTORY SANDBOX's publication command stages (`publish_draft`, `pr_refresh`, `pr`) run the repository's own pre-push hooks and gates. Such a hook or gate MUST succeed in pushing when it is legitimate: its push MUST reach origin through the Dispatcher-materialized credential helper that holds the credential outside the hook's reach. The process of a hook or gate those stages run MUST find no forge token and no GitHub App key, nor any key from which one can be minted, in its environment or in any file it can read; the credential is never exposed to repository-controlled code through an environment variable or a readable file. Consequently a hook or gate an agent stage changed to publish or merge runs without the credential and its attempt fails without changing origin or the run's pull request. This is the safety guarantee behind `contracts.md` paragraph 'Publication is mechanically confined to the scripted publication stages', stated here as a constraint an operator can observe; the wire-level mechanism stays in `contracts.md`. It is a rule about CAPABILITY: a credential reachable by any route a hook or gate can read is held by the hook or gate, whatever the route is named.

2. SPECIFICATION/scenarios.md, '## Scenario 202 — An agent stage follows only its stage prompt, never publishes, and commits through the repository hooks': insert these two scenarios inside the existing gherkin block, immediately after 'Scenario: A planted hook cannot publish with a publication stage's credential':

  Scenario: A legitimate pre-push hook reaches its push through the credential helper
    Given a run reaching publish_draft, pr_refresh or pr whose repository carries an ordinary pre-push hook that pushes through git
    When the stage pushes the run's publish branch and the hook runs
    Then the push reaches origin through the credential helper and succeeds
    And no LIVESPEC_AGENT_PUBLICATION_DENIED refusal is raised

  Scenario: A hook or gate of a publication stage finds no forge credential
    Given a run reaching publish_draft, pr_refresh or pr whose repository hooks and gates are repository-controlled code
    When a hook or gate searches its environment and every file it can read for a forge token or a GitHub App key
    Then it finds no forge token and no App key and no key from which one can be minted
    And its own push still succeeds only through the credential helper

3. No '## ' heading is added, changed or removed, so tests/heading-coverage.json needs no entry. The proposal adds no contracts.md text: the mechanism is already ratified there.
