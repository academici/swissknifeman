# CLAUDE.md — analyst

Гид по кодовой базе для агентов. Это пакет **непрерывного обучения** экосистемы academici:
детерминированный (stdlib-only, **on-demand — без демона**) слой, который извлекает «выстраданные
уроки» из потоков задач Claude Code и — **с человеком в гейте** — продвигает их в переиспользуемое
знание (память mAInd → скиллы). CLI — `analyst`.

Реализованный контур: **P1 (MVP)** — `digest` + lessons-store + human `review`/`promote`;
**P2** — cross-project агрегатор `scan`; **P3** — confidence-арифметика (Beta/decay) + числовая
state-machine `recompute` + mem0-таксономия. Дальше по roadmap: `analyst suggest`→draft-скилл (P4),
`observe.sh` PostToolUse-поток (P5).

## Что это (два слоя, здесь — только слой-1)

- **Слой-1 (этот пакет):** данные/пайплайн. `digest` → lessons-store(state+провенанс) → `review`/`promote`.
- **Слой-2 (промпт-дисциплина):** скиллы (`field-feedback-loop` и др.) — вне этого пакета.

Авто-запись в скиллы **запрещена** (инвариант): analyst лишь предлагает, промоутит **человек**.

## Раскладка

- `bin/analyst` — тонкий bash-лаунчер → `python3 -m analyst <root> <cmd> [args]`.
- `lib/analyst/*.py` — вся логика, **stdlib-only** (реэкспорт общего `core` через `common.py`).
- `tests/` — `unittest`, изоляция в tmpdir; surfacing тестируется фейковым `MAIND_BIN` (без демона/сети).
- `.claude-plugin/` + `commands/analyst.md` — плагин Claude Code (slash `/analyst:*` → CLI). Только команды.
- `docs/` — VitePress: собирается **standalone** (своя `docs/.vitepress/`) и в зонтичном агрегате
  (`scripts/docs-sync.sh` копирует `packages/analyst/docs` → `docs/analyst/`, gitignored; линковка —
  в корневом `docs/.vitepress/config.mts` + `docs/routing.md`). Внутренние ссылки относительные.

### Ключевые модули

| Модуль | Ответственность |
|:--|:--|
| `cli.py` | диспетчер команд (`COMMANDS` → `cmd_*(env, argv)`) |
| `common.py` | `Env(BaseEnv)` (path-property: `state_dir`=`~/.swissknifeman/analyst`, `monorepo_root`) + реэкспорт `core` |
| `lessons.py` | файловый стор: схема урока (скаляры+провенанс), state-каталоги, atomic write, **append-only** `audit.ndjson` + `events.ndjson`, переходы (ре-райт+unlink — не двоится), Jaccard/similar, `classify_consolidation` (mem0-таксономия ADD/UPDATE/NOOP/CONFLICT) |
| `confidence.py` | **чистая** арифметика (stdlib, без I/O/часов): Beta-среднее × volume × time-decay + тиры 0.3/0.5/0.7/0.9. Константы — тюнинг-параметры модуля (P3) |
| `recompute.py` | `analyst recompute` (P3) — детерминированный пересчёт confidence из `events.ndjson` → числовая state-machine (авто `ephemeral→candidate`; `curated` — только человек; просадка → soft-deprecate). Восстановим из логов (при фикс. `--now`) |
| `digest.py` | `analyst digest` — run-report → КАНДИДАТЫ по высокоточным сигналам (resolved-failure, workaround); чистые извлекатели ради тестируемости; защитная деградация |
| `scan.py` | `analyst scan` (P2) — cross-project агрегатор: читает `config.json:projects[]`, per-project уроки → Jaccard-кластеры → паттерны в ≥N проектах (**namespace-изолированно**) → draft-предложения в `~/.swissknifeman/analyst/`; чистые core-функции + writers. **Reconcile**: после `write_artifacts` прун осиротевших index+suggestion СТРОГО в scope прогона (чистая `stale_pattern_ids` + `list_existing_patterns`/`prune_artifacts`; `--no-prune`/`--dry-run`; классификация ns — из ПОЛЯ индекса; чужой ns не рескан → не трогаем) |
| `review.py` | `analyst review` — уроки по state + structured diff против активных (read-only) |
| `promote.py` | `analyst promote`/`deprecate` — конвейер + **человеко-гейт** curated + surfacing в память mAInd (subprocess, graceful) |
| `doctor.py` | диагностика окружения (python/core/maind) |

## Раскладка данных (per-project, LOCAL)

```
<project>/.claude/analyst/
  lessons/{ephemeral,candidate,curated,deprecated}/<id>.json
  audit.ndjson        # append-only провенанс переходов
  events.ndjson       # append-only поток сигналов confidence (P3): скаляры наблюдений
```

Урок несёт **аддитивные** P3-поля-снапшот (пишет `recompute`, не ломая P1-схему):
`S_decayed`/`N_decayed`/`confidence`/`confidence_tier`/`recomputed_at`. Источник истины
пересчёта — `events.ndjson` (снапшот воспроизводим из лога при фиксированном `--now`).

Инвариант приватности: сырьё (raw-транскрипт) — LOCAL-only, наружу (в память на curated) идёт только
абстрагированный урок (trigger→action+evidence). Секреты — только по ссылке, не значением.

## Конвенции (соблюдай при правках)

- **stdlib-only** в `lib/analyst/`. Никаких pip-зависимостей в рантайме.
- **`Env` передаётся явно** (frozen dataclass), без модульных глобалей — тестируемо в tmpdir.
- **Atomic JSON** (`core.atomic_write_json`); `audit.ndjson` — только дозапись, никогда не перезапись.
- **Переход state** — через `lessons.move_lesson` (ре-райт+unlink), не двоить урок между каталогами.
- **Переход в curated — только человек** (`confirm`/`--yes`); авто-промоут запрещён.
- **Сообщения — на русском** (`die(...)`, `warn(...)`), как в maind/skiller.
- **Извлекатели digest — чистые функции** (run_report → [lesson]); IO — только в `cmd_*`.
- **После правок плагина/команд** — `skiller registry` (регенерит общий marketplace; analyst подхватывается как соседний пакет).

## Разработка

```bash
bash scripts/test.sh          # unittest (без сети/демонов)
bash scripts/validate.sh      # py_compile + bash -n + JSON + обязательные файлы + frontmatter + тесты
```

Коммиты — Conventional Commits, на русском. Перед PR: `scripts/validate.sh` зелёный.
