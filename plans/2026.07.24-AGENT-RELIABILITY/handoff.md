# HANDOFF — 2026-07-26 — after P3.2

**Next:** /task:plan-run 2026.07.24-AGENT-RELIABILITY P3.3

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `manual` |
| Context | `continue (/clear) — ручной item` |
| Model | Claude Sonnet 5 |
| Thinking | `high` |
| Суть | Интегрировать behavioral eval bank в skiller (P3.3): system-bank adapter over `packages/skiller/lib/skiller/quality/eval.py`, deterministic graders, paired baseline/candidate, provider capability matrix, seeded transcript sample, benchmark artifact — §3 Routing предписывает `implementation/high`, `Exec = manual`; используй `plan-run` (текущая сессия уже Sonnet/high, ритуал `/model`+`/effort` не нужен), НЕ `plan-exec` (тот пинит sonnet/medium и структурно отклонит `Exec = manual`) |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P3.3
```

**Done:**

- **P3.2 закрыт 🟢 Done** — `analyst.metrics` (item-commit `a4f79f8c`) implements the
  metric-arithmetic layer P3.1 named as P3.2's consumer: `build_metric_record`
  (numerator/denominator/exclusions/completeness/`source_trace_ids`/`baseline_proof_class`,
  resume/fork dedup via `analyst.trace.dedup_records`), `pair_metric` (candidate `None` →
  `deferred`, never a silent zero; a `pinned-not-recomputable`/`unknown` baseline is
  refused as a comparator — `METRIC_PINNED_BASELINE_FORBIDDEN`, D30), `slice_by`
  (project/plan/item over a caller-side `{project_id, trace}` wrapper, since the frozen
  `TraceRecord` carries no `project_id` field), `build_digest`/`digest_to_json` (compact
  byte-stable JSON).
- `packages/analyst/tests/test_metrics.py` — 21 tests green on `a4f79f8c`
  (`PYTHONPATH=packages/analyst/lib python3 -m unittest discover -s packages/analyst/tests
  -p 'test_metrics.py'`).
- `findings/P3.2-metric-reconciliation.md` — re-expresses the four bank-layer-1 floors
  this item's data covers (F1/F7/F13/F14) as `MetricRecord`s bit-identical to
  `bank-manifest.json::layer1_metrics`, each pairing to `deferred` (no layer-2 candidate
  run exists yet); F6 (`trace_completeness`) gets its record shape with `value=None`
  rather than a fabricated pass; a live run demonstrates `pair_metric` refusing
  `journals.classified_lifecycle_events` (pinned) as a comparator.
- `bash packages/analyst/scripts/validate.sh` green: 256 tests total (up from 235 at
  P3.1). `doctor.py`/`test_provider_readers.py`/`test_cli.py` were in this item's
  declared `Files` but left untouched — no concrete requirement against any of them
  surfaced (finding § 6); `cli.py` was outside declared `Files`, so no new
  `analyst <cmd>` was wired (finding § 5).
- `plan.md` §0 Meta v1.16.7 → **1.16.8**; §4 Status Board P3 → `1/5`, `🟡 In progress`;
  §6 Update Log row.

**Remaining:**

- **P3.3–P3.5** ⬜ — system eval bank, disposable-worktree canary, fresh terminal audit.
  **P4** ⬜ waits for terminal P3.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.16.8), §4 Status Board (P3 = `1/5`, `🟡 In progress`), §6
  Update Log, §7 Exported (`unified-agent-trace-v1.md` row unchanged — P3.2 consumed it,
  did not bump it).
- `phases/P3.md` — `## Phase Status` (P3.2 row `🟢 Done`), P3.2 item block (Completion
  Notes/Pending Work carry the full record).
- `packages/analyst/lib/analyst/metrics.py` — the metric-arithmetic layer P3.3/P3.4
  consume (`build_metric_record`/`pair_metric`/`slice_by`/`build_digest`).
- `journal.jsonl` — this item's start/final pair (`plan-run`, `item_id=P3.2`).

**Open risks:**

- **F6/F8/F9/F10 still have no live number** — `bank-manifest.json::baseline_layers.
  layer-2-live-paired.status` ("required before any relative floor is claimed") is not
  yet satisfied; P3.3's paired candidate run is what actually produces it. A P3.3/P3.5
  close that reports these floors green without first running that live pass would be
  exactly the false-GREEN pattern this plan exists to prevent.
- **`analyst`/`harness` package-API minor bumps still owed** (`0.1.0`→`0.2.0`,
  `0.3.0`→`0.4.0`) — `package.json` sat outside both P3.1's and P3.2's declared `Files`;
  apply in the next item that legitimately touches those manifests.
- **`analyst metrics`/`analyst reliability-digest` CLI subcommand not wired** —
  `cli.py`'s `COMMANDS` dispatcher was outside P3.2's declared `Files`; the module is
  directly invokable but has no `analyst <cmd>` entry yet.
- **Predecessor items unchanged:** P0 phase-index row owner (`task:plan-close … P0`)
  and the P1.4 Update Log WARN remain open from earlier handoffs, untouched by P3.2.

**Workarounds / Deferred / Open questions:**

- **`trace-record-missing` residual (P2.5/P2.8)** — still owned by P3.1's trace
  instrument plus P3.3's live paired run; P3.2 built the arithmetic that will consume
  that run's traces, it did not run them.
- **`docs-sync` follow-up** (`packages/task/CLAUDE.md` compiler/enforcement seam
  description) — still owned by P3.1's original note; not touched by this item (out of
  `Files`), carried forward.
- **FOREMAN re-scope marker condition** (`execution-state-machine-v1.md` Exported row:
  "снимается при терминальных P2.1 И P3.1") — both are terminal; the marker lives in
  `2026.07.18-FOREMAN`'s own files (И2 boundary — not edited here), flagged for that
  plan's own bookkeeping.
