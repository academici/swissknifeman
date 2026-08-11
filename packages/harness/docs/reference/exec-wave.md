# Драйвер exec-волны

Команда `harness run <PLAN-ID> <Pn>` снимает ручной ритуал запуска item'ов
`plan-протокола`: читает очередь фазы, гоняет воркера **процессом** (не
`Agent`/`Task` tool — подавление AgentTool в подпроцессной сессии не
воспроизводится), выносит вердикт по каждому item'у и пишет журнал там, где
воркер физически не мог. Решений драйвер не принимает — он производит.

## Что делает

- **`plan_reader`** читает очередь исполнения ОДНОЙ фазы: item'ы в порядке
  `## Phase Status`, терминальные (`🟢`/`🟠`/`⛔`) исключены, по каждому
  оставшемуся — маршрут (`task.task_contract build`), значение `Exec`, право
  вождения. Право вождения даёт РОВНО дословное значение `Exec = plan-exec` в
  `## 3. Routing` — деривация из тира §9 никогда его не выдаёт (только
  отказывает на противоречии). Semantic `Next` для v1 и v2 берётся только из
  owner `handoff.md`; layout-v2 item-state содержит только result fields и не является
  fallback-источником orchestration.
- **`worker`** запускает ОДИН item процессом `claude -p "/task:plan-exec
  &lt;PLAN-ID&gt; &lt;Pn.m&gt;" --output-format json` под таймаутом (по умолчанию 1800s),
  строго один воркер за раз (последовательная волна — параллельный fan-out на
  общей кодовой базе не заводится). Селекторы модели/effort берутся из
  `packages/task/configs/command-routing.json`.
- **`gate`** выносит вердикт `GREEN`/`ATTENTION`/`RED` из четырёх источников:
  класс исхода прогона, `plan-lint --baseline --gate new`, git-топология
  закрытия (`<SHA до>..HEAD`), статус/поля item'а после прогона. Таблица
  «признак → вердикт» тотальна: любой RED побеждает, несматчившийся набор
  признаков сам по себе RED (fail-safe).
- **`journal`** дозаписывает строку в `journal.jsonl` РОВНО когда сессия
  воркера не дошла до close-протокола сама (timeout/transport/quota/error/
  routing-blocked/no-op) — успешное самозакрытие `/task:plan-exec` не
  дублируется (D32).

## Использование

```
harness run <PLAN-ID> <Pn> [--dry-run] [--limit N] [--timeout S]
                            [--plans-root PATH] [--json]
```

| Флаг | Смысл |
|:--|:--|
| `--dry-run` | только очередь/маршруты/точный `argv`/причины отказов — БЕЗ спавна воркера и БЕЗ единой записи (read-only) |
| `--limit N` | максимум item'ов волны (по умолчанию — вся очередь) |
| `--timeout S` | таймаут ОДНОГО прогона воркера, секунды |
| `--plans-root PATH` | каталог, где искать `<PLAN-ID>/plan.md` (по умолчанию `<монорепо>/plans`) |
| `--json` | та же сводка машинно (`ensure_ascii=False`) |

Волна **последовательная** и останавливается на **первом RED**; `ATTENTION` её
не останавливает, но выносится в сводку поимённо. Ретрая нет ни одного тира —
упавший item ждёт следующего ручного запуска.

## Что НЕ делает (закрытый список)

Машину решений `decide` · run-folder · retry-лестницу трёх тиров ·
интеграцию с мессенджерами и remote-approve · пакет `packages/artifex` ·
раскатку agent-pack'ом · второго водителя (`codex exec`) · unattended-профиль
(`--permission-mode` — политика прогона остаётся окружением владельца) ·
параллельный запуск воркеров.

## Приёмка

Живая приёмка принадлежит package tests и `bash packages/harness/scripts/validate.sh`:
v1/v2 plan-reader fixtures проверяют route/Next boundaries, CLI dry-run — read-only,
а wave tests — stop-on-RED/continue-on-ATTENTION. Исторические полевые прогоны остаются
provenance, но не заменяют current validators. Доля вмешательств с fixture-wave —
синтетическое число; боевая статистика по-прежнему накапливается durable журналом.
