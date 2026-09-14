# Проверка артефактов аудита — 2026-09-14

## Выполненные содержательные проверки

1. `python3 tasks/2026.09.14-skills-and-task-audit/collect.py` — 232 canonical skills,
   49 buckets, 684 строки с нормативными signals, три project inventories; JSON читается.
   Рекомендации matrix созданы тем же сборщиком; количество/identity сверяются с corpus.
2. `packages/skiller/bin/skiller budget --check-core` — 431 / 750, 9/9, OK.
3. Из `packages/task`:

   ```bash
   PYTHONPATH=lib python3 -m unittest tests.test_plan_weight.TestRequiredReadsResolution.test_backticked_unicode_plan_identifier_is_a_declared_path tests.test_plan_bundle.PlanBundleTest.test_unicode_cross_plan_decision_path_builds_as_one_declared_input -v
   ```

   Результат: 2 tests, 0.006 s, OK. Это существующие regression tests; аудит их не менял.
4. `task_contract.compile_batch_routing()` на текущем `flexcrm/plans/FLEX-2` — PASS.
   Отдельно подстановка synthetic routing row `{_items: [P1.1], Batch: solo, Exec: plan-run}`
   в `executable_routing_table` через `unittest.mock.patch.object` воспроизводит:

   ```text
   TaskContractBuildError: routing: Routing: line 1: invalid Exec 'plan-run'
   ```

   Это доказательство enum defect на входе compiler, не end-to-end replay исторической сессии.
5. Байт-сравнение текущего source с cache `task/0.16.2` для `plan_weight.py`,
   `plan_bundle.py`, `commands/plan-run.md`, `commands/fix.md` — одинаковы.
   Отдельный loaded consumer session не аттестован.

## Квалификация артефактов

- Относительные Markdown file links внутри task artifacts проверены на существование.
- Matrix содержит ровно 232 identity, равные текущему canonical набору.
- JSON inventory структурно валиден; roadmap snapshot содержит все пять файлов за дату.
- `git diff --check` и whitespace check новых task artifacts выполнены.

Product code/config/skills не изменялись. Package/fleet тесты, docs site build,
новые model sessions и behavioural A/B не запускались; они не заявляются GREEN.
Source package qualification будет нужна реализации, а не публикации рекомендаций.

Некоторые ранние объединённые tool reads были усечены по output budget. Значимые места
перечитаны адресно; полные данные corpus сохранены в inventory, а semantic coverage
явно ограничен в README. Неизвестная native загрузка или токены не заменяются proxy числом.

Внешние product docs не менялись; добавлена одна provenance строка в docs/reference.md.
CHANGELOG не менялся этим аудитом: release-visible изменения ещё не реализованы.

Во время аудита внешняя работа дополнительно изменила `task_contract.py`, `plan_recovery.py`
и `test_task_contract.py`. Эти изменения сохранены; финальная адресная проверка подтвердила,
что Exec enum всё ещё исключает plan-run. Canonical skill bytes, пять roadmap carriers и
все candidate skill bytes с момента inventory не изменились. Финальные хеши ключевых
runtime sources сохранены в [source-hashes.json](source-hashes.json); номера строк не
используются вместо identity исходника.
