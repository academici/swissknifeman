# Идея: исполнитель в песочнице не может закончить пункт с генерируемыми файлами; brief требует reads, удалённые самим пунктом

Статус: идея. Источник: PLAN3 vaulter P5.12 (sonnet/high), 2026-10-18.

## Что произошло
- P5.12 (новый пакет vue-collaboration): код и 66 тестов готовы, но `api:check` (stale `schema.d.ts`) и `package-lock.json`
  требуют `npm run api:generate` / `npm install --package-lock-only` — в песочнице `node_modules` замаскированы, registry закрыт.
  Executor дважды получил красный V1, затем `blocked` (26 с), run `ITEM_BLOCKED`.
- `resume --retry P5.12` → `BRIEF_REFUSED READ_MISSING`: пункт перенёс/удалил файлы, указанные в его `reads`.
- Закрыл наблюдатель вручную: хост-команды, `settle`, `planner reopen` + временное восстановление reads + `start/finish/commit`.

## Предложения
1. Явный тип шага «host-step» в пункте/плане: команды вне песочницы (generate, lockfile) выполняет кондуктор по allowlist
   до checks; результат попадает в коммит пункта.
2. `READ_MISSING` в brief при `resume/retry` и `settle`: считать reads, удалённые изменением самого пункта (в diff), допустимыми.
3. `settle` должен закрывать и пункт в плане (finish + commit по `--path`), а не только журнал run.
4. Write-set пункта «новый пакет» включает `tests/zones.json`, `tests/suites.json`, `tests/baseline/**`, `scripts/t` — иначе
   `OUTSIDE_SCOPE` и ручной `--path`.
