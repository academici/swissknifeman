# HANDOFF — 2026-08-12 — after P1.1

**Next:** run-items: task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.2-P1.3

| Параметр | Значение |
|:--|:--|
| Batch | B-P1-CUTOVER |
| Model class | implementation |
| Effort | high |
| Capabilities | filesystem, git, skiller registry, maind projects |
| Context | continue-root |
| Суть | Мигрировать active Layout v1 fleet, доказать zero-live-v1 и удалить legacy execution path. |
| Команда | `task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.2-P1.3` |

Provider-neutral launch-block:

```text
$ task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.2-P1.3
```

Native Codex launch-block:

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.12-№1-TASK-RESILIENCE P1.2-P1.3'
```

**Done:**

- P1.1 inventory product commit: `6553d06d`.
- Registered fleet snapshot классифицирует direct executable candidates, archives, invalid и unreachable roots; некорректные registry rows и ACTIVE targets fail closed.
- Declared Validation, focused unreadable/clean-checkout regressions и full isolated review завершились GREEN.

**Remaining:**

- P1.2 мигрирует targets и пишет zero-live-v1 ledger.
- P1.3 удаляет Layout v1 execution schema/path только после zero-live proof.

**Sources of truth:**

- `phases/P1/P1.1.md` и `phases/P1/P1.1.state.md`.
- `artifacts/P1/active-layout-inventory-v1.json`.
- `findings/03-layout-v1-cutover-inventory.md`.
- `decisions/D7-retire-v1-after-active-migration.md`, `decisions/D13-public-validation-carrier-for-P1.1.md` и `decisions/D14-declare-P1.2-ledger-deliverable.md`.
- `journal.jsonl`.

**Open risks:**

- Inventory ещё фиксирует active v1, invalid и unreachable entries; P1.3 fail closed, пока P1.2 их не устранит.
- D14 сделала P1.2 ledger exact predecessor output; до его материализации P1.3 корректно остаётся `pending-producer`.

**Workarounds/Deferred/Open questions:**

- Workarounds: —
- Deferred: historical archive lint debt и post-P1 registered-project commits вне P1.1.
- Open questions: —
