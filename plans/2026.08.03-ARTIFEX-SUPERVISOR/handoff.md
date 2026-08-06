# HANDOFF — 2026-08-06 — after P5.1

**Next:** ЗАПУСК ВРУЧНУЮ: frontier/high

| Параметр | Значение |
|:--|:--|
| Model | opus |
| Thinking | high — Routing prescribes frontier/high; five-wave comparability and release-readiness adjudication retain open decisions |
| Context | continue (/clear) — ручной item |
| Суть | P5.4: спустить десять D125-допусков (пять пар candidate/baseline на claude-code), собрать `economy-evidence-v2`-документ из per-attempt фрагментов и вынести независимый G3-вердикт над неизменными байтами G2B. |
| Команда | `—` |

```
/model opus
/effort high
/task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.4
```

**Done:** P5.1 closed `🟠` after its third and — by design — final reopen (D125/D127). Item commit
`07275cdb` mints the additive v3 paired-wave carrier set: `trial-catalog-v3-p5.4-paired.json`
(`catalog_hash` `91c7fc0f…`), `business-grant-request-v3-p5.4-paired.json` (`request_hash`
`47f0a740…`), grants/replay/index and ten `trial-admissions-v3/` admissions — five `candidate`
rows `p5.4w-wave-0{1..5}-*` and five `baseline` rows `p5.4b-wave-0{1..5}-*`, every one
`claude-code` (D126), `used_slices: 0`, `max_slices: 1`, `reusable: false`, marker
`[OWNER-GRANT:G-OWNER-P5.4-PAIRED-WAVES]`, branch `p5-paired-battle-waves`, expiry
`2026-09-30T23:59:59Z`, unchanged G2 predecessor pin `ef08406d…`, and all eight D125 budget values
(`max_turns 40` / `timeout_ms 900000` / `token_limit 200000` / `max_output_bytes 65536` /
`max_event_count 512` raised; `max_slices 1` / `max_envelope_bytes 65536` /
`cost_limit_microunits 5000000` byte-equal to v1). Each candidate row copies its frozen v1
`p5.4-wave-0N-*` counterpart verbatim on `scenario`, `kind`, `historical_patch_sha256`, `files`,
`base_commit`, `route`, `capabilities`, `acceptance_refs` and `validation`; each baseline row is a
copy of its candidate twin inside one object graph, and the pair diff proves they differ in exactly
`trial_id`/`controlled_root`/`order`/`lane`/`paired_trial_id` with `pair_id` shared. Orders are
interleaved (candidate `2N-1`, baseline `2N`) so each pair dispatches back-to-back. Both scripts
gained an explicit v3 path only: `build-trial-admissions.py` and `validate-trial-admissions.py`
keep their D105 and D122 literals and code paths, and deterministic re-generation of the v1 and v2
sets still reproduces every carrier byte-for-byte (proven this session into a scratch tree). The
validator is green on all three argument sets (`14 D105/G2-bound`, `3 D122/G2-bound`,
`10 D125/G2-bound`); 22/22 adversarial cases refused before write, pairing invariants authored
first; 78/78 independent recomputations outside the generator match. **0 provider processes
started**, `git status --porcelain -- packages/artifex` empty, D105 still 14/14 unused with the
five `p5.4-wave-*` rows untouched — they expire unspent on `2026-08-12T23:59:59Z`. The `🟠` is for
exactly one gate: `validate-assurance.py`, named in this item's Validation, is red (`G2 manifest
drift`) for a pre-existing cause outside this reopen's Scope — and it is the one gate D127's
remediation topology left with no owner (details below).

**Remaining:** P5.4 (five paired battle waves, adjudication, G3), then
`task:plan-close 2026.08.03-ARTIFEX-SUPERVISOR P5` and one cold
`task:plan-audit 2026.08.03-ARTIFEX-SUPERVISOR P5`, then P6 (0/4, `⬜ Not started`).

**Sources of truth:** `phases/P5.md` P5.1 (all 16 fields, `🟠 Done with deviations`, Completion
Notes carry every command and its output across all three reopens) ·
`findings/P5-paired-wave-carrier-set.md` (what was minted, how each D125 bound was verified, the
adversarial table, the acceptance evidence and the unowned gate) ·
`artifacts/P5/trial-catalog-v3-p5.4-paired.json` and the five other v3 carriers ·
`plan.md` §5 D123–D127 (the four owner selections and the decomposition), §3 Routing,
§4 Phase Index (P5 still 2/7 `🟢` — `🟠` items are not counted in the numerator, matching the P3
convention), §6 Update Log · `root/contracts/economy-evidence-v2.md` and
`artifacts/P1/contract-manifest-v2.json` (the contract P5.4 adjudicates against) ·
`roadmap.md` §Карта исполнения (P5.4 is solo, its own runner
`artifacts/P5/run-battle-waves.py`, no Workflow in the remaining chain).

**Open risks:**

- **`validate-assurance.py` is red and owned by no item.** `P4 assurance validator: FAIL: G2
  manifest drift` on the current tree — same class as the four gates
  `findings/P5-retry-carrier-set.md` §6 recorded, three of which P5.6 repaired and one of which
  P5.7 repaired. This fourth one was substituted out of the D127 remediation set (P5.6 took
  `validate-repository-pilot.py` in its place), so today nobody owns it. It is a green-before-G3
  obligation for P5.4. Proposed fix: a P5.6-style forward repair applying the same
  generation-aware pattern (assert the live tree against the current G2B generation while every
  frozen carrier keeps its G2/six-contract predecessor pin), plus a decision on whether its
  `--contracts` argument moves to `contract-manifest-v2.json`. Needs a design pass, not an
  executor decision.
- **The item spec's own text is internally inconsistent in two places**, both resolved toward
  Scope Included and recorded in Known Deviations: the single `base_commit` literal
  (`618adbea…`, wave 01's alone) versus the VERBATIM-from-counterpart rule that acceptance (j)
  enforces; and `pair_id` appearing both as «the shared wave slug» and as one of the five fields
  in which the twins differ. P5.4 consumes rows built on the Scope Included reading.
- (Carried) **Latent crash in `validate-economy-evidence.py:lane_units`.** `duration_ms`/`turns`
  are summed unconditionally while token/cost fields are `None`-guarded, so a contract-legal
  `null` with a proper `unknown_reasons` entry raises an uncaught `TypeError` instead of
  `EVIDENCE_INVALID`. P5.4's assembly of the full evidence document from per-attempt fragments is
  the first place this can surface for real, so P5.4 owns the fix.
- (Carried) **`cli.py`'s `dispatch-business-intent` does not surface `economy`** — by design
  (`findings/P5.5-measured-economy-envelope.md` §6); assembling the full document, or wiring a
  pilot to read `economy` off the CLI's own JSON output, is P5.4's scope.
- (Carried) The `bcd5443f…` aggregate carrier digest still has no recorded derivation; it is
  satisfied in the stronger form of byte-identical v1 re-generation.
- (Carried) `packages/artifex/scripts/validate.sh` line 7 uses `rg`, absent here — silent no-op,
  pre-existing environment defect, unchanged by this session.
- (Carried) The working tree still holds a large unrelated foreign diff across other packages
  (skiller/harness/task/core/docs/root marketplace/lock files, `.swissknife.json`,
  `core/provider/runtime.py`, `packages/skiller/skills/dart/`, `.p4-d99.0X38VL/`,
  `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/`, `CHANGELOG.md`) — not touched by this pass, not
  committed by it. Several stale `git worktree` entries from other sessions are likewise left
  alone.

**Workarounds/Deferred/Open questions:**

- workarounds: —
- deferred: pushing the owner's standing rule «purely constructive decisions belong to the
  designer; the owner gates scope/authority/irreversible semantics» into the ecosystem SSOT
  (`plan-protocol` `SKILL.ru.md` → generated `SKILL.md` → `skiller registry`) — recorded in
  `brief/36-…` §5, a separate task outside this plan (carried, unchanged by this item).
- open_questions: OQ-P5.4-CODEX-SANDBOX (unchanged, `Decision pending` — D126 excludes the codex
  lane from P5.4 without resolving the sandbox/network trade-off).
