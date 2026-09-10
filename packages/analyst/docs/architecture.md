# Архитектура пакета

analyst — детерминированный (stdlib-only, on-demand) слой данных/пайплайна. Ниже — модули,
инварианты и раскладка данных.

## Модули (`lib/analyst/`)

| Модуль | Ответственность |
|:--|:--|
| `cli.py` | диспетчер команд (`COMMANDS` → `cmd_*(env, argv)`) |
| `common.py` | `Env(BaseEnv)` (path-property: `state_dir` = `~/.swissknifeman/analyst`, `monorepo_root`) + реэкспорт `core` |
| `lessons.py` | файловый стор: схема урока, state-каталоги, atomic write, append-only `audit`/`events`, Jaccard/similar, mem0-таксономия |
| `digest.py` | run-report → кандидаты по высокоточным сигналам; **чистые извлекатели** + IO в `cmd_` |
| `scan.py` | cross-project агрегатор (P2): кластеры → паттерны в ≥N проектах (namespace-изолированно) + reconcile |
| `workflow_scan.py` | bounded read-only inventory plan workflow files: digest mirrors, static signatures and Rule-of-Three template coverage |
| `suggest.py` | паттерн → **черновик** `SKILL.ru.md` (P4): чистые генераторы + edit-safe writer |
| `confidence.py` | **чистая** арифметика (Beta × volume × decay) + тиры |
| `recompute.py` | пересчёт confidence из `events.ndjson` → числовая state-machine (P3) |
| `review.py` | уроки по state + structured diff (read-only) |
| `promote.py` | конвейер + **человеко-гейт** curated + surfacing в память mAInd (subprocess, graceful) |
| `trace.py` | **Unified Agent Trace v1** — единственный владелец схемы `TraceRecord`: сборка/валидация записи (провенанс + sha256), fail-closed на любом сыром ключе, потенциально несущем chain-of-thought/tool-payload/секрет, `quality.completeness` по шести группам полей с причиной на каждую недостающую, дедуп resume/fork по натуральному ключу |
| `metrics.py` | парные метрики надёжности поверх закоммиченных `TraceRecord` и замороженного банка: `numerator/denominator/exclusions/completeness/source-trace-IDs/baseline-proof-class` в каждой записи; отсутствующий кандидат — `deferred`, а не тихий ноль; baseline класса `pinned-not-recomputable`/`unknown` не может обосновывать сравнение (fail closed) |
| `doctor.py` | диагностика окружения |

Таблица называет несущие модули; полная карта пакета (включая `capture`/`events`/`readers`/
`runs`/`ingest`/`proposals`/`sessions`/`status`/`token_report`) — в `packages/analyst/CLAUDE.md`.
Публичный package-API пакета — `0.2.0`: минорный бамп оплачен по Contribution gate контракта
Unified Agent Trace v1 ровно за два новых публичных модуля выше (`trace`, `metrics`).
Версия `.claude-plugin/plugin.json` из `package.json` **не** выводится — это отдельная
поверхность публикации.

## Инварианты (за них не выходим)

- **Авто-запись в скиллы запрещена** — analyst предлагает, промоутит человек.
- **Приватность:** raw — LOCAL-only; наружу — только абстрагированный `trigger→action`; секреты по ссылке.
- **stdlib-only** — никаких pip-зависимостей в рантайме (без демона/сети).
- **`Env` передаётся явно** (frozen dataclass), без модульных глобалей — тестируемо в tmpdir.
- **Atomic JSON** (`core.atomic_write_json`); `audit`/`events` — только дозапись, никогда не перезапись.
- **Извлекатели/генераторы — чистые функции** (вход → выход, без I/O/часов); IO — только в `cmd_*`/writers.
- **Детерминизм + namespace-изоляция** наследуются во всём cross-project слое.

## Раскладка данных

```
<project>/.claude/analyst/                 # per-project, LOCAL (raw остаётся здесь)
  lessons/{ephemeral,candidate,curated,deprecated}/<id>.json
  audit.ndjson · events.ndjson

~/.swissknifeman/analyst/                   # cross-project слой (state_dir; общий state зонтика)
  index/by_pattern/<id>.json               # scan: абстрагированные паттерны
  suggestions/<id>.md                      # scan: человекочитаемый draft-МД
  drafts/<pattern_id>/                      # suggest (P4): черновик скилла
    SKILL.ru.md · draft.meta.json
```

## Связи в экосистеме

- **[mAInd](/maind/)** — `curated`-уроки всплывают в общую память (`maind memory`, subprocess,
  graceful: демон лёг → урок на диске, повторим позже). Namespace-изоляция scan наследуется отсюда.
- **[skiller](/skiller/)** — конечная точка `suggest`: черновик → человек → зарегистрированный скилл.
- **[harness](/harness/)** — хук `run-report` захватывает прогон (вход для `digest`).
- **core** — общий stdlib-фундамент (`Env`/`io`/`text`/`term`), подключается через PYTHONPATH.

## Разработка

```bash
bash scripts/test.sh          # unittest (без сети/демонов)
bash scripts/validate.sh      # py_compile + bash -n + JSON + обязательные файлы + frontmatter + тесты
```

Коммиты — Conventional Commits, на русском. Перед PR: `scripts/validate.sh` зелёный.
