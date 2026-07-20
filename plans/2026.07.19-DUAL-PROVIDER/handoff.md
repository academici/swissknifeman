# HANDOFF — 2026-07-20 — after P3.4

**Next:** /task:plan-exec 2026.07.19-DUAL-PROVIDER P3.5

| Параметр | Значение |
|:--|:--|
| Model | gpt-5.6-terra |
| Thinking | medium — deterministic independent inventory/parity conformance |
| Context | fresh — P3.5 is plan-exec routed |
| Суть | Execute only P3.5 and independently prove the complete Claude/Codex publication matrix. |

```text
Execute only P3.5 of plan 2026.07.19-DUAL-PROVIDER on gpt-5.6-terra/medium.

First read AGENTS.md, CLAUDE.md, packages/task/commands/plan-exec.md, then
plans/2026.07.19-DUAL-PROVIDER/plan.md, handoff.md, phases/P3.md and every P3.5
Required Read strictly in its listed order. P3.4 is terminal at item commit 1d73963.

Preserve unrelated owner dirt. Execute only P3.5. Do not change P3.1 frozen contracts,
P4+, live Codex user-global state, current root .agents/skills, FOREMAN or fleet.
Use temporary roots for all apply/repair tests. Build expected semantic sets independently
from canonical registry and contract; do not derive them from a provider renderer.
Run the full lifecycle: journal, validation, two commits, status board and handoff.
```

**Done:** P3.4 at `1d73963` added P1-resolved provider distribution preflight, provider-qualified
vendor ownership, fail-closed external Codex marketplace handling, read-only provider doctor,
and an explicit native Codex installer. Legacy Claude remains the missing-provider default.

**Remaining:** P3.5, then independent P3 audit G03 before P4.1.

**Sources of truth:** `phases/P3.md` P3.4–P3.5 · frozen
`root/contracts/provider-skill-publication-contract.md` · `packages/skiller/lib/skiller/publication.py`
· P3.4 item commit `1d73963`.

**Open risks:** Existing plan-lint has 2 documented P3 DoR false-positive warnings; P3.4 adds
no errors. Native user-global Codex install was not run: only the explicit fake-runner path was
tested, by item scope. `maind health --cwd` is healthy; it accepts no positional path argument.

**Workarounds/Deferred/Open questions:**

- workarounds: none.
- deferred: exhaustive inventory/channel parity is P3.5.
- open_questions: —
