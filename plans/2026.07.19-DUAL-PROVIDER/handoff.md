# HANDOFF — 2026-07-20 — after P2.3

**Next:** `/task:plan-exec 2026.07.19-DUAL-PROVIDER P2.4`

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | medium — deterministic synthetic conformance |
| Context | continue (/clear) — ручной item |
| Суть | Выполнить только P2.4 synthetic E2E/doctor/no-write conformance поверх committed P2.1–P2.3 APIs. |

```text
/task:plan-exec 2026.07.19-DUAL-PROVIDER P2.4
```

**Done:** P2.3 terminal `🟢 Done`; item commit `35105f1` introduces `core.provider_registry` with
caller-built immutable descriptors, deterministic duplicate/unknown/unsupported diagnostics,
frozen capability gates, declared-native-extension isolation, and selected identity propagation
through P2.1 render and P2.2 lock values. Focused registry suite and full core suite are green.

**Remaining:** P2.4 only, then terminal P2 phase close and independent audit. P3+ remains out of
scope; package-specific adapter integration, live configs, FOREMAN and fleet remain prohibited.

**Sources of truth:** `phases/P2.md` P2.1–P2.4 · D16–D18/D75 in `plan.md` · frozen
`root/contracts/provider-{capability,artifact,config,migration-gates}.md` ·
`root/adr/ADR-0002-provider-artifact-kernel.md` · commits `0dfdcd6`, `7035a63`, `35105f1` ·
`journal.jsonl`.

**Open risks:** Static `codex doctor --json` route/effort ambiguity remains D56 non-green but
non-blocking under D72. Unrelated owner dirt remains intentionally unstaged. Managed-block
application still fails closed without an explicit caller extractor; P2.4 must not invent
marker grammar before the owning instruction phase.

**Workarounds/Deferred/Open questions:**

- workarounds: managed-block apply is intentionally refused until its owning phase supplies an explicit extractor/replacer.
- deferred: P2.4 conformance/doctor, then all package/provider delivery.
- open_questions: —
