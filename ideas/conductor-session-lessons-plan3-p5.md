# Идеи: уроки сессии оркестрации PLAN3 P5.4–P5.16 (vaulter), не вошедшие в другие файлы

Статус: идеи. Источник: 2026-10-17/18. Связано с: `conductor-ignores-plan-review-policy.md`, `review-rounds-by-batch-risk.md`,
`observer-run-end-notification-lost.md`, `executor-sandbox-blocks-generated-files.md`, `conductor-adopt-and-write-set-mismatch.md`.

## 1. Исполнитель и модель: одна ступень на run
- В run одна ступень `executor` (provider/model_class/effort). Карта плана «P5.9 и P5.11–P5.15 sonnet, P5.7 opus xhigh» не
  выразима внутри батча: B4 (P5.7–P5.9) весь прошёл на opus/xhigh. Нужно: `route` по пунктам из плана (минимум) + выбор
  дешёвого допустимого исполнителя; либо options `stages_by_item`.
- Нужен `--dry-run`, который печатает по каждому пункту: исполнитель/effort, ревью (кто, сколько кругов), оценку времени.

## 2. Follow-up правки по групповому ревью
- `run --input followup.json --commit`: (а) `ROUTE_UNDERSHOOT` — минимум route в followup xhigh, а options по умолчанию
  high → падение за 1 с; options должны наследовать минимум; (б) `COMMIT_REFUSED` при каждом запуске (`git add .swissknifeman`);
  (в) ручная правка goal требует пересчёта digest (`canonical_digest`), `--dry-run` не валидирует.
  Нужны команды `orch conduct followup {show,add,seal} RUN` и флаг `review.verify_fixes` — повторная проверка правок
  ревьюером тем же вызовом (в PLAN3 она нашла 5 недоисправленных находок из 10 и 2 новых Major — без неё это ушло бы дальше).
- Исполнитель правок получает 7+ находок в одном goal; полезно правило: каждый пункт goal → тест, падающий без правки.

## 3. Песочница, silent denial, checks
- `RESULT_SILENT_DENIAL` (Write×5, Bash) у opus/xhigh на follow-up: правки применены не полностью → checks red V2,V6,V10 →
  лишний круг. Вероятная причина: scope.include ручного followup без `tests/baseline`, `tests/suites.json`, inventory.
  Нужно: scope followup = scope пункта ∪ пути из находок ∪ ledger-пути пакета (по `zones.json`/target-map).
- Исполнитель не может запускать node-тесты пакета (modules masked, registry 403): P5.16 `blocked`, `resume --retry` повторяет
  `executor.2` и пропускает `checks.1` («closed earlier»), т. е. не перепроверяет после правки на хосте. Нужно:
  `resume --retry ITEM --recheck` (перезапуск checks без executor) и host-step по allowlist.
- `STAGE_SLOW` на 45 мин тревожит, хотя исполнитель активен: добавить в бикон прогресс (число изменённых файлов, последняя
  правка, дельта от прошлого бикона) и различать «идёт/стоит» автоматически.

## 4. Качество тестов исполнителей: нестабильные тесты
- Два теста, написанных исполнителями (P5.7–P5.9), нестабильны: `limits.test.js` зависит от случайного `clientID` Yjs
  (размер delete set ±1000 байт), `compact-cli` — от времени (`--deadline=1` на загруженной машине). Нашлись только на
  P5.16 (красный V11, 1 из 306). Нужен flake-check в checks нового/изменённого теста: N=5 прогонов с параллельной нагрузкой и
  правило в `roles/executor.md`: детерминируй случайность (seed/clientID), не завязывай тест на секунды.
- Побочный продуктовый баг, пойманный этим тестом: попытка, отсечённая дедлайном, затирала реальную ошибку backend
  (`worker.js`, исправлено вручную).

## 5. Закрытие пункта вручную (settle)
- Последовательность `settle` → `planner reopen` → временно вернуть удалённые `reads` → `start` → `finish` → `commit --path…`
  хрупка (7 шагов). Нужна одна команда `orch conduct finish-by-hand RUN ITEM --status … --check Vn=0 …`, которая делает
  finish+commit по фактическим изменённым путям и учитывает удалённые reads.
- `planner commit` даёт `OUTSIDE_SCOPE` на побочные пути (zones/suites/baseline/scripts/t): для пунктов «новый пакет» нужен
  preset write-set, иначе каждый раз 10+ `--path`.
- Нет автокоммита для новых `tests/baseline/original/*` (untracked) → `WORKTREE_DIRTY` следующего run.

## 6. Среда и инструменты наблюдателя
- Хук `deny_hard` блокирует команды со словом `rm` даже внутри текста heredoc (заметка в файл с `rm -rf` в тексте не прошла) и
  `rm` во временных каталогах сессии: нужны точечные правила (только реальный вызов rm) и scratchpad в `safe-dirs.json`.
- `pkill -f <имя скрипта>` убивает собственную оболочку (имя в командной строке): в протоколе `orch-debug` использовать pid-файлы.
- `Monitor` истекает за 30 мин; решение — `orch watch` и `--chain` (см. `observer-run-end-notification-lost.md`);
  рабочий обход: скрипты chain*.sh + `ScheduleWakeup` ≤25 мин.
- `conduct runs` показывает ITEM_BLOCKED у вручную закрытого run — нужен статус `settled`.
- Устаревшие записи фоновых агентов прошлых сессий (P4.11, P5.2) остаются в списке запущенных: чистить при старте сессии.

## 7. Метрики для планирования (PLAN3 P5)
- opus/xhigh: P5.5 76 мин, P5.7 74 мин; P5.6 39 мин, P5.9 37 мин; sonnet/high: P5.13/P5.14/P5.15 10/9/28 мин.
- Групповое ревью codex gpt-6.1-sol: 125–308 с на группу; один вызов заменяет ~32 мин трёхкругового ревью grok.
- Квотные паузы провайдера за день ≈ 3,1 ч (`PROVIDER_QUOTA`): нужен авто-резюм и планирование тяжёлых батчей с учётом
  известного времени сброса.
