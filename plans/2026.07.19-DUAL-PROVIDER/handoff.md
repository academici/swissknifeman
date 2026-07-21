# HANDOFF — 2026-07-21 — after P3

**Next:** `/task:plan-run 2026.07.19-DUAL-PROVIDER P3.4`

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | high |
| Context | fresh — bounded D80 repair |
| Суть | Repair all known P3.4 vendor fail-closed gaps once, then hand off P3.5. |

```text
Execute only the D80 P3.4 bundled repair of plan 2026.07.19-DUAL-PROVIDER on gpt-5.6-terra/high.

First read AGENTS.md, CLAUDE.md, packages/task/commands/plan-exec.md, then
plans/2026.07.19-DUAL-PROVIDER/plan.md, handoff.md, phases/P3.md and every P3.4
Required Read strictly in its listed order. Read research/19 before code. P3.4 historical
implementation and D78 repair are preserved; implement only the additional D80 bundle.

Preserve unrelated owner dirt. Do not change P3.1 frozen contracts, P3.5 implementation,
P4+, live Codex user-global state, current root .agents/skills, FOREMAN or fleet. Use temporary
roots for all tests. Keep the existing resolver, skill lock grammar and --force ownership path;
do not add a public module, a new command, or provider-specific selection code. Implement only
the research/19 matrix: pre-write selected-provider conflict/drift/provenance refusal, source
staleness distinction, and explicit --repair with pre-image plus observed/expected/source hashes.
Run only targeted regressions/static checks under D80; do not run or claim phase-wide validation.
Commit scoped code, then plan bookkeeping, and hand off P3.5.
```

**Done:** P3.4 D78 repair at `c367335` evaluates every selected provider's `plan_sync()`
conflicts before any provider apply. An unmanaged Codex target now emits qualified
`SPUB_OWNERSHIP_CONFLICT` before Claude/Codex skill writes, lock writes or registration;
the separate post-preflight provider-B copy-failure/repair proof remains green. `c27f679`
records the fix in the changelog.

**Remaining:** D80 P3.4 bundle, P3.5, then one full P3 validation/close and independent P3 audit G03 before P4.1.

**Sources of truth:** `phases/P3.md` P3.5; frozen
`root/contracts/provider-skill-publication-contract.md`; `packages/skiller/lib/skiller/{publication,registry,connect,skillset,update,doctor}.py`; P3.4 item commits `c367335` and `c27f679`.

**Open risks:** Existing plan-lint warnings are documented P3 DoR marker/orchestration false
positives. The D80 repair must not treat source staleness as local drift, overwrite a corrupt
lock, or use --force as an implicit repair. P3.5 must independently assert all outcomes.
This is a schedule recovery after repeated P3.4 re-open: D81 requires the next status to name
the blocked/executable state explicitly and to report any renewed schedule impact proactively.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: P3.5/full P3 validation/audit follow the D80 repair.
- open_questions: none.
