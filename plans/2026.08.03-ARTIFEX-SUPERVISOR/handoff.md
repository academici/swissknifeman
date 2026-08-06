# HANDOFF — 2026-08-06 — after P5.2

**Next:**

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | high — per §3 Routing, P5.3 is `implementation/high`, `Exec = manual`; current session route matches exactly |
| Context | continue (/clear) — ручной item |
| Суть | Run the P5.3 crash/resume/duplicate/provider-failure pilot over exact P4 cut identities against the same catalogued task/base, through fresh processes, proving no-rerun reconcile. The claude-code business path should now actually be able to write real edits (dontAsk allow-list fix landed); codex's own sandbox limitation (below) is unresolved. |
| Команда | `/task:plan-run 2026.08.03-ARTIFEX-SUPERVISOR P5.3` |

**Done:** P5.2 closed `🟠 Done with deviations` (commits `842c5d18` escalation → `6755be6b`
seam/`load_indexed` fix → `69b03ecf` D122 re-run execution → `7f38e296` bookkeeping). Then, owner-
directed live in this same session, a full root-cause investigation of the `PROVIDER_PROTOCOL_UNKNOWN`
pattern (RAG via `perplexity-web` + disposable-worktree live diagnostics, zero D105/D122 grants
touched) found and fixed two real bugs (commit `6b9afc9b`):
1. **claude-code's real blocker.** `--permission-mode dontAsk` auto-denies any tool call absent
   from a *separate* `--allowedTools` list — `--tools` only declares availability.
   `build_business_argv` never passed `--allowedTools`; without it, every real Edit call was
   silently denied regardless of budget (live-proven: a real dispatch returned "Blocked by
   tooling: Edit is denied in dontAsk mode"). Fixed (`--allowedTools Read,Edit`, identical to
   `--tools`, nothing widened) — a live dispatch then produced a real edit to `scheduler.py`
   (+37 lines).
2. **Two independent parsing gaps**, also fixed: codex's `ALLOWED_EVENTS` lacked `item.started`
   (real multi-step work legitimately emits it — 13 such events in one successful 369-line live
   dispatch); claude-code's `_RESULT_KEYS` lacked `errors` (emitted on `error_max_turns`).

3 new unit tests lock both fixes in; package suite 103/103 green; G2B re-frozen a fourth time
(`generation_hash` now `61d9e34c2e0e51dbf69f0bbb328f6d81994bbbfb3e0a8e78ca2fee05403276d4`, 0 new
provider processes). Full detail: `findings/P5-repository-pilot.md` §8.

**Remaining:** Explicitly scoped by the owner this session: the claude-code path was this
session's priority; **codex's own path is deliberately left for its own future self-testing pass**,
not further hardened here. Two open items forwarded, neither fixed:
- `max_turns: 8` is still tight for a genuine multi-file edit (the fixed claude-code dispatch still
  exhausted it) — a frozen D105/D122 catalog value; raising it needs a new owner grant, same class
  as D122's `timeout_ms` raise.
- codex's own sandbox (`bwrap`) cannot get network-namespace capabilities in this nested
  environment (`RTM_NEWADDR: Operation not permitted`, a documented AppArmor/userns restriction).
  The official `--dangerously-bypass-approvals-and-sandbox` escape hatch verifiably fixes it
  (live-proven: a real 369-line write), but this host has real outbound network access, so
  adopting it trades away the `network-disabled`/`SEC-WORKTREE` guarantee — a genuine security
  decision, not adopted, left open for codex's own future pass.

P5 `0/5` 🟢 (P5.1/P5.5/P5.2 all `🟠`, P5.3/P5.4 `⬜`) — execution order **P5.3 → P5.4**, then P6.

**Sources of truth:** `findings/P5-repository-pilot.md` §7 (D122 re-run) + §8 (root-cause/fixes) ·
`findings/P5.2-v2-admission-not-indexed-2026-08-06.md` (F1–F4) · `phases/P5.md` P5.2 (Completion
Notes/Pending Work, this pass) · `plan.md` §6 Update Log ·
`packages/artifex/lib/artifex/providers/{claude_code.py,codex.py}` (the two fixes) ·
`packages/artifex/lib/artifex/business_dispatch.py` (`GRANT_BATCHES`) ·
`plans/2026.08.03-ARTIFEX-SUPERVISOR/artifacts/P5/business-successor-generation-v1.json` +
`business-successor-assurance-v1.json` (four-times-frozen, current) · commits `842c5d18`,
`6755be6b`, `69b03ecf`, `7f38e296`, `6b9afc9b`.

**Open risks:**

- **codex sandbox vs. network isolation trade-off** (above) — open owner decision, not this
  session's to make; P5.3/P5.4 should not assume codex slices will succeed until it's resolved.
- **`max_turns: 8` budget** (above) — a new owner grant may be needed before claude-code slices in
  P5.3/P5.4 can realistically complete multi-file work in one dispatch.
- Four frozen gates stay red on the current tree, one shared cause (D108's additive seventh
  contract and D118/D119's deliberate package divergence from G2), unchanged this pass:
  `validate-shadow.py`, `validate-assurance.py`, `validate-package-promotion.py`,
  `validate-contract-set.py`. None blocks P5.2/P5.3; all are green-before-G3 obligations for P5.4.
- (Carried forward, P4-owned) `git diff --exit-code 124df816 -- phases/P4.md artifacts/P4` red,
  unchanged.
- (Carried forward) `packages/artifex/scripts/validate.sh` line 7 uses `rg`, absent here — silent
  no-op, inherited environment defect.
- D105 stays 14/14 unused, expiry `2026-08-12T23:59:59Z` unchanged. D122's three replacement rows
  are spent (real dispatches occurred for all three) — no further attempt possible against these
  exact admissions; the fixes landed too late to help them, but should help P5.3/P5.4's own D105
  rows.
- В рабочем дереве по-прежнему лежит чужой незакоммиченный дифф по другим пакетам
  (skiller/harness/task/core/docs/root marketplace/lock-файлы, `.swissknife.json`,
  `core/provider/runtime.py`, `packages/skiller/skills/dart/`, `.p4-d99.0X38VL/`,
  `plans/2026.08.02-PROVIDER-CONTRACT-LOCALE/`) — не субъект этого захода, не трогался.

**Workarounds/Deferred/Open questions:**

- workarounds: this session's `packages/artifex` fixes were made directly by the P5.2 executor
  under explicit, live owner instruction, overriding the normal P5.5-exclusive routing ceremony —
  recorded as Known Deviations, not silent scope drift.
- deferred: codex sandbox/network trade-off decision; `max_turns` grant question; the four red
  frozen gates; the P4-owned evidence-diff anchor reconciliation; P5.4; P6; чужой грязный рабочий
  дифф.
- open_questions: — (both raised as explicit forwarded decisions above, not silent gaps).
