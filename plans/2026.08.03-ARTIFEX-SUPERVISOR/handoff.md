# HANDOFF — 2026-08-06 — after P5.3

**Next:**

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — per §3 Routing, P5.4 is `implementation/high`, `Exec = manual`; current session route matches exactly |
| Context | continue (/clear) — ручной item |
| Суть | Run five predeclared paired battle waves (candidate vs. incumbent) over the terminal G2B successor, prove reliability/parity/intervention/economy floors, and produce an independent GO/NO-GO readiness verdict — the last P5 item before `plan-close ... P5` and a cold `plan-audit ... P5`. |
| Команда | `/task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.4` |

**Done:** P5.3 closed `🟠 Done with deviations` (item commit `3c05ba71`). Ran all six real,
one-shot D105 admissions (`p5.3-call-01`..`06`) through the exact journal-free P5.2 business seam,
proving crash-after-intent, crash-after-observation, duplicate-dispatch, provider-timeout,
schema-refusal and unknown-third-state recovery — the live-provider composition class P4's
fully-controlled fault harness could never exercise. Before spending any admission, the
plan-unspecified crash-injection mechanism (a `/proc`-based poll-until-condition kill/orphan
technique invented for this item, since the business seam has no exposed cut-points and
`packages/artifex/**` is out of Files) was surfaced to the owner via `AskUserQuestion`; the owner
delegated ("идеальный пакет") and the executor chose to self-test synthetically and dry-run
against the real seam with fake, zero-cost binaries first — this caught and fixed two real bugs
(an unobservable zombie-detection window; a `TemporaryDirectory` that would have destroyed the
one preserved-worktree trial) before either could waste a real admission. Full narrative:
`findings/P5-recovery-pilot.md`.

**Remaining:** P5.4 (the only remaining P5 item), then `task:plan-close ... P5` and one cold
`task:plan-audit ... P5`, then P6 (umbrella packaging/ops, currently `⬜ Not started`, 0/4).

**Sources of truth:** `findings/P5-recovery-pilot.md` (full mechanism/root-cause narrative) ·
`phases/P5.md` P5.3 (Completion Notes/Pending Work/Known Deviations) · `plan.md` §6 Update Log ·
`artifacts/P5/recovery-pilot-results-v1.json` (7 rows: 6 catalogued + 1 duplicate-refusal) ·
`artifacts/P5/run-recovery-pilot.py` (harness, not in this item's `Files` — see Known Deviations)
· `artifacts/P5/validate-recovery-pilot.py` · item commit `3c05ba71`.

**Open risks:**

- **`validate-repository-pilot.py` (terminal P5.2's own validator) is RED on the current tree** —
  `g2b_generation_hash` stale against the live (fourth) G2B freeze; P5.2's own results file was
  pinned to the third freeze before this session's later root-cause fix re-froze G2B again.
  Out of P5.3's Scope/Files to fix. Remediation proposal (a small P5.2-scoped slice re-run, or
  fold into P5.4's consolidated fan-in): `findings/P5-recovery-pilot.md` §6. Same shared root
  cause (D108/D118–119 package divergence from G2) as the four gates below; P5.4 should confirm
  whether its own consolidated fan-in already subsumes this or whether it needs a named
  fix-item first.
- Four frozen gates stay red on the current tree, same shared cause, unchanged this pass:
  `validate-shadow.py`, `validate-assurance.py`, `validate-package-promotion.py`,
  `validate-contract-set.py`. None blocks P5.3/P5.4; all are green-before-G3 obligations for
  P5.4's own consolidated fan-in.
- **`max_turns: 8` budget** — still tight for genuine multi-file claude-code work (unchanged
  from P5.2's finding); a new owner grant may be needed before P5.4's battle waves can complete
  multi-file edits reliably in one dispatch.
- **codex sandbox vs. network isolation trade-off** (carried from P5.2, unchanged) — open owner
  decision, not P5.3's or P5.4's to make unilaterally.
- (Carried forward, P4-owned) `git diff --exit-code 124df816 -- phases/P4.md artifacts/P4` red,
  unchanged.
- (Carried forward) `packages/artifex/scripts/validate.sh` line 7 uses `rg`, absent here — silent
  no-op, inherited environment defect.
- D105 stays 14/14 unused (P5.3 spent zero D105 rows — its own six admissions are a separate,
  already-exhausted set with distinct `trial_id`s, `p5.3-call-01`..`06`, all one-shot spent this
  pass); expiry `2026-08-12T23:59:59Z` unchanged for the remaining fourteen.
- В рабочем дереве по-прежнему лежит чужой незакоммиченный дифф по другим пакетам
  (skiller/harness/task/core/docs/root marketplace/lock-файлы, `.swissknife.json`,
  `core/provider/runtime.py`, `packages/skiller/skills/dart/`, `.p4-d99.0X38VL/`,
  `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/`) — не субъект этого захода, не трогался (unchanged
  from prior handoff).

**Workarounds/Deferred/Open questions:**

- workarounds: this session's crash-injection mechanism (`/proc`-based poll-until-condition
  kill/orphan detection) was invented for this item under explicit owner delegation, since no
  existing package hook exists for it and `packages/artifex/**` is out of P5.3's Files — recorded
  as a Known Deviation (undeclared harness script, same category as P5.2's `run-pilot.py`), not
  silent scope drift.
- deferred: `validate-repository-pilot.py` staleness fix; the four red frozen gates; `max_turns`
  grant question; codex sandbox/network trade-off decision; the P4-owned evidence-diff anchor
  reconciliation; P5.4; P6; чужой грязный рабочий дифф.
- open_questions: — (all raised as explicit forwarded decisions above, not silent gaps).
