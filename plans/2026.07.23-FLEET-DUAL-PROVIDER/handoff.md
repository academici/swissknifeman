# HANDOFF — 2026-07-23 — after P1.1

**Next:** design-item: task:plan-design 2026.07.23-FLEET-DUAL-PROVIDER P1.1

| Parameter | Value |
|:--|:--|
| Model | gpt-5.6-sol |
| Thinking | xhigh — revise consumer rollout contract |
| Approval policy | never |
| Sandbox | danger-full-access |
| Cwd | /home/vostrikov/projects/packages/swissknifeman |
| Context | NEW SESSION — шаг-не-item |
| Суть | Redesign P1 pilot selection after the owner-directed skip; do not mutate any consumer. |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="xhigh"' -a never -s danger-full-access 'NEW SESSION: Run /task:plan-design 2026.07.23-FLEET-DUAL-PROVIDER P1.1. Start with pwd, git status --short, codex doctor --json, hook-command integrity, ./packages/maind/bin/maind health --cwd, and applicable plan lint. Read AGENTS.md, CLAUDE.md and the task-plan-design skill. Read findings/P1.1-pilot.md first. Owner decision D5 skipped sibintek-insiders because it is actively worked: do not mutate it, do not run P1.2, do not select another consumer or use --repair/--force without an approved plan redesign. Redesign the P1 pilot-selection and ordinary-consumer instruction-target contract.'
```

**Done:** P1.1 item finding `28236355` records the fail-closed provider-qualified instruction diagnosis. The owner skipped `sibintek-insiders`; no consumer bytes were written.

**Remaining:** Redesign P1.1 before another pilot is selected or any consumer mutation is attempted.

**Sources of truth:** `plan.md` · `phases/P1.md` · `findings/P1.1-pilot.md` · `journal.jsonl` · `packages/harness/lib/harness/instructions.py`.

**Open risks:** Root `CLAUDE.md`/`AGENTS.md` are unmanaged consumer targets and package-scope instruction targets are absent on the Laravel pilot. This is a contract/scope decision, not authority to repair or overwrite.

**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: all consumer writes, `--repair`, `--force`, P1.2, and another pilot.
- open_questions: which eligible replacement can receive the required instruction projection, and whether ordinary consumers should receive package-scope projections.
