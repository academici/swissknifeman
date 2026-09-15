# Доказательства диагностического отчёта

Основной результат: [resource-efficiency report](../../2026.09.15-corex-p3-local-resource-efficiency.md).
Это metadata-only field snapshot; не новый execution protocol и не product acceptance.

## Источник и границы

Thread `01a0a63e-5b7e-7af2-8348-ab127f7d7fef`; исходный machine-local путь,
число строк и SHA256 неизменяемого prefix записаны в `session-metrics.json.source`.
Prefix заканчивается **вторым `task_complete`, строка 2541, 19:42:40.647 UTC**.
Третий task/диагностика и последующее пополнение JSONL исключены. Полный rollout в этот
каталог не копируется. SHA считается по исходным байтам выбранных строк, включая newlines.

## Состав

| Носитель | Содержание / происхождение |
|:--|:--|
| `session-metrics.json` | Итоговые usage, границы двух turns, accounting windows, read-proof aggregates, folder distribution и 31 formal command envelope. |
| `provider-usage-points.json` | 334 `token_usage_record`: timestamp, identity и usage counters; dedup по `response_id`. |
| `compaction-metadata.json` | Пять `compacted` events и связанные provider usage по response ID; replacement count, без summary body. |
| `command-dispatches.json` | 411 statically recognized shell dispatches: command SHA/length/first program/families, без command body. Regex extraction — неполная нижняя наблюдаемая часть, не полный subprocess trace. |
| `tool-output-metadata.json` | 326 tool output envelopes: размер, truncation flag, найденные exit/original-token counters, без stdout body. |
| `patch-targets.json` | Decoded `tools.apply_patch` headers: timestamp и пути, без patch body. Это нижняя наблюдаемая часть edits, не все shell writes. |
| `plan-file-inventory.json` | Все 1 341 file paths и размеры selected CoreX plan, включая ignored cache, на момент исследования. Не content-read coverage. |
| `commit-distribution.json` | `git show --numstat bde6098`, финальные file sizes и product/test vs plan/evidence группировка. |
| `source-manifest.json` | 40 selected repository sources/evidence с byte size и SHA256; абсолютные пути для machine-local перепроверки. Не claim чтения каждого файла плана. |
| `native-command-results.json` | Пять diagnostic invocations: argv, cwd, timestamps, exit, stdout/stderr bytes. Acquisition выполнен один раз. |
| `native-diagnostic-summary.json` | Выбранные counters/coverage maind, analyst и Task. Raw maind/analyst stdout не копируется: содержит чужие legacy session findings/command strings. |
| `task-returns.stdout`, `task-history-p31.stdout`, `task-history-p32.stdout` | Bounded native Task diagnostic output. |
| `session-journal-metadata.json` | Только execution session journal timestamps, item/command/result/run/attempt identity. |
| `runtime-reproductions.json` | Четыре наблюдения native parser/byte-anchor: два schema FAIL, semicolon entry mismatch и unchanged missing-only anchor GREEN без реального product coverage. |
| `checksums.json` | SHA256 и размер файлов этого snapshot; создаётся после записи доказательств. |
| `validation.json` | Результат проверки metrics arithmetic, local provenance, reproduction observations, ссылок и metadata shapes. |

## Методика воспроизведения

1. Читать JSONL только до второго payload `type: task_complete`; проверить prefix SHA.
   Для `type: token_usage_record` взять `payload.response_id`, `payload.usage` и timestamp.
   Повторный response ID не суммировать. Reasoning — subset output, cached — subset input.
2. `fresh = input − cached`; `total = input + output`. Сумма 334 provider records включает
   пять compactions; без них cumulative `event_msg.token_count` совпадает с main-response sum.
   Compaction usage уже входит в общий итог, повторно не прибавляется.
3. `elapsed = last task_complete timestamp − first task_started timestamp`;
   `active = sum(task_complete.duration_ms)/1000`; `gap = second start − first complete`.
   Остаток timestamps vs duration_ms — −0,005 с. Не смешивать owner wait с CPU/model time.
4. Accounting windows — полуоткрытые интервалы timestamp provider usage; их сумма равна
   total usage. Это не доказанная причинная атрибуция внутреннего reasoning/latency.
5. Read totals — saved required-read progress records. Дедуп envelope по
   `(command, started_at, ended_at, log)`; wall sums не CPU time, параллельный span меньше суммы.
6. Inventory — размеры файлов, без копирования содержания. Manifest hashes позволяют
   сравнить source snapshot; изменение исходника после исследования требует нового snapshot,
   а не редактирования старой метрики для видимости GREEN.

Точные диагностические argv доступны в `native-command-results.json`. `maind analyze`
запускался с `--no-health`; `analyst token-report --sessions 20 --json` выдал legacy trend,
не текущий Codex thread. `analyst:deep` найден в command catalog, но agent workflow не запускался.

Parser reproductions: заполнить штатный decision template и вызвать `parse_decision`;
затем дать valid YAML с English headings. Для paths дать semicolon Files sentence в
`_declared_paths`, собрать два identical missing anchors и вызвать `verify_closure`.
Для reads передать ненумерованную semicolon строку в `split_entries` (ожидалось три paths).
Использовались temporary fixtures; CoreX product/plan не изменялись.

Никакие product tests, phase audit, fleet qualification, lesson ingestion или runtime changes
не выполнялись ради snapshot. Из этих данных не выводятся USD, доказанный waste percentage
или обещанное ускорение будущей реализации.
