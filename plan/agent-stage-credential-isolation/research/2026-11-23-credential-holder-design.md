# Credential holder for the implement-work-item workflow: measurements and lawful shapes

Seat: agent-stage-credential-isolation, 2026-11-23. For the maintainer, via legacy-coordinator-agent
(coordinator-duties §9: an architectural change). Notation: "holder" = a node that must keep a
publication-capable credential by contract (`publish_draft`, `pr_refresh`, `pr`, and the preserving
steps); "reader" = a command node that only reads the forge; "agent stage" = a node whose turn an agent
takes.

## The problem in one paragraph

The engine's environment table is run-wide: every node of a run sees the same environment, and a command
node has no environment of its own (measured on runs 01M7ZNN9F2DD and 01M7ZTRPE4SA, bd-ib-sgnfom). The
contract (contracts.md, "Publication is mechanically confined to the scripted publication stages") says
an agent stage's environment, files and processes hold no credential that can publish and none from which
one can be minted, while the holders keep theirs. Those two facts cannot both hold while the credential
sits in the run-wide environment. Run 01M84RAW8R8H (bd-ib-w64kr3) showed the consequence: its agent made
the Red test pass by deleting the credential projection for EVERY node, which would also strip the
holders (preserved ref refs/heads/needs-human/1ee4e45a786d4938b38d27e24aad4f0c; not mergeable).

## Measurements (what the sandbox is)

1. **The factory sandbox runs as root.** The exported run 01M84RAW8R8H shows every stage using
   `/root/.claude/plugins/...`, `/root/.cache/...` and `/root/.livespec-gate-preview/...`.
2. **Same image, measured in a gate Job** (gates-repro-lq, poweredge-xubuntu, image
   `ghcr.io/livespec-ai/livespec-fabro-sandbox@sha256:2d3366fda0c53eee9884dd1ea1953de14c7c0c01311bb10c61dc4b48a7d0d6b8`
   = python-agent-v1.188.1, gate-repro run `20261123T192503Z-2350911`): `uid=0(root)`, `HOME=/root`,
   `CapEff=CapBnd=00000000a80425fb` (a container-default style capability set), `NoNewPrivs: 0`,
   `Seccomp: 0`; `/usr/bin/su` present. **Caveat:** a gate Job is not the petri pod. The factory pod is
   built by sandbox-driver-kubernetes v0.8.4, whose pod spec this seat cannot read (`fabro settings`
   exposes the image and CPU/memory only). The image, uid and capability facts are the image's; the pod's
   own securityContext, sidecars and shareProcessNamespace are NOT measured.
3. **Consequence of (1) and (2):** if the agent runs as root with the default capability set, every agent
   process can read any file in its container regardless of owner or mode. A holder process, file or
   socket in the same container cannot then be protected from an agent by uid, mode or ownership. (The
   default set carries CAP_DAC_OVERRIDE and CAP_SETUID; the exact bit decode was not run on the Job.)
4. **What already exists:** the broker (a one-shot stdin process; the workflow launches none today), the
   gh wrapper's recorded-stage file (agent-writable), and the INTERIM 0600 `app-inputs.env` (zf2kdh;
   readable by any root agent, to be closed by this item). A finished run's sandbox is retained, stopped,
   with its filesystem until the run's retention TTL (measured on run 01M83PGQX4TT).

## Lawful shapes

| Shape | Where the credential lives | Who proves "this call is a holder, not the agent" | Cost | Risk |
|---|---|---|---|---|
| **C. Per-node environment in the engine** | The engine hands the run's credential only to the environment of command nodes that declare it (`publish_draft`, `pr_refresh`, `pr`, preserving steps); agent nodes and readers get none | The engine: it launches the node with that environment; the agent cannot change which node it is | A change in Fabro (the fork, `.ai/fabro-fork-hand-build.md`) so a node can carry its own environment, plus node declarations in the workflow. No new process. Replaces the run-wide table entry and the interim file | Needs the engine change and its release train. Unmeasured: whether the engine can scope env per node, and what a holder's children inherit |
| **E. Publication moves out of the pod** | The dispatcher/host (outside the pod) holds the only publication credential; the pod holds at most a read-only token | The host, which reads the run's state from the engine (current node), never from the pod | Highest. `publish_draft`/`pr_refresh`/`pr` become host-side actions fed by the run's preserved refs; the three publication command nodes change meaning | Largest behaviour change; preservation and refresh-merge logic that runs repository hooks with the credential today must be redesigned |
| **B. Credential sidecar container** | A second container in the pod (different filesystem), reached over a unix socket on a shared volume | The sidecar, from a stage record the ENGINE writes into a volume the agent container mounts read-only | Medium-high: needs a sandbox-driver-kubernetes pod-spec change | The driver is a vendored plugin; root in the agent container can write the record if the mount is rw |
| **A. Host-side credential service** | A long-lived service outside the pod that performs the broker's writes and the holders' pushes | The service asks the engine which node of the run is current | Medium: a service plus an authenticated per-run channel | The per-run capability is readable by the agent, so the service must enforce policy per operation and per current node; availability and network path |
| ~~D. In-pod uid separation~~ | A non-root holder uid inside the same pod | not applicable | not applicable | **Rejected by measurement** if the pod matches the Job: the agent is root with the default capabilities |

## What does not work (so the maintainer need not weigh it)

- Deleting the projection everywhere (the 01M84RAW8R8H diff). It satisfies the three assertions by
  breaking publication and the readers.
- A file, socket or process in the agent's own container, including `app-inputs.env`, as the end state.
- A stage name the agent can write (the gh wrapper's `agent-stage` record) as the authority for what an
  agent may do.

## Recommendation

**C (per-node environment in the engine)** if the engine can scope an environment to a node, because it
changes the fewest moving parts: the publication nodes, the preserving steps and the readers keep their
scripts, the interim file and the run-wide token entry disappear, and the proof is simple (an agent stage's
environment holds nothing; the holders' still hold theirs). It must be measured first: one engine-side
spike (can a node carry its own `env`, and is it absent from a sibling node?) is the smallest next step.
If the engine cannot, choose **E** over B or A: B and A both keep a credential reachable from the pod's
network or volume and so need per-operation policy (the broker's job today), whereas E removes the
credential from the pod. Readers still need a read-only token in every shape; that part (read scope, the
interim file replaced) rides on whichever shape wins.

## Slices once ruled

S1 is this note's measurement (done above, except the engine-env spike and the petri pod spec). S2 the
holder implementation for the chosen shape (replaces `app-inputs.env`). S3 the overlay withdrawal, only
after S2. S4 the test that fails if any agent-stage-readable credential file exists, with "the file is
absent after the final reader node". The regroomed w64kr3 Definition of Done MUST name the nodes that KEEP
the credential (`publish_draft`, `pr_refresh`, `pr`, and the preserving steps `needs_human`,
`fix_commit_settle`, `review_fix_commit_settle`) so a "delete it everywhere" diff fails it.
