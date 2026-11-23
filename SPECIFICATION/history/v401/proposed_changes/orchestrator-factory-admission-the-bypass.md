---
topic: orchestrator-factory-admission-the-bypass
author: claude-sonnet-5-5
created_at: 2026-11-23T17:03:02Z
---

## Proposal: A managed account's protection floor is read from the role holder's one protection-floors record, never applied from a value of this repository's own

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Admission, the bypass launcher and judge and seat selection read an account's protection floor from the protection-floors.json record that livespec-overseer's caam pass publishes, apply no floor value of their own, and refuse a managed account whose protection status the record cannot establish.

### Motivation

Plan central-credential-service (livespec-overseer overseer-iyfjbo), work item overseer-3g5zow (follow-up carrier of overseer-kzmmn7 bullet 2) and its orchestrator-side sibling bd-ib-5vrm34, split by coordinator ruling R301 on 2026-11-23. The orchestrator-side consumers read a protection floor from a record the overseer publishes, which is a contract between two repositories, and the ratified text states no such record: the tier classifier on bd-ib-5vrm34 found that the ratified text defines the admission floor only as the committed `dispatcher.session_headroom_floor_percent`, which the Dispatcher applies itself, and says nothing about the bypass launcher or judge and seat selection reading a floor from one record. A consumer that applies its own value can spend an account's weekly reserve that the maintainer protects (the 2026-11 incident of overseer-kzmmn7, where a consumer drove the protected anthropic-0 account into paid extra usage). The record is already ratified on the producer side: livespec-overseer SPECIFICATION/contracts.md, section "Published protection floors" (spec v123), fixes its name, location, fields and reader rules; this proposal states the reader side here.

### Proposed Changes

1. In `SPECIFICATION/contracts.md`, section "Dispatcher admission, WIP cap, and post-merge acceptance", immediately after the paragraph that begins `**Under `central-factory-selection`, the central factory selection names the slot.**`, insert this paragraph:

**A managed account's protection floor is read from the role holder's one protection-floors record, never applied from a value of this repository's own.** The PROTECTION FLOORS RECORD is the identity-only file `protection-floors.json` that livespec-overseer's account rotation publishes, beside the factory selection record, in the dispatching user's `~/.local/state/caam-usage-rotate/` directory (livespec-overseer contracts.md "Published protection floors"). The caam pass of livespec-overseer is its only writer. It carries `written_at` and `floors`, a list with one entry per PROTECTED account and no entry for an unprotected account, each entry carrying `profile`, `account_uuid` (or `null`) and `floor_percent`, the account's effective protection floor as a percentage of its weekly allowance. A pass with no protected account writes an empty `floors` list. The record carries no credential material and no usage figure, is written on the credential-rotation role holder's host, and is not delivered to other hosts: a reader on a host that does not hold it MUST treat it as absent. Three components of this repository choose a managed account on their own authority and are its READERS: factory admission under the paragraphs above, the bypass launcher that builds a credential policy for a bypass launch, and judge and seat selection. Each reader MUST use the entry's `floor_percent` as the account's only protection floor and MUST apply no protection floor value of its own for a managed account. Each reader MUST treat the record as read-only and MUST NOT write, repair or replace it. A reader MUST refuse to select a managed account whose protection status it cannot establish because the record is absent, unreadable or malformed, with a refusal line naming the account; under admission that refusal is a skip with exactly the semantics of a `no-central-factory-selection` skip. A reader that refuses or skips an account strictly below its protection floor MUST name the account and the floor in that line. The committed `dispatcher.session_headroom_floor_percent` is a separate session-headroom floor and is not a protection floor; this paragraph does not change it.

2. In `SPECIFICATION/scenarios.md`, immediately after the scenario `## Scenario 378 — A central-factory-selection dispatcher projects only the centrally selected slot`, insert these four scenarios, verbatim, numbered with the next free scenario numbers:

## Scenario NNN — Factory admission skips a managed account below the protection floor the role holder published

Given a protection floors record whose entry for the account `anthropic-0` carries `floor_percent` 10

And a covered ready item whose centrally selected slot is `anthropic-0` with seven-day remaining 8 percent

When the Dispatcher evaluates admission

Then the candidate is skipped

And the skip line names `anthropic-0` and the floor 10

## Scenario NNN — The bypass launcher reads the same protection floor and applies none of its own

Given a protection floors record whose entry for the account `anthropic-0` carries `floor_percent` 10

And a bypass launch whose chosen slot is `anthropic-0` with seven-day remaining 8 percent

When the bypass launcher builds its credential policy

Then it refuses the slot and names `anthropic-0` and the floor 10

And it applies no protection floor value of its own

## Scenario NNN — Judge and seat selection read the same protection floor and apply none of their own

Given a protection floors record whose entry for the account `anthropic-0` carries `floor_percent` 10

And a judge or seat selection whose candidate is `anthropic-0` with seven-day remaining 8 percent

When the selection runs

Then the candidate is refused and the line names `anthropic-0` and the floor 10

And an account with no entry in the record is not refused for protection

## Scenario NNN — An absent protection floors record refuses selection of a managed account

Given no protection floors record on the host

When admission, the bypass launcher or judge and seat selection would choose a managed account

Then each refuses it with a line naming the account

And none writes, repairs or replaces the record
