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

## `analyst doctor`

```
analyst doctor
```

Диагностика окружения (python / core / maind).
