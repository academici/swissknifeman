# HANDOFF — 2026-07-26 — after P3.1

**Next:** /task:plan-run 2026.07.24-AGENT-RELIABILITY P3.2

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `manual` |
| Context | `continue (/clear) — ручной item` |
| Model | Claude Sonnet 5 |
| Thinking | `high` |
| Суть | Реализовать reliability metrics/digest (P3.2) — paired reliability metrics derived only from the P3.1 trace; §3 Routing предписывает `implementation/high`, `Exec = manual` — используй `plan-run` (текущая сессия уже Sonnet/high, ритуал `/model`+`/effort` не нужен), НЕ `plan-exec` (тот пинит sonnet/medium и структурно отклонит `Exec = manual`) |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P3.2
```

**Done:**

- **P3.1 закрыт 🟠 Done with deviations** — Unified Agent Trace v1 заморожен v1
  (`root/contracts/unified-agent-trace-v1.md`, item-commit `3af26580`): closed
  13-field `TraceRecord`, `trace_id`/dedup rule, analyst-owns-schema/harness-reads-
  thin/journal-links-only split.
- `packages/analyst/lib/analyst/trace.py` — schema owner (`build_trace_record`,
  `trace_id`, `dedup_records`, `record_to_json`): provenance/sha256 check, fail-closed
  privacy scan (`TRACE_PRIVACY_VIOLATION`), `quality.completeness` over six nullable
  field groups with mandatory `reasons`, completeness-ranked resume/fork dedup — 22
  tests green on `3af26580`.
- `packages/harness/lib/harness/provider_trace.py` — thin Claude/Codex readers
  (`build_claude_raw`, `build_codex_raw`): Claude reads the SCHEMA=2 run-report
  presence + caller-supplied linkage; Codex degrades every uncaptured field to
  `null` + `codex-hook-not-integrated` (no comparable Codex hook exists yet) — 9
  tests green on `3af26580`.
- `packages/task/lib/task/journal.py` — additive optional `trace_ref`/`--trace-ref`,
  outside `REQUIRED_FIELDS`; omitted, entry stays byte-identical — 29 tests total (2
  new) green on `3af26580`.
- All three package `validate.sh` green: analyst 235 tests, harness 431 tests, task
  407 tests + `plan-lint` 0 errors / 215 pre-existing warnings (unrelated plans).
- `plan.md` §7 Exported row for `unified-agent-trace-v1.md`: `planned P3.1` →
  `committed P3.1 (3af26580)`. §0 Meta v1.16.6 → **1.16.7**; §6 Update Log row; §4
  Status Board P3 → `🟡 In progress` (0/5 🟢 — P3.1 is 🟠, doesn't count toward the
  🟢 numerator).

**Remaining:**

- **P3.2–P3.5** ⬜ — metrics/digest, system eval bank, disposable-worktree canary,
  fresh terminal audit. **P4** ⬜ waits for terminal P3.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.16.7), §4 Status Board (P3 = `0/5`, `🟡 In progress`), §5
  Decision Log (D80 — F6 deferral resolution), §6 Update Log, §7 Exported (this
  item's row now `committed P3.1`).
- `phases/P3.md` — `## Phase Status` (P3.1 row `🟠 Done with deviations`), P3.1 item
  block (Completion Notes/Pending Work/Known Deviations carry the full record).
- `root/contracts/unified-agent-trace-v1.md` — the frozen v1 schema P3.2/P3.3/P3.4
  consume; §Boundaries names what is explicitly NOT owned here (D90 analytics
  envelope, journal REQUIRED_FIELDS, Codex raw capture).
- `journal.jsonl` — this item's start/final pair (`plan-run`, `item_id=P3.1`).

**Open risks:**

- **F6 (`trace_completeness ≥99%`) has no live number yet** — P3.1 proved the
  instrument only (D80); P3.2/P3.3 owe the first live paired-bank measurement
  against `artifacts/reliability-bank-v1/`. A P3.2/P3.3 close that reports F6 green
  without first running that live pass would be exactly the false-GREEN pattern this
  plan exists to prevent.
- **`analyst`/`harness` package-API minor bumps owed but not applied** (`0.1.0`→
  `0.2.0`, `0.3.0`→`0.4.0`) — `package.json` sat outside P3.1's declared `Files`;
  apply them in the next item that legitimately touches those manifests (P3.2 is the
  natural candidate since it extends `analyst`).
- **Predecessor items unchanged:** P0 phase-index row owner (`task:plan-close … P0`)
  and the P1.4 Update Log WARN remain open from earlier handoffs, untouched by P3.1.

**Workarounds / Deferred / Open questions:**

- **`trace-record-missing` residual (P2.5/P2.8)** — now has an owner-in-progress:
  P3.1 built the trace instrument; P3.2's live paired run is what actually closes
  this residual.
- **`docs-sync` follow-up** (`packages/task/CLAUDE.md` compiler/enforcement seam
  description) — still owned by P3.1's original note; not touched by this item
  (out of `Files`), carried forward.
- **FOREMAN re-scope marker condition** (`execution-state-machine-v1.md` Exported
  row: "снимается при терминальных P2.1 И P3.1") — both are now terminal; the
  marker itself lives in `2026.07.18-FOREMAN`'s own files (И2 boundary — not edited
  here), flagged for that plan's own bookkeeping to pick up.
