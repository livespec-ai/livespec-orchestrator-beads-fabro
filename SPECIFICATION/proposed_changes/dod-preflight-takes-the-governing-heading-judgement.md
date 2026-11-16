---
topic: dod-preflight-takes-the-governing-heading-judgement
author: claude:legacy-dispatcher-agent
created_at: 2026-11-16T18:34:43Z
---

## Proposal: dod-preflight-takes-the-governing-heading-judgement

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The repository Definition-of-Done preflight must take the governing-heading judgement on every run, exit 2 with a did-not-run line when it cannot, and record the verdict it takes so the launch-time taking reuses it, so a launch never refuses bytes the preflight passed.

### Motivation

Measured 2026-11-16 on build b51b407db7f7 (work item bd-ib-ta4m5b). bd-ib-m76gue: dod-preflight PASS at 17:23:59Z on the repaired References; the launcher's launch-time preflight REFUSED the same bytes at 17:27:45Z (governing-heading verdict named '## Dispatcher admission, WIP cap, and post-merge acceptance'); a re-run at ~18:2xZ PASSED again with the line 'No governing-heading verdict was taken, so I fell back on my own search of the subject'; the 18:28:01Z run refused again. livespec-dev-tooling-i76rv2: preflight PASS 16:34:22Z, then the in-run dod_gate@1 FAILED 16:43:44Z on its reference line (run 01M7JKQEKJQX). The contract's 'One rubric, one subject' requirement (Scenarios 239 and 240) binds every host taking to the same subject and rubric, but does not say that the governing-heading judgement is part of the taking or that a taking which did not take it must not pass, so the preflight fails open and the launch-time taking, which does take it, refuses. Because no governing-heading verdict is recorded, the recorded-verdict reuse of Scenario 240 has nothing to reuse.

### Proposed Changes

Add to SPECIFICATION/contracts.md, in the "One rubric, one subject" taking paragraph that begins "A TAKING is one invocation of the judgement", the following sentences after the chain-of-candidates sentences:

"The spec-stated governing-heading judgement is part of every host taking. A repository preflight MUST take it on every run, and MUST NOT answer a pass on a fallback search of the subject when it was not taken. When the governing-heading judgement cannot be taken (no eligible model, a timeout, an unparseable verdict, or the input bound ending every candidate), the repository preflight MUST NOT exit 0: it MUST print a did-not-run line naming the cause and exit 2, and it MUST write the did-not-run record at most once per distinct cause until the judgement next runs. A repository preflight that takes the governing-heading judgement MUST record the verdict it took as a cache-eligible record on the item's subject and rubric digests, so the launch-time taking and the pre-dispatch taking on identical digests reuse that verdict ('One rubric, one subject') and never take it again. A reference line that a repository preflight passed on a recorded governing-heading verdict MUST NOT be refused by the launch-time taking on identical digests."

Reconcile the existing reference-line paragraph of SPECIFICATION/contracts.md (the paragraph that says the `dod_gate` prompt MUST direct the judge, "wherever it reads `scenarios.md` itself rather than taking a returned governing-heading verdict", to quote the step line that states the behaviour). Append to that sentence's paragraph: "That direction applies only to the `dod_gate` node's own reading of `scenarios.md`. It is not a fallback for a host taking: a repository preflight, pre-admission judgement or pre-dispatch judgement that has not taken a governing-heading verdict MUST NOT answer a pass on a reading of `scenarios.md` of its own; it reports that it did not run, as 'One rubric, one subject' requires."

Add to SPECIFICATION/scenarios.md the following scenario, numbered with the next free scenario number at revise (shown here as NNN):

## Scenario NNN — A repository preflight never passes on a fallback search, and its recorded governing-heading verdict is reused by the launch-time taking

```gherkin
Feature: A reference line the preflight passed is not refused at launch on the same bytes
  As the operator of a factory
  I want the repository preflight to take the governing-heading judgement or report that it did not
  So that a launch never refuses a reference line the preflight passed

  Scenario: A preflight that cannot take the governing-heading judgement does not pass
    Given an item with a Definition of Done whose reference line names a heading
    And the governing-heading judgement cannot be taken on the host
    When the repository preflight runs
    Then it prints a did-not-run line naming the cause and exits 2
    And it does not exit 0 and does not answer PASS on a search of its own
    And it writes the did-not-run record once for that cause

  Scenario: A recorded governing-heading verdict is reused by the launch-time taking
    Given a repository preflight that took the governing-heading judgement and passed the item's reference line
    And the item's subject digest and the rubric digest are unchanged
    When the launch-time preflight is taken on the same bytes
    Then it reuses the recorded verdict and takes no judgement
    And it does not refuse the reference line the repository preflight passed
```

