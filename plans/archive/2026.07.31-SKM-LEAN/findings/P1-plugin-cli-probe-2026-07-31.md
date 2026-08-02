# Живой замер CLI плагинов Claude Code (слой 1) — 2026-07-31

**Слой 1 (сырьё).** Прямой прогон автора плана на ЖИВОЙ установке, 2026-07-31.
Версия инструмента — `claude --version` → **2.1.220 (Claude Code)**.
Потребитель: **P1.1** (конструкция агрегатора), частично **P1.2** (стоимость фан-аута).

> Повод: Execution Rules плана требуют перепроверять любое утверждение о поведении
> Claude Code на живой версии. D13 проектировался от предположения «у `claude plugin`
> нет `--json`, поэтому агрегатор парсит текст». Замер это предположение **уточняет**.

## 1. `claude plugin --help` — состав подкоманд

`details` · `disable` · `enable` · `eval` · `init|new` · `install|i` · `list` ·
`marketplace` · `prune|autoremove` · `tag` · `uninstall|remove` · `update` · `validate`.

Заявленная справка `details`:

```text
Usage: claude plugin details [options] <name>
Show a plugin's component inventory and projected token cost
Options:
  -h, --help  Display help for command
```

## 2. `claude plugin list --json` — **существует**, в `--help` не заявлен

Флаг отсутствует в справке (`Options:` пусты), но работает и печатает валидный JSON
(exit 0). Это **недокументированная** поверхность — риск молчаливого исчезновения выше,
чем у документированной; отсюда требование регресс-теста и fail-loud в P1.1.

Ключи записи (полный набор, замер 55 записей):

```json
{
  "id": "codex@openai-codex",
  "version": "1.0.6",
  "scope": "user",
  "enabled": true,
  "installPath": "/home/vostrikov/.claude/plugins/cache/openai-codex/codex/1.0.6",
  "installedAt": "2026-07-29T06:07:07.255Z",
  "lastUpdated": "2026-07-29T06:07:07.255Z"
}
```

Дополнительно встречаются: `projectPath` (только у `scope: "local"`) и `errors: [...]`
(строки диагностики; замер — у `brain@brain`: «invalid manifest file … Validation errors:
commands: Invalid input, skills: Invalid input»). Оба ключа **опциональны** — их
отсутствие нормально.

Значения `scope` в замере: `local` 49 · `user` 5 · `project` 1.

### 2.1 Вывод CWD-ЗАВИСИМ — и это ровно то, что нужно для пер-проектной атрибуции

Один и тот же вызов из разных каталогов даёт разный `enabled`-набор:

| CWD | Enabled-плагинов | Разбивка |
|:--|--:|:--|
| `/tmp` | 4 | все `scope: user` |
| `/home/vostrikov/projects/packages/chatom` | 16 | `user` 4 · `local` 11 · `project` 1 |

Из `chatom` enabled-набор: `architect@swissknifeman` (local), `brain@brain` (user),
`codex@openai-codex` (user), `core@` · `devops@` · `laravel-auth@` · `laravel-data-layer@` ·
`laravel-testing@` · `php-packages@` · `php@` · `quality@` · `system@` · `task@` (local),
`maind@` · `skm@` (user), `task@swissknifeman` (**второй раз**, scope `project`).

**Два следствия для P1.1:**

1. эффективный набор плагинов проекта берётся вызовом с `cwd=<target>` — отдельного
   разбора `enabledPlugins` из `settings.json` не требуется (это и была отвергнутая
   D142 конструкция «skiller следит за раскладкой чужого продукта»);
2. **один `id` может прийти дважды** (разные `scope`) — дедупликация по `id`
   обязательна, иначе цена плагина удвоится в сумме.

## 3. `claude plugin details <id>` — `--json` **НЕТ**, формат текстовый

`claude plugin details codex@openai-codex --json` → `error: unknown option '--json'`.

Дословный вывод (первые строки, `codex@openai-codex`):

