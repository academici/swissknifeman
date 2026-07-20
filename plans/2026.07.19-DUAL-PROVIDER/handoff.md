# HANDOFF — 2026-07-20 — after P2.2

**Next:** ЗАПУСК ВРУЧНУЮ: `gpt-5.6-sol/high`

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-sol |
| Thinking | high — capability catalog contract decision |
| Context | continue (/clear) — ручной item |
| Суть | Реализовать только P2.3 immutable capability-aware adapter registry поверх terminal P2.1/P2.2 APIs. |

```text
Продолжай только P2.3 плана 2026.07.19-DUAL-PROVIDER на gpt-5.6-sol/high.

Сначала прочитай AGENTS.md, CLAUDE.md, packages/task/commands/plan-exec.md, затем
plans/2026.07.19-DUAL-PROVIDER/plan.md, handoff.md, phases/P2.md и все P2.3 Required Reads
строго в указанном порядке. P2.1 terminal: D75 and item commit 0dfdcd6. P2.2 terminal:
item commit 7035a63 adds core.provider_lock fail-closed lock/drift/explicit-apply API.

Execute only P2.3. Preserve unrelated owner dirt. Do not touch P2.4+, package-specific
integration, live configs, FOREMAN, fleet, or user files. Implement only the frozen explicit
immutable catalog; no discovery, globals, package imports, environment/cwd selection, or
provider-name branching. Stop only for an actual frozen-contract/authority gap.
```

**Done:** P2.1 and P2.2 are terminal `🟢 Done`. P2.2 item commit `7035a63` provides canonical
v1 artifact-lock serialization, deterministic fail-closed drift planning, explicit-root atomic
apply, explicit repair backup and TemporaryDirectory conformance tests.

**Remaining:** P2.3 → P2.4 remain strictly sequential. P2.3 consumes the terminal artifact and
lock APIs to create a capability-aware immutable catalog; P2.4 then provides the synthetic E2E
conformance/doctor evidence. Package and live-target integration remain out of scope.

**Sources of truth:** `phases/P2.md` P2.1–P2.3 · D16–D18/D75 in `plan.md` · frozen
`root/contracts/provider-{capability,artifact,config,migration-gates}.md` ·
`root/adr/ADR-0002-provider-artifact-kernel.md` · commits `0dfdcd6` and `7035a63` ·
`journal.jsonl`.

**Open risks:** Static `codex doctor --json` route/effort ambiguity remains D56 non-green but
non-blocking under D72. Unrelated owner dirt remains intentionally unstaged. Managed-block
application requires an explicit caller extractor and currently fails closed, rather than
inventing marker grammar before P5 instruction semantics.

**Workarounds/Deferred/Open questions:**

- workarounds: managed-block apply is intentionally refused until its owning phase supplies an explicit extractor/replacer.
- deferred: capability catalog (P2.3), synthetic E2E/doctor (P2.4), and all package/provider delivery.
- open_questions: —
