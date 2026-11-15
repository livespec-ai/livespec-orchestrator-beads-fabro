---
topic: commit-red-fold-restores-the-working-tree
author: claude-opus-5-5:v380-r301-poststeps
created_at: 2026-11-15T04:10:05Z
---

## Proposal: commit_red's fold restores the folded commits' changes to the working tree, not the index

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

The seeded-run bullet 'The seed's work reaches publication under replay evidence' (contracts.md §"Self-contained plugin dispatch", v380 line 3816) says commit_red MUST 'fold into the index every seed checkpoint commit' and, two sentences later, that the Red commit MUST stage the one Red test file and no other path. Read literally, folding the checkpoint commits into the index stages their product changes, which contradicts the single-path Red commit. This proposal restates the fold: commit_red moves HEAD to the dispatch base with the seed checkpoint commits, any reseed commit and this run's engine checkpoint commits folded out of history, and restores their changes to the working tree and not to the index, so that the Red commit stages only the one Red test file, directly on the dispatch base. Scenario 285's carried-changes scenario gains one assertion that the carried product change is not staged.

### Motivation

Doctor objective finding O4 on orchestrator spec v380 (check doctor-llm-objective-internal-contradiction, severity medium, SPECIFICATION/contracts.md line 3816): "The seeded-run bullet 'The seed's work reaches publication under replay evidence' requires commit_red to 'fold into the index every seed checkpoint commit' and also requires that 'The Red commit MUST stage the one Red test file and no other path'. Read literally, folding the checkpoint commits into the index stages their product changes, which contradicts staging only the Red test file. The intended mechanism (presumably a soft reset to the dispatch base followed by unstaging the carried changes into the working tree) is not stated." Ruled by legacy-coordinator-agent under R301 on the v380 post-steps; it is cut in the next orchestrator revise slot. In-flight survey (2026-11-15): eight open spec/* pull requests (#5293, #5281, #5180, #5120, #5083, #5061, #5048, #5005); none edits the seeded-run paragraph, commit_red or Scenario 285, so this proposal composes with all of them (default-align).

### Proposed Changes

1. contracts.md, §"Self-contained plugin dispatch", in the paragraph that begins "**A seeded run enters the implement stage from its seed.**", in the bullet that begins "- *The seed's work reaches publication under replay evidence.*": replace its first two sentences, from "Before it commits, `commit_red` MUST fold into the index every seed checkpoint commit" through "and every carried change it does not hold MUST remain in the working tree.", with:

"Before it commits, `commit_red` MUST move HEAD to the dispatch base with every seed checkpoint commit and, when the run started from a reseed commit, that reseed commit, together with this run's engine checkpoint commits, folded out of history, and MUST restore those commits' changes to the working tree and NOT to the index, so that the Red commit sits directly on the dispatch base. The fold MUST NOT leave any carried change staged. The Red commit MUST stage the one Red test file and no other path, whatever the carried changes hold, and every carried change it does not hold MUST be in the working tree, unstaged, once the commit is made."

The bullet's remaining sentences are unchanged. Its existing rule that every product file holds its dispatch-base content while the Red commit's hook runs, and that the carried changes are restored from the seed head commit and this run's engine checkpoint commits after the commit, still governs the hook's duration; the working-tree restoration this proposal states is the state before the hook starts and after the hook ends, whether the hook accepted or refused the commit.

2. scenarios.md, §"Scenario 285 — Red and Green run as separate nodes and every implement commit is made by a command node", in the scenario "A seeded run's carried product changes do not refuse the Red commit": IMMEDIATELY AFTER its last line "And the product change the checkpoint commits carried is still in the working tree", append the line:

```gherkin
    And that product change is not staged in the index
```

No heading is added, changed or removed, so tests/heading-coverage.json MUST NOT change. No other sentence of either file changes.
