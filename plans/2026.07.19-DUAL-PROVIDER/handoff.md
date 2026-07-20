# HANDOFF — 2026-07-20 — after P3.1

**Next:** `/task:plan-exec 2026.07.19-DUAL-PROVIDER P3.2`

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | medium — deterministic Claude compatibility refactor |
| Context | continue (/clear) — ручной item |
| Суть | Execute P3.2 only: extract the immutable semantic publication catalog and preserve Claude output bytes. |

```text
Execute only P3.2 of plan 2026.07.19-DUAL-PROVIDER on gpt-5.6-terra/medium.

First read AGENTS.md, CLAUDE.md, plans/2026.07.19-DUAL-PROVIDER/plan.md,
handoff.md, phases/P3.md, then P3.2 Required Reads strictly in their listed order.
P3.1 is terminal: D77 froze provider-skill-publication-contract v1.0.0 at item commit
2b5fbbe. Preserve all unrelated owner dirt. Execute only P3.2 Files/Scope; do not start
P3.3+, alter generated outputs except through the declared P3.2 renderer path, perform
native install/live writes, or touch FOREMAN/fleet.

Keep the frozen D77 contract and current Claude marketplace/plugin bytes, names, ordering,
source paths, and enabledPlugins semantics as hard compatibility gates. Build the catalog and
Claude renderer from explicit immutable inputs; do not add Codex paths/tokens, discovery,
global registration, or provider-manifest conversion. Follow full item lifecycle: journal,
validation, two commits, plan status, and handoff.
```

**Done:** P3.1 is terminal. D77 records the exact Owner approval and freezes
`root/contracts/provider-skill-publication-contract.md` v1.0.0. The approved review records
the S1–S6 alternatives/verdict; no package/runtime artifact, native install, live configuration,
FOREMAN, fleet, or owner-owned file changed.

**Remaining:** P3.2–P3.5, then independent P3 audit G03 before P4.1.

**Sources of truth:** `phases/P3.md` P3.1/P3.2 · D77 and Contracts in `plan.md` · frozen
`root/contracts/provider-skill-publication-contract.md` ·
`artifacts/P3-skill-publication-contract-review.md` · item commit `2b5fbbe`.

**Open risks:** The static `codex doctor --json` model/effort ambiguity remains D56 non-green
but non-blocking under D72. Unrelated owner dirt remains intentionally unstaged. P3.2 must retain
Claude byte compatibility and must not pull Codex concerns forward from P3.3. `plan-lint` reports
two P3 DoR false-positive warnings after the phase enters `🟡`; P3.1 records a scoped remediation
proposal but has no ERROR and does not alter the task linter.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: native Codex manifests/bundles are P3.3; distribution/install/update flows are P3.4.
- open_questions: —
