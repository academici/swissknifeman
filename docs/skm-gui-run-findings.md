# Прогон плана SKM-GUI (PLAN5) дирижёром: наблюдения и правки

Рабочий журнал оркестратора (Sonnet 5.5). Запись делается сразу, как проблема найдена. Запись на проблему: симптом,
причина, что сделано (коммит), что стоит обсудить. Мелкое чиним сразу, крупное выносим владельцу. Порядок — хронологический.
Заметки плана с теми же номерами лежат в журнале плана (`ORCH-PROBLEM-N`).

Настройки прогона зафиксированы решением D16 плана: исполнитель claude-code/sonnet/medium, групповая review одна на фазу
(`codex/gpt-6.1-sol/high`), batch B1 на фазу, общий executor-сеанс (`session.executor: shared`).

## P3 (запуск, 2026-10-16)

| # | Симптом | Причина | Правка | К обсуждению |
| --- | --- | --- | --- | --- |
| 1 | `WORK_SOURCE_FAILED … BRIDGE_PARTNER_UNAVAILABLE` на claim | `orch conduct run` через `.swissknifeman/launcher.py` не находит партнёров моста planner-orch: `PLANNER_ROOT`, `SKM_ORCH_ROOT`, `AICORE_ROOT` не заданы, `planner` нет на PATH (ADR 0058 запрещает искать соседнюю папку) | обход: экспорт трёх корней на `packages/` проекта перед запуском; кода не правил | **крупное.** Launcher/umbrella должен сам отдавать корни партнёров хаба в окружение `orch conduct`, либо `doctor` обязан проверять их. Сейчас каждый запуск требует ручного экспорта |
| 2 | `CLAIM_BLOCKED READ_MISSING` на P3.3 | claim батча проверяет существование всех `required` чтений всех пунктов сразу, а P3.3 читает файлы, которые создаёт P3.2 (`config-view` examples, generated `config-view.ts`) | в плане P3.3 оба чтения переведены в `required: false` с пометкой «создаётся P3.2» (коммит плана) | **крупное.** `plan-design`/`design-done` должен предупреждать о required path, который создаёт более ранний пункт батча; либо claim проверяет чтения в момент старта пункта |
| 3 | `CLAIM_BLOCKED ITEM_OWNED` на следующем `run` | после остановки claim P3.1/P3.2 остались `in_progress` (по `conductor.md` в batch остановка пункты не возвращает); я запустил новый `run` вместо `resume` | `orch conduct release` для обоих пунктов, плановые файлы закоммичены | моя ошибка процедуры, не дефект. Открыт вопрос: должен ли `CLAIM_BLOCKED` до начала любой работы возвращать пункты сам |
| 4 | исполнитель `ITEM_BLOCKED` за 18 с: `bwrap: setting up uid map: Permission denied`, работы нет | роль `executor` запускается под `ro-run.py` (Landlock), а поверх добавляется песочница Claude (bwrap), когда она доступна. Landlock запрещает `mount` и запись `/proc/<pid>/uid_map`, поэтому bwrap внутри него не стартует. Обе защиты стали активны вместе после включения AppArmor-профиля bwrap. Воспроизведено вне conductor | коммит `fix(orch): песочница провайдера заменяет Landlock-охрану…`: `strip_guard` в `roles.py`, исправленный расчёт `isolation` в `cli.py`, тесты `SandboxTests` | **крупное.** Выбрать одну модель изоляции исполнителя. Открыто: `scope.extra_paths`/`--allow-path` и каталог транскриптов shared-сессии не попадают в `sandbox`-блок Claude, потому что `extra_write_dirs` работал только с `ro-run`. Проверить до первого пункта с `extra_paths` |
| 5 | `ROLE_LINGERED` и `attempt 1 failed at the provider (unknown: the role returned no final text)` у P3.2 | процесс провайдера жил 30 с после полного ответа, финального текста нет; сработал штатный повтор | не правлено, наблюдаю | смотреть, повторяется ли; если да — причина в формате ответа роли, а не в плане |
| 6 | во время работы исполнителя в `git status` появляются нетрекаемые `.bash_profile`, `.bashrc`, `.claude/commands`, `.claude/hooks` и др. | песочница Claude (bwrap) на время запуска создаёт в рабочей папке пустые заглушки запрещённых путей; после завершения команды они исчезают (проверено: уже отсутствуют) | не правлено | не мешает: conductor коммитит по write set. Если заглушка попадёт в коммит пункта — добавить в игнор/фильтр снимка дерева |
| 7 | follow-up групповой review: `ROUTE_UNDERSHOOT — the executor effort medium is below high required` за 1 с | `followup_input` (`review_plan.py`) жёстко задаёт `route.minimum.effort = high`, а решение D16 требует исполнителя sonnet/medium и в follow-up | обход: input пересобран через `orch input adhoc --effort medium --provenance review_followup` (тот же goal и scope). **исправлено:** `followup_input` берёт эффорт маршрута исполнителя прогона (`high`, если его нет), тест `test_the_followup_asks_no_more_effort…` | закрыто |
| 8 | follow-up `blocked`: vitest (7 файлов) и eslint не стартуют у исполнителя, `EACCES` на `node_modules/**/*.min.js` | в личных настройках владельца `.claude/settings.local.json:80` стоит `Read(**/*.min.js)` в deny; песочница Claude переносит правило в запрет чтения для Bash-процессов | правки follow-up приняты вручную: `npm run check` (eslint, tsc, vitest 60/60) и affected-тесты прогнаны мной вне песочницы, красный eslint (`set-state-in-effect` в `PreviewDialog.tsx`) исправлен, добавлен регрессионный тест, закоммичено | **обсудить.** Пока правило стоит, исполнитель не может проверять frontend: проверки пунктов проходят только через conductor вне песочницы. Варианты: убрать правило владельцем, либо `sandbox.filesystem.allowRead` в блоке conductor |
| 9 | после `blocked` follow-up правки остались в дереве, а `.swissknifeman/orch-artifacts/` (по `conductor.md` committed) — нетрекаемой папкой | `--commit` коммитит только при принятом результате; blocked с готовыми правками оставляет их владельцу | артефакты закоммичены вместе с принятой работой | норма процедуры; но `blocked` по причине окружения (п. 8) выглядит как провал работы — различать в отчёте |

## Review фазы P3

Групповая review (codex/gpt-6.1-sol/high, 157 с): 0 Blocker, 3 Major, 4 Minor. Major — в follow-up, Minor — заметки плана
(`P3.3`). Находки: откат чтения-после-записи затирает параллельного писателя (`aicore config/model.py`), устаревший preview
остаётся применимым при изменении черновика (`PreviewDialog.tsx`), локальное состояние `ScalarListField` переживает discard.

## Прогон дальше

Записи следующих пунктов и фаз добавляются ниже по мере выполнения.
