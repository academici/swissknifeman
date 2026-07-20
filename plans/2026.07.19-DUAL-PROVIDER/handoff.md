# HANDOFF — 2026-07-20 — after P2.1

**Next:** ЗАПУСК ВРУЧНУЮ: `gpt-5.6-terra/high`

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | high — managed-boundary safety semantics |
| Context | continue (/clear) — ручной item |
| Суть | Реализовать P2.2 lock/drift/apply API поверх terminal P2.1 artifact kernel. |

```text
Продолжай только P2.2 плана 2026.07.19-DUAL-PROVIDER на gpt-5.6-terra/high.

Сначала прочитай AGENTS.md, CLAUDE.md, packages/task/commands/plan-exec.md, затем
plans/2026.07.19-DUAL-PROVIDER/plan.md, handoff.md, phases/P2.md и все P2.2 Required Reads
строго в указанном порядке. P2.1 terminal: D75 accepted K1-K6; item commit 0dfdcd6 added
core.provider_artifact. Preserve all unrelated owner dirt. Execute only P2.2; do not touch
P2.3+, package-specific integration, live configs, FOREMAN, fleet, or user files.

Implement the frozen lock/drift contract fail-closed: planning is no-write, apply receives
only an explicit target root plus precomputed plan, and every write stays under TemporaryDirectory
in tests. Do not auto-adopt, force, recursively discover, or delete outside declared managed entries.
```

**Done:** P2.1 is terminal `🟢 Done`: D75 accepted K1–K6, and item commit `0dfdcd6`
added the pure `core.provider_artifact` kernel, explicit exports, accepted contribution proposal,
accepted ADR-0002, and focused deterministic/provenance/path conformance tests.

**Remaining:** P2.2 → P2.3 → P2.4 remain strictly sequential. P2.2 owns lock, drift,
explicit apply, repair, and atomic containment semantics; no package or live-target integration
is open yet.

**Sources of truth:** `phases/P2.md` P2.1/P2.2 · D75 in `plan.md` ·
`root/contracts/provider-artifact-contract.md` v1.0.0 · accepted
`artifacts/P2-core-contribution-proposal.md` · accepted
`root/adr/ADR-0002-provider-artifact-kernel.md` · item commit `0dfdcd6` · `journal.jsonl`.

**Open risks:** Static `codex doctor --json` route/effort ambiguity remains D56 non-green but
non-blocking under D72. Current target plan-lint has no errors; any residual warnings must be
baseline-attributed at P2.2 close. Unrelated owner dirt remains intentionally unstaged.

**Workarounds/Deferred/Open questions:**

- workarounds: —
- deferred: locks/drift/apply/repair (P2.2), catalog (P2.3), synthetic E2E/doctor (P2.4), and all package/provider delivery remain deferred.
- open_questions: —
