# P4 rationalization portfolio — 2026-09-21

Reducer: `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/research/02-p1-measurement-contract.md` · gates: `decisions/D6-p4-hard-gates-and-experiment-cap.md` · method: `findings/p4-design-method.md`.

**Execution route:** Cursor `composer-2.5` / implementation / high (owner `task:plan-run`); catalog frontier pin remains `claude-opus-5-thinking-high`. No weighted score. No permanent product, config, consumer, docs, or `CHANGELOG` writes.

## Tree boundary

| Axis | Value |
|:--|:--|
| Base HEAD (pre/post Files) | `aa1792e6e05b1b23288975bafefd60cd9579d21c` |
| Base status sha256 (pre/post) | `4f16a7397757aa81238f6e8fc9e6248100a4a92bebae3b2080c245b139947b74` |
| Temporary worktrees | `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/.plan-cache/p4-worktrees/*` — created for experiments, removed with `git worktree remove -f` |
| Experiment traces (machine) | `plans/2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION/.plan-cache/p4-experiment-results.json` |
| P1–P3 admission | GREEN P1.1, P2.1, P3.1; global design audit sealed per D8 |

## Intake ledger (full)

Each row maps audit hypotheses (H*), P1 claims (C*), and P2/P3 evidence. Outcome column is the P4 disposition before experiments; final verdict is in the reducer table below.

| Row | Sources | Mechanism / pain | P4 gate | Experiment | Final verdict |
|:--|:--|:--|:--|:--|:--|
| H1 / C01 | P1 root 2,653 tokens | Shrink root instructions | eligible | EX-P4-02 (merged with H2) | `defer` |
| H2 / C02 | P1 drift AGENTS vs CLAUDE health | Dedupe common carriers | eligible | EX-P4-02 | `defer` |
| H3 / C03 | P1 Task inventory | Explicit-only Task routing | no activation denominator | — | `defer` |
| H4 / C04 | P1 `review.md` | Split review dispatcher | no false-activation denominator | — | `defer` |
| H5,H12 / C05 | P1 routing config | Capability routing vs pins | owner-only / security | — | `reject` |
| H6,H7 / C06 | P1 31 skills listed | Bulk skill disable | no per-task causal evidence | — | `defer` |
| H11 / C07 | P1 projection drift | Thin projection removal | dominated by H2 slice | — | `merged` → H2 |
| H8,H9,H15 / C03 | P1 protocol surface | Durable carrier simplification | not isolatable without Task write | — | `defer` |
| H10 / C09 | P1 health drift; P2 CX-E02, AO-E02, ED-E02 | Lazy maind / drop `--fix` prose | eligible | EX-P4-01 | `keep` |
| H13 / C11 | P1 MCP structural green | Semantic parity slice | no bounded behavioral measure | — | `defer` |
| H14 / C12 | P1 single-plan journal | Reduce plan audit carriers | no repeated material cause | — | `defer` |
| C08 | P1 workflows | Narrow workflow admission | no P2 pain denominator | — | `defer` |
| C10 memory | P3 `defer`; P2 memory names | Capability value | P3 stop | — | `defer` |
| C10 codegraph | P3 `defer`; P2 scan_run_report gap | Capability value | P3 stop | — | `defer` |
| C13 | P1 docs inventory | Doc consolidation | dominated / no measure | — | `reject` |
| C14 | P1 PR #156 | CI hygiene follow-up | separate owning work | — | `defer` |
| C15 | P1 guardrails | Preserve strengths | invariant | — | `keep` |
| P2 friction umbrella roots | CX-E01, ED-E01 | Consumer instruction projection | context-dependent | — | `defer` |
| P2 provider selection | AO-E03 | Config vs observed Cursor | conflicting, not isolatable here | — | `defer` |
| P2 hook paths | ED-E07 | Absolute paths in hooks | consumer-only | — | `defer` |
| P2 auto-approve | CX-E03 | `MODE=bypass` | security-sensitive | — | `reject` |

Experiments run: **2** (cap 4). No experiment rests on zero-valued under-covered telemetry alone.

## Hard-gate ledger (experiment candidates)

| ID | Hypothesis | Observed pain | Isolatable mechanism | Measurement | Reversible | Gate |
|:--|:--|:--|:--|:--|:--|:--|
| EX-P4-01 | H10 / C09 | Healthcheck block in `CLAUDE.md` (~272 tokens on cursor budget) | Remove managed `maind:healthcheck` block | `skiller budget --first-turn --provider cursor` | temp worktree edit | run |
| EX-P4-02 | H1+H2 / C01+C02 | Duplicated common block (~1,600–1,900 tokens) | Delegate common block to `AGENTS.md` pointer | same | temp worktree edit | run |
| — | H6 skill bulk cut | file count ≠ prompt count | — | — | — | **reject** at gate |
| — | H5 routing | policy change | — | — | — | **reject** at gate |

## Experiment EX-P4-01 — remove `maind:healthcheck` block (H10)

**Frozen controls:** P1 corpus parents `T1` (`559026fd…`) and `T6` (`33d93220…`); provider `cursor`; primary metric **total first-turn tokens**; guardrails: no writes outside declared worktree `CLAUDE.md`; invalid if budget exits non-zero.

