# HANDOFF — 2026-07-20 — after P3.2

**Next:** ЗАПУСК ВРУЧНУЮ: gpt-5.6-terra/high

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | high — native Codex marketplace contract |
| Context | continue (/clear) — ручной item |
| Суть | Execute P3.3 only: add a native Codex projection over the frozen semantic catalog. |

```text
Execute only P3.3 of plan 2026.07.19-DUAL-PROVIDER on gpt-5.6-terra/high.

First read AGENTS.md, CLAUDE.md, plans/2026.07.19-DUAL-PROVIDER/plan.md,
handoff.md, phases/P3.md, then all P3.3 Required Reads strictly in their listed order.
P3.1 is terminal at D77. P3.2 is terminal at item commit 28dc93e: its immutable semantic
catalog and named Claude renderer preserve the pre-refactor Claude byte golden. Preserve all
unrelated owner dirt. Execute only P3.3 Files/Scope; do not start P3.4+, alter current Claude
artifacts, install or enable any plugin, write user-global Codex state, or touch FOREMAN/fleet.

Use the same catalog without provider-manifest conversion. Follow frozen native Codex contract,
cache containment, explicit bundle allowlists and provenance/lock rules. Keep Codex outputs
generated and non-canonical; no raw copytree and no copying SKILL.ru.md/evals/upstream service
files. Follow the full item lifecycle: journal, validation, two commits, plan status and handoff.
```

**Done:** P3.1 frozen publication contract v1.0.0 is unchanged. P3.2 added the package-owned
immutable semantic catalog and P2-backed Claude renderer at item commit `28dc93e`; the pre-refactor
aggregate byte golden, focused tests, package validation and `registry --check` passed. Current
Claude marketplace/plugin bytes, names, ordering, paths and `enabledPlugins` semantics are unchanged.

**Remaining:** P3.3–P3.5, then independent P3 audit G03 before P4.1.

**Sources of truth:** `phases/P3.md` P3.1–P3.3 · D77 and Contracts in `plan.md` · frozen
`root/contracts/provider-skill-publication-contract.md` · P2 artifact conformance · P3.2 item
commit `28dc93e` and `packages/skiller/lib/skiller/publication.py`.

**Open risks:** The static `codex doctor --json` model/effort ambiguity remains D56 non-green
but non-blocking under D72. Unrelated owner dirt remains intentionally unstaged. `plan-lint`
retains two documented P3 DoR false-positive warnings; P3.2 added no plan errors. P3.3 must keep
the Claude golden unchanged while adding only declared native Codex artifacts.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: distribution/install/update flows are P3.4.
- open_questions: —
