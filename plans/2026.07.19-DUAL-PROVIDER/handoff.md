# HANDOFF — 2026-07-20 — after P3.3

**Next:** ЗАПУСК ВРУЧНУЮ: gpt-5.6-terra/high

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | high — provider distribution and repair boundary |
| Context | continue (/clear) — ручной item |
| Суть | Execute P3.4 only: providerize distribution flows over the completed Claude and Codex projections. |

```text
Execute only P3.4 of plan 2026.07.19-DUAL-PROVIDER on gpt-5.6-terra/high.

First read AGENTS.md, CLAUDE.md, plans/2026.07.19-DUAL-PROVIDER/plan.md,
handoff.md, phases/P3.md, then all P3.4 Required Reads strictly in their listed order.
P3.3 is terminal at item commit 302a5f0: native Codex marketplace, direct bucket plugins,
cache-contained core/skm bundles, locks and focused conformance exist. Preserve all unrelated
owner dirt. Execute only P3.4 Files/Scope; do not start P3.5+, alter P3.1 frozen contracts,
install or enable plugins, write user-global Codex state, touch the current root .agents/skills,
or touch FOREMAN/fleet.

Use the P1 resolver and P2 immutable plan/apply boundary. Keep native installation explicit,
separate from ordinary render/check/doctor/update, and prove no implicit subprocess or user-global
write through temp-root tests. Follow the full item lifecycle: journal, validation, two commits,
plan status and handoff.
```

**Done:** P3.3 added the independent native Codex publication renderer at item commit `302a5f0`.
It emits direct bucket/meta manifests, a contained repo marketplace, and self-contained `core`/
`skm` cache bundles with deterministic locks. Claude golden compatibility remains covered.

**Remaining:** P3.4–P3.5, then independent P3 audit G03 before P4.1.

**Sources of truth:** `phases/P3.md` P3.3–P3.4 · frozen
`root/contracts/provider-skill-publication-contract.md` · `packages/skiller/lib/skiller/publication.py`
· P3.3 item commit `302a5f0`.

**Open risks:** The static `codex doctor --json` model/effort ambiguity remains D56 non-green
but non-blocking under D72. Unrelated owner dirt remains intentionally unstaged. `plan-lint`
retains two documented P3 DoR false-positive warnings; P3.3 added no plan errors.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: provider distribution/install/update flows are P3.4.
- open_questions: —
