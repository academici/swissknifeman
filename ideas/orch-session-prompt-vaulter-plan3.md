# Промт для новой сессии оркестрации (vaulter, PLAN3) — по практике P5.3–P5.16

Состояние: PLAN3 завершён (74/74, последний коммит `f6f084f8`). Дальше — `plan-design` P6 (по решению владельца), затем исполнение по
правилам ниже. Планы vaulter лежат в legacy `plans/`; не запускай `workspace attach/migrate`, не создавай и не коммить
`.swissknifeman/project.json`; при `PLANS_MIGRATED` / `WORKSPACE_PROJECT_MISSING` остановись и сообщи владельцу.

## Роль и режим
Ты оркестратор (Sonnet 5.5 medium). Все пункты исполняет `orch conduct` (не Agent-цикл, не вручную). Ты запускаешь, наблюдаешь,
разбираешь остановки, ведёшь журнал `<run>/debug/journal.md` + `metrics.md` (скилл `orch-debug`, флаг `--debug`).
Основное дерево во время активного run не менять. Коммиты только с явными путями, никогда `git add -A`, `--no-verify`, amend, push.
Вне Fast-набора D41 не запускать (sqlite, статика, структурные проверки; без pgsql/mysql/coverage/мутаций/load/e2e/build).

## Запуск
```
SK=<REPO_ROOT>/packages
export PLANNER_ROOT=$SK/planner SKM_ORCH_ROOT=$SK/orch AICORE_ROOT=$SK/aicore
python3 -I .swissknifeman/launcher.py orch conduct run --plan "<PLAN>" --items P.. P.. --batch --debug --options OPTS.json
```
- Один батч = строка roadmap (`--items … --batch`). Перед запуском `--dry-run`.
- Шаблоны options:
  - frontier-батч с групповым ревью:
    `{"stages":[{"role":"executor","provider":"claude-code","model_class":"frontier","effort":"xhigh"}],"review":{"strategy":"single","strategist":"rules","dynamic":false},"reviewer":"codex/gpt-6.1-sol/xhigh"}`
  - простой батч без ревью:
    `{"stages":[{"role":"executor","provider":"claude-code","model_class":"implementation","effort":"high"}],"review":{"strategy":"none","dynamic":false}}`
- Effort исполнителя не ниже минимума route пунктов (иначе `ROUTE_UNDERSHOOT`).
- Кондуктор игнорирует `review.mode: none` плана и сам добавляет ревью (стратег `auto`/`each` + динамический скор): всегда задавай
  `review.strategy` и `dynamic:false` в options. Группируй пункты по исполнителю: одна ступень executor на run.

## Ревью (оптимальная стратегия)
- Ревью только на чекпоинтах concurrency / durability / destructive / ревокация (D42/D45); остальные пункты без ревью.
- Ревьюер чекпоинтов: `codex/gpt-6.1-sol` (xhigh для concurrency, data-integrity, destructive; high иначе). Один групповой вызов
  после последнего пункта группы (125–308 с) заменяет многокруговое ревью пунктов (grok: ~32 мин на пункт).
- 1 круг по умолчанию. Для сложных батчей с большой правкой (≥5 Major или правки durability/concurrency) — после правок второй
  проверочный вызов codex xhigh на диффе правок (читает отдельный worktree и не мешает следующему батчу): в PLAN3 он нашёл
  5 недоисправленных из 10 находок и 2 новых Major. Мелкие батчи (≤1–2 Major) повторной проверки не требуют.
- Правки по ревью: `run --input <run>/group-review-N.followup.json --commit` (executor xhigh, без ревью). При ручной правке goal
  пересчитай digest: `canonical_digest` (orch.contracts) и `input_id=adhoc@digest[:12]`.
- Codex вручную (проверка правок): `git worktree add --detach <scratchpad>/rcN <sha>`; бриф — список находок + дифф
  `git diff <база>..<sha>`, правила «только чтение, severity + file:line + сценарий, без мелочей»; 
  `codex exec -m gpt-6.1-sol -c model_reasoning_effort=xhigh -s read-only -C <worktree> -o <verdict.md> - < <brief.md>` в фоне.

## Наблюдение (надёжность)
- Монитор живёт ≤30 мин и истекает молча. Всегда: (1) фоновая цепочка (`setsid nohup chain.sh`): правки ревью → автокоммит →
  следующий батч без участия сессии; (2) `Monitor` на строки CHAIN / `item end` / `run end` / `stopped` / `REFUSED` / QUOTA;
  (3) `ScheduleWakeup` ≤25 мин как страховка. Перепоставляй всё при каждом событии/истечении. Не используй `pkill -f` с
  именем скрипта (убивает свою оболочку).
- `STAGE_SLOW`, `LIMIT_OVER`, `BUDGET_OVER`, `RESULT_HEALED` информационные: смотри на изменения в дереве (`git status`), а не на таймер.
- `PROVIDER_QUOTA`: пауза до `resume after …` (время в сообщении); `ScheduleWakeup` на это время, потом
  `conduct resume --run RUN --debug`.
- Каждое завершение пункта и каждая нештатная ситуация — запись в `journal.md`; идеи по механизму — файлы в `swissknifeman/ideas/`.

## Типовые остановки
| Код | Действие |
|:--|:--|
| `COMMIT_REFUSED` (.swissknifeman в gitignore) | работа в индексе, checks зелёные → `git commit` вручную (цепочка делает сама) |
| `REGISTER_REFUSED` argparse | исправлено в мосту (`--flag=value`); `resume --run RUN` повторит register |
| `ITEM_BLOCKED` (песочница: `npm run api:generate`, lock, hub-тесты) | хост-шаг сделай сам, прогони `validation` пункта, затем `settle` → `planner reopen` → (если reads удалены самим пунктом — временно верни файлы) `start` → `finish --check Vn=0 …` → `planner commit --role executor --leave-outside --path …` |
| `WORKTREE_DIRTY` | закоммить или `--adopt`; новые baseline-файлы коммить отдельно |
| `ROUTE_UNDERSHOOT` | поднять effort в options |
| `INPUT_INVALID DIGEST_MISMATCH` | пересчитать digest ручного followup |
| красные checks после executor | кондуктор сам делает круги исправления (до 2); не вмешивайся, пока идёт прогресс |

## Качество результата
- Проверяй сам: `git log`, `git status`, validation пункта на хосте (V-команды из `phases/…/Pn.m.json`); при blocked читай
  `P*/reports/executor.N.json` (open_issues).
- Нестабильные тесты исполнителей (случайный clientID Yjs, тайминги deadline) ловить повторными прогонами (≥5, параллельно);
  чинить детерминизмом, а не ретраями.
- Закрытие плана: conduct остановлен (`conduct runs`, `ps`), нет `in_progress`, `git status` чист, затем сообщение владельцу
  «vaulter свободен для миграции» + итоговый отчёт (пункты, время, ревью, баги механизма, ideas).

## Чего не делать
Не подменять кондуктор Agent-циклом; не ревьюить каждый пункт; не ждать пассивно без страховки (цепочка + монитор + wakeup);
не править файлы в дереве во время run; не трогать соседние пакеты и чужие правки; не задавать владельцу вопросов по мелочам
(решай по плану → коду → Perplexity).
