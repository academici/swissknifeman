# Plan index - `plans/<PLAN-ID>/index.md`

<!-- Map of plan FILES + provenance links (root/contracts/plan-index-schema.md, P1.2
     sealed v1). NOT a bearer of status (Status Board/phases/Pn.md) and NOT a bearer of “where
     further" (handoff.md) - the temptation to bring this or that here = the second bearer of the fact,
     stop (§3 plan-protocol). Optional: plan without index.md is valid. Three sections strictly
     in that order; directory map nodes that are missing from the plan are omitted. -->

**Updated:** <YYYY-MM-DD>

## Directory map

| Path | Destination |
|:--|:--|
| `plan.md` | stable core: Meta, Context, Rules, §3 Routing, §7 Contracts |
| `status.md` | generated status projection |
| `phases/<Pn>/<Pn>.md` | stable Phase Context + item index |
| `phases/<Pn>/<Pn.m>.md` | stable item specification |
| `phases/<Pn>/<Pn.m>.state.md` | generated volatile item state |
| `phases/<Pn>/<Pn>.closed.md` | generated terminal phase contract/result |
| `bundles/<Pn.m>.json` | ordered digest-qualified executor inputs |
| `decisions/` | append-only decisions + generated current/archive/index views |
| `handoff.md` | rolling pointer "where we are" (overwritten) |
| `roadmap.md` | executive map: batches/workflow/gates |
| `journal.jsonl` | append-only run history `task:plan-*` |
| `brief/` | layer 0 “input”: owner’s brief + clarifications |
| `findings/` | layer 1 “raw materials”: ​​RAG-squeeze, recon |
| `research/` | layer 2 “synthesis”: author’s design documents |
| `artifacts/` | worked examples and raw retrieval/no-search provenance for self-contained design |
| `root/` | long-lived material (contracts, etc. - see section below) |
| `open-questions.md` | controversial/unresolved |

## Provenance

<!-- The only meaningful section is the “source → phase-consumer” connections.
     If-then (anti-double, §3 contract): if COMPLETELY derived from Inputs/Required
     Reads items - narrow the index to a directory map + escalate the value of the section
     owner, do not create a double. -->

| Source | Layer | Nourishes | Essence |
|:--|:--|:--|:--|
| `findings/<slug>.md` | findings | `<Pn>` | 1st line: what gives |
| `research/<NN>-<slug>.md` | research | `<Pn.m>` | 1st line: what gives |

## Key artifacts `root/`

<!-- Optional. The status HERE is about the maturity of the CONTRACT-artifact (sealed/draft), not
     about the item of the plan: this is not the second bearer of the item status (§3 the limit is met). -->

| Artifact | Essence | Status |
|:--|:--|:--|
| `root/contracts/<name>.md` | 1 line | sealed vN (`<Pn.m>`) \| draft |
