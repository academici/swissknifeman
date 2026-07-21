# HANDOFF — 2026-07-21 — after P4

**Next:** design-phase: task:plan-design 2026.07.19-DUAL-PROVIDER P4

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | skills.repository · command.filesystem-read/write · command.git-read |
| Context | cold-start — plan-step |
| Суть | Reopen P4 only for the Codex runtime-projection consumer contradiction; P5 remains untouched. |

```text
$ task:plan-design 2026.07.19-DUAL-PROVIDER P4

РЕЖИМ: реопен по §3 (4 шага), НЕ детализация
ВХОД: plans/2026.07.19-DUAL-PROVIDER/phases/P4.md → блок `## Audit P4 — 2026-07-21`; прочитать ПЕРВЫМ
СКОУП: 1) починить owning Codex runtime projection без изменения Claude canonical bytes 2) добавить узкий consumer regression на отсутствие imperative Claude selector/slash output в Codex runtime 3) регенерировать только task Codex artifacts/locks и повторить непосредственный parity consumer
НЕ ТРОГАТЬ: frozen D84 contract, Claude golden/canonical commands, statuses/16 fields/journal topology, root adapters, P5+, FOREMAN, fleet, live/user config и unrelated owner files
```

**Done:** independent Audit P4 attempt 1 recorded literal RED on `b921487`; exact-set,
routing diagnostics, Claude goldens, protected diff and the recorded terminal close gate were
reconciled without rerunning package-wide validation.

**Remaining:** one bounded owning-seam P4 reopen/remediation for the generated Codex runtime
consumer plus focused regression and direct parity rerun. P5+ remains unopened and untouched.

**Sources of truth:** `phases/P4.md` → `## Audit P4 — 2026-07-21`;
`packages/task/lib/task/command_render.py:428`/`:435`;
`packages/task/adapters/codex/skills/task-plan-audit/{SKILL,command}.md`; frozen D84 contract.

**Open risks:** current Codex task cache can present a native `$ task:…` wrapper and then
instruct the session to obey Claude model pins and slash invocations from its runtime body.

**Workarounds/Deferred/Open questions:**

- workarounds: none accepted; do not use the broken Codex projection as G04 evidence.
- deferred: P5 and later phases remain outside this execution.
- open_questions: none; remediation scope is bounded by the audit finding.
