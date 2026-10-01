# Lesson life cycle

The lesson goes through a deterministic pipeline of states, with a person in the gate at the input to the reusable
knowledge. Everything - append-only and recoverable from logs.

## States

```
ephemeral ──promote──▶ candidate ──promote(person)──▶ curated
    │                      │                               │
    └──────── deprecate (soft, not deleted - audit) ◀──────┘
```

| Status | Meaning | How it gets there |
|:--|:--|:--|
| `ephemeral` | raw candidate from run | `digest` |
| `candidate` | confirmed (observed/worked) | `promote` or auto from `recompute` (P3) |
| `curated` | trusted knowledge, comes to memory mAInd | **human only** (`promote --to curated`) |
| `deprecated` | demoted (soft) | `deprecate`, `--supersedes`, drawdown confidence |

Data Layout (per-project, **LOCAL**):

```
<project>/.claude/analyst/
  lessons/{ephemeral,candidate,curated,deprecated}/<id>.json
  audit.ndjson     # append-only provenance of transitions
  events.ndjson    # append-only signal flow confidence (P3)
```

## Provenance and audit

Each lesson brings `source` / `session_id` / `scope` / `evidence`; each transition is a record in
append-only `audit.ndjson` (who, from where to where, agreement). Transition - via re-write + unlink (lesson not
doubles between directories).

## Confidence (P3)

`recompute` recalculates confidence **clean** arithmetic (stdlib, without I/O/hours):

```
p          = (S + α) / (N + α + β)      # Beta-average success rate
volume     = 1 − e^(−N / k)             # penalty for small volume
decay      = λ ^ days                    # time decay
confidence = p × volume × decay          # ∈ [0, 1)
```

Application ranges: `tentative` 0.3 · `moderate` 0.5 · `strong` 0.7 · `core` 0.9 (below 0.3 - `none`).
All thresholds (and why exactly like this) — in [Tuning parameters](./tuning).
Source of truth - `events.ndjson`; snapshot is reproduced at fixed `--now`. Numeric
state-machine: auto `ephemeral→candidate`, `curated` — human only, drawdown → soft-deprecate.

## Consolidation (mem0-taxonomy)

When `promote`/`review` lesson is checked against active (Jaccard) and is classified:
`ADD` (new) · `UPDATE` (clarifies) · `NOOP` (take) · `CONFLICT` (contradicts). **Conflict →
flag-and-ask**: auto-resolve is prohibited, a person decides `--supersedes ID` (soft-deprikate old) or
`--force`.

## Cross-project scan (P2)

`scan` rises over one project: bypasses the registry `config.json:projects[]`, collects lessons from
all, clusters by Jaccard and detects patterns in **≥N projects** — **namespace-isolated**
(inherits from [mAInd](/maind/guide/namespaces): pattern from `ns:axioma` does not flow into someone else's namespace;
project without namespace isolated). Result - `index/by_pattern/<id>.json` (abstracted projection:
`representative{trigger,action,kind}`, `members`, `weight`, `projects`) + human readable
`suggestions/<id>.md`.

**Reconciliation** post-record: orphaned artifacts (pattern disappeared - project disabled, lesson
deprecated, cluster fell below threshold) are removed **strictly in scope run** (`scanned_namespaces` =
`{--namespace}` if specified, otherwise union namespace all enabled-projects). Alien namespace not rescanned →
its files are not touched. Broken index → SKIP (do not delete unclassified). Non-standard
`--min-projects/--threshold` skip auto-prun (protection against churn).

Next: pattern index - input for [suggest →](./suggest).
