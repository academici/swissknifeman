# P2 — формат transcript-директории workflow-прогона (эмпирика)

**Источник:** прямое чтение `~/.claude/projects/**` на этой машине 2026-07-10
(swissknifeman/loqum/azguard/edufy прогоны). Формат **внутренний, недокументированный**
для Claude Code — спека `roadmap/workflow-status-cli.md` прямо назначает источником истины
фикстуру реального прогона, а не доки. Вердикт: парсер строим на этой раскладке, защищённо
(unknown-поля игнорировать, при несовпадении — «формат не распознан», не трейсбек).

## Раскладка на диске

```
~/.claude/projects/<proj-slug>/<session-uuid>/
├── workflows/scripts/<name>-wf_<id>.js        ← СКРИПТ прогона (export const meta)
└── subagents/workflows/wf_<id>/               ← transcript-директория ПРОГОНА
    ├── journal.jsonl                          ← события агентов
    ├── agent-<hex>.jsonl        (0600)        ← транскрипт агента (большой)
    └── agent-<hex>.meta.json                  ← мета агента (минимальная)
```

- `<proj-slug>` — абсолютный путь проекта с заменой `/`→`-`, ведущий `-` сохранён
  (напр. `/home/vostrikov/projects/packages/loqum` → `-home-vostrikov-projects-packages-loqum`).
  RAG:✅ 2026-07-10 эмпирика (имена каталогов совпадают дословно).
- **Скрипт лежит НЕ в `wf_<id>/`, а в sibling `../../workflows/scripts/<name>-wf_<id>.js`**
  (D19). Спека подразумевала скрипт «в директории прогона» — расхождение.

## journal.jsonl

JSON-lines, **только два типа события**, БЕЗ timestamp/label/phase:

```json
{"type":"started","key":"v2:<sha256>","agentId":"<hex>"}
{"type":"result","key":"v2:<sha256>","agentId":"<hex>","result":<любой JSON>}
```

- `key` = `v2:<hash>` — кэш-ключ промпта+opts, НЕ человекочитаемый label.
- `result` — произвольный JSON (объект/строка/массив); у структурного агента типовые поля
  `findings`/`summary`/`title` — для 1-строчной выжимки брать по упорядоченному fallback.
- Прогресс: `started`−`result` = в полёте; `result` = завершено. **Timestamp'а в журнале нет** →
  время активности берём из mtime `journal.jsonl` (последняя запись) / mtime файлов агентов.
- Строки читать по одной; битую строку — `continue`, не падать.

## agent-<hex>.meta.json

```json
{"agentType":"workflow-subagent","spawnDepth":1}
```

Метки/фазы/модели **НЕТ**. `agent-<hex>.jsonl` (0600, транскрипт) в line-0 несёт `type:user`
с `message`+`promptId`+`timestamp` — там label/phase могли бы восстановиться, но это дорого,
хрупко (версия CC) и файл 0600. **Вывод (D18):** per-agent→phase attribution из журнала/меты
не выводится; отчёт показывает декларации фаз из `meta` скрипта + ОБЩИЙ прогресс агентов,
per-phase счётчики опущены осознанно.

## export const meta (в скрипте)

```js
export const meta = {
  name: 'p1-4-auth-security-review',
  description: '…',
  phases: [
    { title: 'Review', detail: '…' },
    { title: 'Verify', detail: '…' },
  ],
}
```

Это **JS-объект, не JSON** (ключи без кавычек, висячие запятые) → парсить регуляркой,
извлекая `phases[].title/detail`, **без eval/exec** JS. meta не распознан → `phases=[]` + флаг.

## Что надёжно / что нет

| Сигнал | Источник | Надёжность |
|:--|:--|:--|
| run id | имя каталога `wf_<id>` | надёжно |
| имя/описание/фазы (декларация) | `export const meta` скрипта | надёжно (регуляркой) |
| число агентов, завершённых, в полёте | `journal.jsonl` started/result | надёжно |
| грубый % | завершённые / стартовавшие | надёжно (грубо) |
| последние N результатов (1 строка) | `journal.jsonl` result | надёжно |
| время активности | mtime `journal.jsonl` | надёжно (для discovery/сортировки) |
| **какой агент в какой фазе** | — | **НЕ выводится** (D18) |
