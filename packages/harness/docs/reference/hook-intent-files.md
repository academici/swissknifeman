# `*.env.ini` — хуковый интент, а не конфиг узла

`*.env.ini` — спроектированный носитель **интента хука per-project** (какой режим включён в
ЭТОМ дереве): не разрозненные локальные конфиги и не дубль конфига узла mAInd. Файл
`~/.swissknifeman/config.json` предположение аудита не подтвердило: там нет `config.json`
вовсе — есть `projects.json`/`topology.json`/`memory/` (реестр флота), а шаблон конфига узла
maind — корневой `config.example.json` (ключи `node`/`memory`/`graph`/`agents`/`namespaces`/
`projects`/`mcp`/`observability`) — другой предмет, сливать их значило бы сломать работающий
механизм ради устранения дублирования, которого нет (P5.3, `research/05-p5-hygiene-model.md`,
`findings/P5-hygiene-surfaces-2026-07-31.md` §4).

## Два класса файла — и правило трекинга по классу

| Класс | Путь | В git? | Почему |
|:--|:--|:--|:--|
| **Per-project intent** (машиноспецифичен) | `<project>/.claude/<hook>.env.ini`, `<project>/.codex/memory.env.ini` | **НЕТ** — `.gitignore` | Это выбор ЭТОГО дерева (bypass/strict/maind/off), не общая база; коммит унёс бы чужой выбор в чужой репозиторий |
| **Шаблон-дефолт хука** | `configs/claude-code/hooks/<hook>/env.ini`, `configs/claude-code/agent-packs/<pack>/hooks/review-gate.env.ini` | **ДА** | Это раздаваемый дефолт: `harness hooks`/agent-pack копируют его в проект как исходное значение лестницы |

Правило класса, а не список файлов: следующий хук получает судьбу автоматически по тому,
в какой из двух директорий он живёт. `.gitignore` ловит класс "per-project intent" паттернами
без ведущего `/` (`.claude/auto-approve.env.ini`, `.claude/memory.env.ini`,
`.claude/run-report.env.ini`, `.codex/memory.env.ini`) — совпадают на любой глубине дерева.

**Находка инвентаризации (не гипотеза):** до P5.3 трекинг был непоследовательным — один
класс, три судьбы. `.claude/run-report.env.ini` (per-project intent) был закоммичен вопреки
своему классу; `packages/skiller/.claude/auto-approve.env.ini` (тоже per-project intent, внутри
монорепо) был закоммичен исторически, до того как правило класса появилось в `.gitignore`.
Оба untracked этим item'ом (`git update-index --force-remove`, без команды с подстрокой `rm`);
`.gitignore` дополнен строками `.claude/run-report.env.ini` и `.codex/memory.env.ini`
(`auto-approve`/`memory` per-project паттерны уже покрывали любую глубину, включая
`packages/skiller/.claude/`).

## Лестница приоритета

Одинакова у обоих bash-читателей (`auto-approve`, `memory`):

```
$CLAUDE_PROJECT_DIR/.claude/<hook>.env.ini   (per-project override — если файл есть, используется он)
      ↓ (не найден)
<hookdir>/env.ini                             (шаблон-дефолт хука)
      ↓ (не найден)
"off"                                          (жёсткий дефолт в коде)
```

`memory`-хук на Codex-стороне дополнительно смотрит `.codex/memory.env.ini` (тот же
per-project класс, тот же формат) — `packages/harness/lib/harness/hooks.py:365`.

`run-report.py` и `maind/health.py` **не несут этой лестницы**: они читают ровно один путь
(`<cwd>/.claude/run-report.env.ini`, `<project>/.claude/memory.env.ini`) и на его отсутствие
падают на жёсткий дефолт в коде — второго слоя (`<hookdir>/env.ini`) у них нет. Не путать
«одна точка чтения + дефолт в коде» с лестницей приоритета — это разные конструкции одного
семейства.

## Схема формата (измерено, не предположено)

`KEY=VALUE`, один ключ на строку, `#`-комментарии и пустые строки пропускаются. Формат
разбирается самописно в четырёх местах (`auto-approve/lib/common.sh`, `memory/lib/common.sh`,
`run-report.py`, `maind/health.py`) — общий модуль-парсер здесь не заводится (кросс-языковая
граница bash↔python, P5.3 Scope Excluded).

**Неизвестный ключ (измерено прогоном, `packages/harness/tests/test_hooks.py`
`test_read_mode_ignores_unknown_key`):** все четыре читателя молча его игнорируют — ни ошибки,
ни варнинга. `FOO=bar` рядом с `MODE=permissive` не меняет разобранное значение `MODE`.
Практическое следствие: опечатка в имени ключа (`MODEE=…`) не диагностируется этим слоем —
хук просто откатится на следующую ступень лестницы/дефолт.

Известные ключи по хуку:

| Хук | Ключи | Допустимые значения |
|:--|:--|:--|
| `auto-approve` | `MODE` | `strict` \| `permissive` \| `bypass` \| `off` |
| `memory` (Claude Code) | `MODE` | `maind` \| `file` \| `federation` \| `agentmemory` \| `off` |
| `memory` (Codex) | `MODE`, `BRAIN` | `MODE` — тот же набор; `BRAIN` — имя brain (свободная строка) |
| `run-report` | `ENABLED`, `RUNS_KEEP`, `DIGEST` | `ENABLED`/`DIGEST` — `on`/`off`/`0`/`1`/`true`/`false`/`yes`/`no` (регистронезависимо); `RUNS_KEEP` — целое ≥ 1 |
| `agent-router` | `POLICY` | режимы `agent-router` (см. `hooks.py:block_router`) |

## Процедура правки

Правится вручную человеком/агентом — генератора нет. Новый хук с собственным `env.ini`
автоматически получает класс и судьбу трекинга по правилу выше — отдельного шага не требует.
