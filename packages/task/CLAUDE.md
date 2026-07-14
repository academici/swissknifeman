# CLAUDE.md — task

Гид по кодовой базе для агентов. Это пакет **интент-команд постановки задач** экосистемы
academici: набор slash-команд `/task:*` для Claude Code, каждая из которых пинит свою
модель + reasoning effort (+ где нужно — workflow-профиль), перебивая настройки текущей
сессии, чтобы не держать в голове ручное переключение. Второй блок команд —
**plan-протокол** (`/task:plan-*`): исполняемые мастер-планы в `plans/<PLAN-ID>/` с
детерминированным линтером схемы. Пакет **plugin-only** — своего `bin/`/CLI/`install.sh`
у него нет, доставляется через marketplace/vendor skiller-канал (см. корневой CLAUDE.md).

## Что это

- **Интент-команды** (`commands/{design,dev,fix,research,review}.md`) — типовые задачи
  (проектирование/разработка/мелкая правка/исследование/ревью), у каждой в frontmatter
  зашиты `model`/`effort` под профиль задачи (напр. `review` → opus/xhigh — adversarial
  read-only, `fix` → sonnet/medium — token-frugal).
- **Plan-протокол** (`commands/plan-{design,exec,close,audit}.md`) — SSOT схемы живёт в
  скилле `packages/skiller/skills/general/plan-protocol/SKILL.ru.md`; команды пакета
  `task` — исполнительный слой поверх этой схемы (`plan-design` проектирует, `plan-exec`
  исполняет item, `plan-close` реконсилирует/закрывает, `plan-audit` — adversarial-аудит
  закрытой фазы). Третий режим исполнения — `commands/plan-run.md` (D18): БЕЗ пина
  `model`/`effort`, наследует модель/effort сессии владельца — делегирует протокол
  `plan-exec` с инвертированным routing-гейтом, снимает ритуал `/model`+`/effort` перед
  серией `Exec = manual` item'ов.
- **`lib/task/plan_lint.py`** (+ `scripts/plan-lint.py` — тонкий bash/python-лаунчер) —
  детерминированный валидатор структуры `plans/<PLAN-ID>/{plan.md, phases/Pn.md,
  handoff.md}`: 6 канонических статусов, обязательные секции/таблицы, единый формат
  handoff. Вызывается всеми `plan-*`-командами и `scripts/validate.sh`.

## Раскладка

- `commands/*.md` — slash-команды плагина (frontmatter: `description`/`model`/`effort`,
  тело — инструкция агенту).
- `lib/task/` — `plan_lint.py` (валидатор) + `__init__.py`. **stdlib-only**.
- `scripts/plan-lint.py` — лаунчер: резолвит `core/` монорепо на PYTHONPATH опционально
  (fallback на standalone-раскладку, как у остальных пакетов).
- `.claude-plugin/plugin.json` — манифест плагина (командный список, без MCP-сервера).
- `tests/` — `unittest` (`test_plan_lint.py` + `fixtures.py`), без сети.

## Конвенции (соблюдай при правках)

- **stdlib-only** в `lib/task/` — как во всех python-пакетах монорепо.
- **Каждая команда пинит модель+effort под свою задачу** — правя `commands/*.md`, не
  меняй `model`/`effort` без явного намерения; это принятое SSOT-решение по типу задачи
  (`plan.md` §Routing проектов ссылается на ту же матрицу).
- **`plan_lint.py` — единственный источник истины схемы плана** наравне со скиллом
  `plan-protocol`; расхождение (лишний/недостающий статус, другая структура секций) —
  правь оба места синхронно, не только одно.
- **Нет `bin/`/CLI/`install.sh` осознанно** — пакет не участвует в
  `swissknifeman <group>`-роутинге и не ставится корневым `install.sh` (см. его
  комментарий у `for pkg in skiller harness maind analyst`).
- Сообщения — на русском, как в остальных пакетах.

## Разработка

```bash
bash packages/task/scripts/validate.sh   # py_compile + bash -n + обязательные файлы +
                                          # frontmatter slash-команд + unittest +
                                          # (если в монорепо есть plans/) plan-lint.py по ним
```

Коммиты — Conventional Commits, на русском. Перед PR: `scripts/validate.sh` зелёный.