| Pair | Corpus | Arm A (baseline) | Arm B (candidate) | Δ total | Δ `claude_md` | Acceptance |
|:--|:--|:--|:--|:--|:--|:--|
| P4-01-AB | T1 | 4939 / 2653 | 4667 / 2381 | −272 (−5.5%) | −272 | budget OK; corpus behavioral oracle **not run** |
| P4-01-BA | T6 | 4939 / 2653 | 4667 / 2381 | −272 (−5.5%) | −272 | same |

**Threshold:** material efficiency requires ≥15% or ≥1,000 tokens on primary cost on **both** pairs — **not met** (272 &lt; 1,000 and 5.5% &lt; 15%). Non-inferiority on static probe: yes. **Verdict: `keep`** — aligns with P2 replicated health `--fix` friction but does not justify a P5 slice on cost alone.

**Re-open:** owner authorizes corpus acceptance arms on `T1`/`T6` or accepts sub-threshold hygiene-only slice.

## Experiment EX-P4-02 — delegate `CLAUDE.md` common block to `AGENTS.md` (H1+H2)

**Frozen controls:** corpus parents `T3` (`8a86f55e…`) and `T1` (`559026fd…`); provider `cursor`; primary metric **total first-turn tokens**; same guardrails/invalid rules as EX-P4-01.

| Pair | Corpus | Arm A | Arm B | Δ total | Δ `claude_md` | Acceptance |
|:--|:--|:--|:--|:--|:--|:--|
| P4-02-AB | T3 | 4611 / 2325 | 2704 / 418 | −1907 (−41.4%) | −1907 | budget OK; corpus oracle **not run** |
| P4-02-BA | T1 | 4939 / 2653 | 2976 / 690 | −1963 (−39.7%) | −1963 | budget OK; corpus oracle **not run** |

**Threshold:** material efficiency **met** on both pairs. **Guardrails:** experiment worktrees only; no provider-parity re-measure on Codex in this item. **Acceptance:** P1 binary acceptance on frozen corpus prompts was **not executed** (same class of gap as P2 `0/6` T1–T6 match). Per reducer, incomplete acceptance → **`defer`**, not `go`.

**Re-open:** run two matched corpus acceptance pairs per `02-p1-measurement-contract.md` on the candidate bytes, plus Codex `skiller budget` parity check, then re-admit for P5.

## Evidence → threshold → guardrail → outcome (summary)

| Slice | Evidence | Threshold | Guardrail | Outcome |
|:--|:--|:--|:--|:--|
| EX-P4-01 | −272 tokens ×2 | below 15% / 1k | no product writes | `keep` |
| EX-P4-02 | −41% tokens ×2 | material met | acceptance oracle missing; cursor-only measure | `defer` |
| Memory / codegraph | P3 defer | n/a | coverage gap | `defer` |
| Task / review / routing / skills bulk | P1+P2 | no experiment | — | `defer` / `reject` |
| C15 guardrails | P1 | invariant | — | `keep` |

## GO manifest (P5)

Owner **D9** (2026-09-21) admits one row. P1 corpus agent acceptance on umbrella checkout is **waived**; field validation on consumer projects is out of band.

| slice_id | source | verdict | owned Files | prerequisites | validation | rollback |
|:--|:--|:--|:--|:--|:--|:--|
| `SLICE-GO-01` | EX-P4-02 / H1+H2 | `go` (D9) | `CLAUDE.md` | `AGENTS.md` common contract unchanged | `skiller budget --first-turn` cursor+codex; plan citations/lint/diff | `git restore CLAUDE.md` |

**Release-visible:** yes → root `CHANGELOG.md` `[Unreleased]`.

## Producer-readiness projection (`producer-readiness/v1`)

```json
{
  "schema_version": "producer-readiness/v1",
  "plan_id": "2026.09.20-№1-SWISSKNIFEMAN-RATIONALIZATION",
  "item_id": "P4.1",
  "go_row_count": 1,
  "manifest_digest": "sha256:slice-go-01-ex-p4-02-d9",
  "status": "admitted",
  "owner_decision": "D9-owner-admit-ex-p4-02-field-validation-deferred.md"
}
```

## Dependency graph (selected)

```text
P1 baseline ──┬── EX-P4-01 (keep)
              ├── EX-P4-02 (defer → optional P5 if owner + acceptance)
P2 friction ──┘
P3 memory/codegraph defer ── blocks capability deletion slices
C15 guardrails ── constrain any future P5 row
```

## P5 result section

### SLICE-GO-01 — CLAUDE common delegated to `AGENTS.md`

| Field | Value |
|:--|:--|
| Pre budget (HEAD `aa1792e6`, cursor / codex) | total **6519**, `claude_md` **2653** |
| Post budget (same commit family, after slice) | total **4623**, `claude_md` **757** |
| Δ total / `claude_md` | **−1896** (−29.1%) — meets P4 material threshold |
| P1 corpus acceptance | **skipped** per D9 (field projects later) |
| Guardrails | plan-only writes outside `CLAUDE.md` + `CHANGELOG.md`; budget exit 0 |
| Retained | **yes** |
| Rollback | `git restore CLAUDE.md` restores pre bytes |

Programme stop: no further manifest rows.

## Cleanup

- All `p4-worktrees` worktrees removed; base HEAD/status unchanged.
- Machine-readable experiment output retained under `.plan-cache/` (plan evidence, not product).
