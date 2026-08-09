# HANDOFF — 2026-08-09 — after P5.4

**Next:** /task:plan-design 2026.08.07-PLAN-ECONOMY P5.4

## Provider-neutral plan-protocol launch-block

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high |
| Capabilities | — |
| Context | NEW SESSION — шаг-не-item |
| Суть | Сверить схему реестра диспозиций P3.6 с обязательной Validation P5.4 и исправить ТЗ по D-записи |
| Команда | `task:plan-design 2026.08.07-PLAN-ECONOMY P5.4` |

```text
$ task:plan-design 2026.08.07-PLAN-ECONOMY P5.4
```

## Native Codex launch-block

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-design 2026.08.07-PLAN-ECONOMY P5.4'
```

**Done:** P5.4 прошёл routing и pre-mutation Task Contract (`allow`) в сессии
`gpt-5.6-terra/high`; в `journal.jsonl` дописаны start и escalation события, а state/status
проекции регенерированы. Реализация не начиналась.

**Remaining:** `task:plan-design` должен устранить конфликт схемы реестра диспозиций и
Validation P5.4; после этого повторить P5.4. Затем P5.5 — адаптер над пакетом P4 и
приёмка фазы.

**Sources of truth:** `phases/P5/P5.4.md` (особенно Validation) ·
`packages/task/configs/lint-check-dispositions.json` (P3.6 schema) ·
`findings/P5.4-lint-disposition-schema-conflict-2026-08-09.md`.

**Open risks:** P5.4's literal Validation expects `checks` to be a list of rows with
`id/default_enabled`, but the P3.6 registry is a keyed function map with `disposition` only.
Changing either side without a D-record risks breaking live lint consumers. Baseline plan-lint
still has 6 pre-existing WARN. The worktree carries unrelated `brief/index/roadmap` changes
that P5.4 did not overwrite.

**Workarounds/Deferred/Open questions:** workaround — none; deferred — P5.3's historical
test-bootstrap issue remains outside this item's scope; open question — whether P5.4 must use
the P3.6 mapping schema or P3.6 needs an explicitly migrated row schema.
