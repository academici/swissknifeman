# HANDOFF — 2026-08-06 — after P5.5

**Next:** ЗАПУСК ВРУЧНУЮ: frontier/high

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — Routing prescribes frontier/high; P5.1's third reopen (D125/D127 paired-wave v3 mint) retains open design decisions on carrier composition |
| Context | continue (/clear) — ручной item |
| Суть | P5.1 (третий реопен): отчеканить аддитивный v3-набор из десяти D125-строк `[OWNER-GRANT:G-OWNER-P5.4-PAIRED-WAVES]` (пять candidate/пять baseline пар, все claude-code, поднятые бюджеты D125) — не трогая v1/v2 байты и пять неиспользованных `p5.4-wave-*` D105-строк. |
| Команда | `—` |

```
/model opus
/effort high
/task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.1
```

**Done:** P5.5 closed `🟠` after its third (D123/D127) reopen — the only remaining reopen on this
item. Both business provider folds (`claude_code.fold_business_records`,
`codex.fold_records` with a new `include_economy=True` keyword, default `False` preserving the
P2/P3 smoke lane byte-for-byte) now emit a closed `economy` object beside the existing booleans:
the seven `economy-evidence-v2` `metric_fields` for `worker` (extraction-only, by key, from the
provider's own reported record) and `coordinator` (always the measured all-zero envelope), plus
`unknown_reasons`/`inclusion_bases`/`zero_bases`. The one sanctioned inclusion basis
(claude-code `reasoning_tokens` ⊂ `output_tokens`) and the one sanctioned structural zero
(`coordinator` → `packages/artifex/lib/artifex/scheduler.py`) use byte-identical text to the
already-frozen P5.7 case-bank fixture. codex's `cost_microunits` is always `null` (D25 — no cost
field exists); its `duration_ms` has no source field in-protocol at all, so it is filled by
`activity.BusinessProviderActivityPort._fill_wrapper_duration` from the wrapper's own measured
wall time *after* `worker.run` returns (not threaded through the shared `normalizer` signature,
to keep the provider-free smoke lane untouched); `turns` is event-derived. `cost_microunits` for
claude-code uses `Decimal`/`ROUND_HALF_UP`, never `float`. `worker.run` propagates the `economy`
key verbatim; `security.observation` admits the new closed five-key shape. 18 new tests (103→121
total), two of which splice the emitted fragment into the real, already-frozen
`validate-economy-evidence.py`'s `validate_shape_v2` and prove both acceptance and refusal.
`test.sh`/`validate.sh` green (121 tests). Both G2B manifests re-frozen a third time
(`business-successor-generation-v1.json`/`business-successor-assurance-v1.json`, item commit
`4e5b1e62`) via the same writer/R2-feedback discipline as the two prior reopens — zero provider
processes. Independent recomputation of both derived hashes, and of all 50 current
`packages/artifex` file hashes from disk, matches. Second, final item-commit `b75e207b` adds the
one appended `g2b-generation-ledger-v1.json` entry and `findings/P5.5-measured-economy-envelope.md`.
The `🟠` is for exactly one disclosed reason: the shared extraction/zero-envelope helpers landed
in `packages/artifex/lib/artifex/providers/common.py`, which neither this item's base `Files` nor
the D123/D127 reopen's own `Files` addition names (only `providers/codex.py`/`providers/claude_code.py`
are listed) — `common.py` is the pre-existing shared-helper module both providers already import,
and duplicating the frozen `zero_bases`/`inclusion_bases` text and the cost-conversion logic
separately in both files would risk the exact drift `root.shared-core` exists to prevent, so the
correct engineering choice was kept and the Files-scope gap recorded honestly rather than
dodged. The D119/D121-carried P4-anchor deviation (`git diff --exit-code 124df816 -- phases/P4.md
artifacts/P4`) is **resolved, not carried forward**: P5.6/D131 retargeted the anchor to
`3533234c`, verified green this session. P5.5's Scope Included is now fully executed across all
three reopens (D108/D119/D121/D123/D127) — no work remains open on this item.

**Remaining:** P5.1 (third reopen, D125/D127 v3 paired-wave mint) → P5.4 (five paired battle
waves), then `task:plan-close ... P5` and one cold `task:plan-audit ... P5`, then P6 (0/4,
`⬜ Not started`).

**Sources of truth:** `phases/P5.md` P5.5 (all 16 fields, `🟠 Done with deviations`, Completion
Notes carry every command and its output across all three reopens) ·
`findings/P5.5-measured-economy-envelope.md` (economy-envelope shape, per-field extraction
rules, smoke-lane boundary, re-freeze scope) · `root/contracts/economy-evidence-v2.md` (the
frozen contract the envelope targets) · `artifacts/P1/economy-evidence-cases-v2.json` (the P5.7
fixture the envelope's `evidence_ref`/`zero_basis` text matches) ·
`artifacts/P5/g2b-generation-ledger-v1.json` (six entries now) ·
`artifacts/P5/business-successor-{generation,assurance}-v1.json` (third re-freeze) · `plan.md`
§4 Phase Index (P5 still 2/7 `🟢` — `🟠` items are not counted in the numerator, matching the P3
convention), §6 Update Log.

**Open risks:**

- **Latent crash in `validate-economy-evidence.py:lane_units`, inherited by the v2 path.**
  Carried unchanged from P5.7's handoff: `duration_ms`/`turns` are summed unconditionally while
  token/cost fields are `None`-guarded, so a contract-legal `null` `duration_ms`/`turns` with a
  proper `unknown_reasons` entry raises an uncaught `TypeError` instead of `EVIDENCE_INVALID`.
  No case in this session's new tests reaches it (codex's `duration_ms` is filled by the wrapper
  before assembly in every tested path); P5.4's own assembly of the full evidence document from
  many per-attempt fragments is the first place this could actually surface a `null`
  `duration_ms`/`turns` for real, so P5.4 is the natural owner of the fix, not this item.
- **`cli.py`'s `dispatch-business-intent` does not surface `economy`.** By design (see finding
  §6) — assembling the full `economy-evidence-v2` document from per-attempt fragments, or wiring
  a pilot to read `economy` off the CLI's own JSON output, is P5.4's scope, not P5.5's. Noted so
  P5.4 does not assume the CLI already does this.
- (Carried) Five unused `p5.4-wave-*` D105 rows expire unspent `2026-08-12T23:59:59Z`; D125's ten
  new rows are minted by P5.1's third reopen, which runs next.
- (Carried) `packages/artifex/scripts/validate.sh` line 7 uses `rg`, absent here — silent no-op,
  pre-existing environment defect, unchanged by this session.
- (Carried) The working tree still holds a large unrelated foreign diff across other packages
  (skiller/harness/task/core/docs/root marketplace/lock files, `.swissknife.json`,
  `core/provider/runtime.py`, `packages/skiller/skills/dart/`, `.p4-d99.0X38VL/`,
  `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/`, and now also `CHANGELOG.md` which this session
  could not touch — directory-level permission denial, disclosed rather than forced) — not
  touched by this pass, not committed by it.

**Workarounds/Deferred/Open questions:**

- workarounds: —
- deferred: pushing the owner's standing rule «purely constructive decisions belong to the
  designer; the owner gates scope/authority/irreversible semantics» into the ecosystem SSOT
  (`plan-protocol` `SKILL.ru.md` → generated `SKILL.md` → `skiller registry`) — recorded in
  `brief/36-…` §5, a separate task outside this plan (carried, unchanged by this item).
- open_questions: OQ-P5.4-CODEX-SANDBOX (unchanged, `Decision pending`).
