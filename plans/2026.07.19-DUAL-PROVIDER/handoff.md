# HANDOFF — 2026-07-21 — after P3.3

**Next:** `/task:plan-exec 2026.07.19-DUAL-PROVIDER P3.5`

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | medium |
| Context | continue (/clear) — ручной item |
| Суть | Rerun only the independent P3.5 inventory/channel parity proof against D83's committed clean-tree Codex cache/lock repair. |

```text
Execute only P3.5 of 2026.07.19-DUAL-PROVIDER on gpt-5.6-terra/medium.

Read plan.md, handoff.md, phases/P3.md P3.5, then every P3.5 Required Read in order.
D83 P3.3 is committed at f947d77: the clean-worktree Codex core cache/lock regeneration and
focused catalog-vs-cache regression are green. Rerun P3.5's independent inventory/channel parity
evidence without changing fixtures or expected data. Do not modify P3.3, frozen contracts, Claude
outputs, provider selection/distribution, root .agents/skills, P4+, FOREMAN, fleet, user-global
state, or unrelated owner dirt. Do not run terminal P3 validation, G03, or create a PR; after the
P3.5 item closes, hand off only the terminal P3 close/audit route.
```

**Done:** D83 P3.3 repair commit `f947d77` regenerated the stale Codex `core` `plan-protocol`
cache member and `publication-lock.json` from the committed catalog, with a focused regression.

**Remaining:** independent P3.5 rerun → one terminal P3 validation and clean-tree registry check
→ fresh G03. A P1–P3 review PR and P4 remain prohibited until literal GREEN.

**Sources of truth:** `phases/P3.md` P3.3/P3.5 and Audit P3; D83 in `plan.md`;
`research/21-p3-codex-core-registry-remediation.md`; frozen
`root/contracts/provider-skill-publication-contract.md`; `packages/skiller/lib/skiller/{publication,registry}.py`.

**Open risks:** D83 evidence is targeted by D80; only the terminal P3 sequence may claim
phase-wide validation or an audit verdict.

**Workarounds/Deferred/Open questions:**

- workarounds: none; `registry --check` remains the drift gate.
- deferred: terminal P3 validation/G03, P1–P3 review PR and P4.
- open_questions: none.