```text
codex 1.0.6
  Use Codex from Claude Code to review code or delegate tasks.
  Source: codex@openai-codex

Component inventory
  Skills (11)  adversarial-review, cancel, codex-cli-runtime, …
  Agents (1)  codex-rescue
  Hooks (3)  SessionStart, SessionEnd, Stop  (harness-only — no model context cost)
  MCP servers (0)
  LSP servers (0)

Projected token cost
  Always-on:   ~449 tok   added to every session

Per-component (rounded)
  component              always-on  on-invoke
  codex-cli-runtime            ~40      ~1.1k
  …
  On-invoke cost is paid each time a skill or agent fires.
  Token counts are estimates and may differ from actual usage.
```

Второй замер (`maind@swissknifeman`, 8 скиллов): `Always-on:   ~450 tok   added to every
session`.

**Единственная строка, нужная агрегатору:**

```text
  Always-on:   ~449 tok   added to every session
```

То есть текстовый парс сужается до ОДНОГО регэкспа по одной строке, а не до разбора
всего отчёта. Числа с суффиксом (`~1.1k`) встречаются только в пер-компонентной таблице —
в строке `Always-on` замер дал целые токены дважды; поведение при ≥1000 ток **не
наблюдалось** и должно трактоваться fail-loud, а не догадкой.

Согласуется с прецедентным замером `~449 ток` из архива
(`plans/archive/2026.07.25-ECO-OPT/findings/P7.3-plugin-cost-and-procedure.md:15,25`).

## 4. Стоимость вызовов (для фан-аута P1.2)

| Команда | `real` |
|:--|--:|
| `claude plugin list --json` | 0,19 с |
| `claude plugin details <id>` | 0,67 с |

`details` описывает ПЛАГИН, не проект, и от CWD не зависит → при обходе флота
`details` зовётся один раз на УНИКАЛЬНЫЙ `id`, а не на пару «проект × плагин».
Оценка полного обхода: 26 × 0,19 с + (уникальных плагинов ≈ 20) × 0,67 с ≈ **20 с**.

## 5. Реестр флота (вход P1.2)

Носитель — `config.json` в корне монорепо (`~/.maind/projects.json` пуст: `projects: []`),
читатель — `packages/maind/lib/maind/federation.py:21` `_enabled_projects`.

- записей **26**, все `enabled: true`;
- из них **4 — мусор**: `id: local-repo` с `local_path` внутри `/tmp/...` (следы прогонов
  тестов); каталоги частью уже не существуют;
- реальных проектов — **22** (agelto, diabox, flexcrm, axiomaerpsdk, azguard, botkit,
  vaulter, swissknifeman, axiomastudio, corex, memster, cms, edufy, vintera, dterema,
  dterema-app, sibintek-insiders, chatom, perplexity-web-mcp, loqum, brain, agentools).

Существующий фан-аут `maind doctor --context` (`doctor.py:128–158`) уже fail-soft:
несуществующий `local_path` → строка `context: "n/a"`, обход продолжается.

## 6. Конвенция закрытия roadmap-записи (вход P1.1)

`roadmap/README.md` несёт таблицу `## Закрыто и удалено (2026-07-25)` — «Спека | Где живёт
результат»; реализованная спека удаляется файлом и получает строку там.

**Замер:** `roadmap/budget-first-turn-plugin-visibility.md` **не упомянут ни в одной
таблице README** (`grep budget-first-turn roadmap/README.md` → 0 вхождений) — файл-сирота.
Следовательно закрытие требует не удаления строки, а ДОБАВЛЕНИЯ её в таблицу закрытых.

## 7. Что этим замером НЕ проверено (честная граница)

- поведение `Always-on` при значении ≥1000 ток (суффикс `k` или целое) — не наблюдалось;
- стабильность недокументированного `list --json` между версиями — по определению
  непроверяема одним замером; отсюда регресс-тест на фикстуре;
- `scope: "project"` (одна запись в замере) — механика его резолва не изучалась,
  для агрегатора он неотличим от прочих enabled-записей после дедупликации по `id`.
