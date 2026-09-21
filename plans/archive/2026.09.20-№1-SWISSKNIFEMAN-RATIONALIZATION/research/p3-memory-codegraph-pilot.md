# P3 memory / codegraph pilot — 2026-09-21

Reducer: `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/research/02-p1-measurement-contract.md`.
Coverage: `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/findings/p3-telemetry-coverage.md`.
Decision: `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/decisions/D5-p3-coverage-first-pilot-budget.md`.

No combined score. `go` is impossible while the coverage/guardrail gap stands.

## Route and tree

| Axis | Value |
|:--|:--|
| Provider / model / effort | Cursor `cursor-grok-4.6-high` / frontier / high |
| Task run | `690aa4985d3ba14e4531e6eb2ff2af17bf1297cbac25dfbc1a00043704691638` |
| Env conversation | `9c5317fe-29c7-4d9c-aa34-0e80a0d1c877` |
| Hook conversation (sidecar) | `6a029f10-06e7-42fa-a428-cfef0a22014b` |
| Base HEAD before Files | `aa1792e6e05b1b23288975bafefd60cd9579d21c` |
| Pre-Files status sha256 | `3fafb439587286366894005c307fa8fb03c8e84d7b1fa38f836f1be78778b48a` |
| Temporary worktrees | none (pairs not started) |

## P1 thresholds (frozen, not re-interpreted)

- Non-inferiority: every valid B arm accepted; no guardrail regression.
- Material efficiency: both valid pairs improve the predeclared primary cost by ≥15% or ≥1 000 input tokens; one secondary cost must not worsen by >10%.
- Capability value: usefulness ≥ `2` on both valid pairs with provenance/anchor correctness.
- Activation: zero false activations and zero missed required activations.
- Incomplete, mixed, or under-covered evidence → `defer`. Required valid-pair minimum is two per mechanism.

P1 corpus T1–T6 remains eligible in principle and was not substituted. It was not run.

## Pair ledger

| Mechanism | Valid pairs | Invalid replacements | Why empty |
|:--|:--|:--|:--|
| Memory | 0 | 0 | Exact provider does not bind identity, typed exposure, result quality, tokens, and acceptance in one automatic report. D5 forbids expansion. |
| Codegraph | 0 | 0 | Same gap. Live `MCP:find_symbol` is not a typed codegraph op. |

No prompt hash, pair ID, or A/B condition exists because no arm started. Order `AB`/`BA` was not used.

## Probe traces (not pairs)

These are coverage probes, not P1 matched pairs. They prove mechanism availability on the exact provider.

| Probe | Mechanism | Trace | Worksheet result |
|:--|:--|:--|:--|
| M0 | memory | store `mem_mub0hgx0_c76c9db132ce` → recall score 24.64 → forget `deleted: 1` | Known nonempty retrieval; seed removed |
| C0 | codegraph | `find_symbol` `scan_run_report` in `core/codegraph_telemetry.py` L83–92 | Known nonempty symbol |

Usefulness was not scored as a P1 pair metric. Retrieval also returned unrelated lower-score facts, which would matter on a real pair and is not used here to claim value.

## Memory verdict: `defer`

| Gate | Status |
|:--|:--|
| Two valid pairs | missing |
| Coverage complete | no — identity mismatch, calls-only sidecar, `metrics: {}`, analyst has no Cursor schema 2 reader |
| Guardrails on pairs | n/a |
| Material efficiency / usefulness ≥2 on both pairs | n/a |

One-line: keep current selective maind memory activation; do not emit a P4/P5 memory slice from this phase.

Applicability: the worksheet probe shows store/recall/forget work in this connected Cursor session. That is not a P1 capability-value proof.

Coverage limits: Claude automatic result quality was not the execution provider. Codex transcript presence was not re-measured here. Cursor 2-part `MCP:maind_memory_*` names are not `_maind_tool` ops.

Implication for P4: no memory `go` row.

## Codegraph verdict: `defer`

| Gate | Status |
|:--|:--|
| Two valid pairs | missing |
| Coverage complete | no — live `MCP:find_symbol` unclassified; tests expect `MCP:plugin-core-codegraph:find_symbol`; `scan_run_report` would count 0 |
| Frozen 1–4 anchors on a paired task | not started |
| Guardrails on pairs | n/a |

One-line: keep current session-local codegraph availability; do not emit a P4/P5 codegraph slice from this phase.

Applicability: Serena/`plugin-core-codegraph` returned the expected symbol on this provider. That is not anchor-recall or efficiency evidence against `rg|find|read`.

Coverage limits: maind federation `MCP:maind_graph_*` is out of scope and was not treated as repository codegraph. Historical `.cursor/runs` with `MCP:maind_graph_*` remain federation traffic.

Implication for P4: no codegraph `go` row. A later measurement needs typed 3-part MCP names or an equivalent parser, a single run identity, and result-quality capture before any pair.

## Effect / guardrail table

| Mechanism | Δ acceptance | Δ primary cost | Usefulness | Guardrails | Verdict |
|:--|:--|:--|:--|:--|:--|
| Memory | n/a | n/a | n/a | n/a | `defer` |
| Codegraph | n/a | n/a | n/a | n/a | `defer` |

`keep` would require accepted baseline pairs that are non-inferior but below the material threshold. That evidence does not exist. `reject` would require a falsified hypothesis on a valid B arm. The honest stop is `defer`.

## Cleanup

- Memory seed `mem_mub0hgx0_c76c9db132ce` deleted (`deleted: 1`); post-forget recall did not return it.
- No temporary worktrees created; none to remove.
- No session-local codegraph config written.
- Declared Files only; no permanent config, product, docs, CHANGELOG, consumer, or rollout writes.
