# Журнал исполнения — `plans/<PLAN-ID>/journal.jsonl`

<!-- Справочник, НЕ файл для копирования как есть: journal.jsonl — append-only NDJSON
     (root/contracts/plan-journal-schema.md, P1.1 sealed v1), пишется хелпером
     lib/task/journal.py из close-протокола команд /task:plan-*, руками правится
     ТОЛЬКО при бэкфилле/бутстрапе (D22) или backstop-записи упавшего прогона. Ниже —
     канонический способ дописать запись + минимальная схема для ручного бэкфилла. -->

## Канонический способ (close-протокол команд, автоматически)

```bash
PYTHONPATH=packages/task/lib python3 -m task.journal append \
  --plan-dir plans/<PLAN-ID> --plan <PLAN-ID> --item <Pn.m> \
  --command plan-exec --actor sonnet/medium --result in-progress
# … исполнение …
PYTHONPATH=packages/task/lib python3 -m task.journal append \
  --plan-dir plans/<PLAN-ID> --plan <PLAN-ID> --item <Pn.m> \
  --command plan-exec --actor sonnet/medium --result closed-green \
  --note "1 строка сути закрытия"
```

Флаги `--session-id/--run-id/--attempt/--friction/--cost-usd/--num-turns/--duration-ms`
— опциональны, дефолты см. `lib/task/journal.py`. `--result`/`--command`/`--friction` —
закрытые enum (§2.1/§2.2 контракта); битая запись CLI отклоняет ДО записи (schema-валидация).

## Схема одной записи (§2 контракта, для ручного бэкфилла/backstop)

Одна строка = один JSON-объект (`ensure_ascii=False`, ключи любым порядком — парсер
NDJSON не требует сортировки, но `lib/task/journal.py` пишет `sort_keys=True`):

```json
{"ts":"2026-07-18T18:40:00Z","plan_id":"<PLAN-ID>","item_id":"<Pn.m>","command":"plan-run","session_id":null,"run_id":null,"attempt":1,"actor":"opus/high","friction":[],"result":"in-progress","cost_usd":null,"num_turns":null,"duration_ms":null,"note":null}
```

Обязательные поля: `ts, plan_id, item_id, command, session_id, run_id, attempt, actor,
friction, result, cost_usd, num_turns, duration_ms, note` — все 14, неизвестное значение
= `null` (не пропуск поля). Полные enum'ы `command`/`friction`/`result` и durable-граница
cost/turns/duration — `root/contracts/plan-journal-schema.md` §2–§2.2.

**Правило append-only.** Существующие строки НИКОГДА не переписываются/не удаляются
(контракт §1) — ошибочная запись компенсируется НОВОЙ строкой с
`friction:["deviation"]` + поясняющим `note`, не правкой задним числом.

**Ручной бэкфилл (D22).** Датовый план от cutoff-даты (`plan_lint.py:JOURNAL_CANON_DATE`)
без валидного `journal.jsonl` — ERROR. Бэкфилл закрытых до канона item'ов — РЕАЛЬНЫЕ
записи (actor/result/note по факту Update Log плана), не заглушка на пустом файле.
