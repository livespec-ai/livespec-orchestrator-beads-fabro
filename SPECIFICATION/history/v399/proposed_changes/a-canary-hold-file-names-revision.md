---
proposal: a-canary-hold-file-names.md
decision: modify
revised_at: 2026-11-23T11:36:09Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Accepted under legacy-coordinator-agent's R301 ruling of 2026-11-23 on bd-ib-soy2m4: narrowing the canary hold to the build it names is a safety-guarantee change, so it is ratified rather than released as internal. The proposal's clause text is applied verbatim.

## Modifications

The proposal said no new H2 heading and carried no scenario. Authoring discipline (i) requires load-bearing behaviour to have a Gherkin scenario, so two Scenario blocks are added inside the existing Scenario 307 feature (a build-naming hold holds only launches resolving to that build; a hold with no build line or an unresolvable build holds every launch). No H2 heading is added, removed or changed, so tests/heading-coverage.json is unchanged.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-23T11:36:02Z
verdict: NO BLOCKERS
proposal_stem: a-canary-hold-file-names
content_digest: 944690ebe454d603d05fae90d2235116ec78faeee5a4138bf1d191859264c9bd
