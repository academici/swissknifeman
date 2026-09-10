# CLI и команды

CLI — `analyst <command> [args]` (тонкий bash-лаунчер → `python3 -m analyst`). Также доступно как
плагин Claude Code (`/analyst:*`) и через корневой роутер `swissknifeman analyst …`. Все команды —
детерминированные, on-demand, без демона; сообщения на русском.

## `analyst digest`

```
analyst digest [--cwd | --session UUID] [--project ID] [--dry-run] [--json]
```

Детерминированно извлекает кандидат-уроки из свежего `run-report` прогона по высокоточным сигналам
(**resolved-failure** «команда падала и затем прошла»; явные **dev-loop workarounds**) →
`.claude/analyst/lessons/ephemeral/` (LOCAL). `--dry-run`/`--json` — предпросмотр без записи.

## `analyst scan` (P2)

```
analyst scan [--min-projects N] [--namespace NS] [--threshold T] [--no-prune] [--dry-run] [--json]
```

Cross-project агрегатор: обходит реестр `config.json:projects[]`, читает per-project уроки,
greedy-Jaccard-кластеризует и детектит паттерны, повторяющиеся в **≥N проектах** (по умолчанию 3),
→ draft-предложения в `~/.swissknifeman/analyst/suggestions/` + индекс `index/by_pattern/`.
**Namespace-изолированно**. Реконсиляция: осиротевшие артефакты снимаются **строго в scope прогона**
(`--no-prune` выключает, `--dry-run` показывает). Подробнее — [Жизненный цикл](./lifecycle).

## `analyst workflow-scan`

```
analyst workflow-scan [--project ID] --output DIR|FILE.json --now ISO [--json]
```

Read-only инвентаризация workflow-скриптов только из явных `local_path`/`vault_path` plan-root
enabled-проектов. Команда хеширует байты до разбора, сохраняет aliases зеркал, считает Rule of
Three по разным планам и сопоставляет статические признаки с четырьмя Task templates. JavaScript
не выполняется, абсолютные пути, prompts и тела скриптов в отчёт не попадают. Результат
`workflow-fleet-report/v1` может предложить лишь доказанное уточнение существующего слота;
пятая template-family и смена матрицы стадий остаются `report-only`.

## `analyst suggest` (P4)

```
analyst suggest <pattern_id> | --all [--bucket B] [--min-weight N] [--dry-run] [--json] [--force]
```

Cross-project паттерн (`index/by_pattern/`) → **ЧЕРНОВИК** скилла `SKILL.ru.md` + `draft.meta.json`
в `~/.swissknifeman/analyst/drafts/<pattern_id>/`. **НЕ** пишет в `skills/`, **НЕ** генерит EN-канон,
**НЕ** регистрирует — промоут в бакет делает человек. Ре-suggest защищён от ручных правок
(`--force` перезаписывает); осиротевшие черновики — предупреждение, не удаление. Подробно —
[suggest →](./suggest).

## `analyst review`

```
analyst review [--state ephemeral|candidate|curated|deprecated] [--project ID]
```

Показать уроки по состояниям + structured diff против активных (Jaccard) + mem0-рекомендация
(`ADD`/`UPDATE`/`NOOP`/`CONFLICT`). Read-only.

## `analyst recompute` (P3)

```
analyst recompute [--now ISO] [--dry-run]
```

Детерминированный пересчёт confidence из append-only `events.ndjson` (Beta-среднее × volume × decay)
→ числовая state-machine (авто `ephemeral→candidate`; `curated` — только человек; просадка →
soft-deprecate). Восстановим из логов при фиксированном `--now`. Демона нет.

## `analyst promote` / `deprecate`

```
analyst promote <id> [--to candidate|curated] [--supersedes ID] [--force] [--yes]
analyst deprecate <id>
```

Продвинуть урок по конвейеру `ephemeral→candidate→curated`. **Переход в `curated` требует согласия
человека** (`confirm` на tty либо `--yes`) и всплывает в память [mAInd](/maind/guide/memory).
Противоречие с активным уроком → **flag-and-ask** (авто-резолв запрещён: реши `--supersedes` или
`--force`). `deprecate` — soft-демоут (не удаляется, доступен для аудита).

## `analyst status`

```
analyst status [--json]
```

Read-only сводка стора уроков: счётчики по состояниям, `curated-ready` (числа для curated есть —
нужен человек), `promote_failed` (память была недоступна — досыл `promote --retry-failed`), число
событий, даты последнего `digest`/`recompute`. Ничего не меняет.

## `analyst compact`

```
analyst compact [--before ISO] [--dry-run] [--json]
```

Свести старые события `events.ndjson` (старше `--before`, или ВСЕ) в один snapshot-event на урок.
Суммы (S/N/tests) и возраст последнего события сохраняются, поэтому [`recompute`](#analyst-recompute-p3)
до и после даёт **ту же** confidence. `--dry-run` — показать, ничего не писать. Провенанс операции —
в `audit.ndjson`.

## `analyst sessions`

```
analyst sessions [--project P] [--weeks N] [--json]
```

Недельные ISO-медианы `first_turn_overhead`/`fresh-per-turn` из ЖИВЫХ jsonl-транскриптов сессий
(`~/.claude/projects/<encoded-cwd>/*.jsonl`, отдельный источник от `usage-trend.ndjson` —
тот питает `analyst token-report`); `--project P` резолвит `local_path` по id из реестра узла,
без флага — текущий каталог. Warn в stderr при росте медианы недели >20% к предыдущей (календарно
смежной) неделе — сигнал context-economy-рецидива (постоянная альтернатива разовому замеру
`skiller budget --first-turn` / `maind doctor --context`).

## `analyst doctor`

```
analyst doctor
```

Диагностика окружения (python / core / maind).
