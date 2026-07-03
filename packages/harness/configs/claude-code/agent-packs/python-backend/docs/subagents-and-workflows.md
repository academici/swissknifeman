# Субагенты и dev-loop — {{PACK_PREFIX}} (Python backend)

Стек: Python {{WEB_FRAMEWORK}}, менеджер `{{PKG_MANAGER}}`, бинарь `{{PY_BIN}}`.

## Роли (`.claude/agents/{{PACK_PREFIX}}-*.md`)

| Роль | Когда | Инструменты |
|:--|:--|:--|
| `slice-builder` | срез эндпоинта (router→service→repo→схема) | Edit/Write |
| `test-writer` | pytest по готовому коду до зелёного | Edit/Write |
| `type-checker` | узкий mypy-проход по диффу + предложения аннотаций | read-only |
| `reviewer` | read-only: ruff/mypy, слои, безопасность | read-only |
| `spec-writer` (опц.) | tech-spec перед крупным модулем | Write(docs) |
| `orchestrator` (из `_common`) | план Task→@role | read-only |

## dev-loop

`.claude/workflows/{{PACK_PREFIX}}-dev-loop.js` — impl→tests-to-green→type-check→review на
одной ветке. Скоуп срезов задаёт человек через `args.slices` (`{id,title,goal,
acceptance_criteria,skills?,risk?}`). `risk` (`LOW|MED|HIGH`) → Lean-tiering: impl
`LOW→haiku` иначе `sonnet`, review `LOW→sonnet · MED→opus/high · HIGH→opus/xhigh`,
type-check `sonnet`. Нет `risk` → дефолт `MED`; ревью идёт по `risk_level`, который вернул
test-writer.

## Гейты

- **SubagentStop** → `review-gate.sh` (`{{CHECK_CMD}}`).
- **PostToolUse** (Edit/Write `*.py`) → `validate-python.sh`: advisory ruff →
  additionalContext, НЕ блокирует.

## Уроки overnight-прогона (зашиты в workflow — соблюдай и вручную)

1. **Один branch на прогон**, хард-кап срезов литералом (`DEFAULT_MAX`) — переживает resume;
   circuit-breaker: 2 не-зелёных подряд → стоп.
2. **Модель/effort — по РИСКУ, не по умолчанию.** Дешёвые исполняют, дорогая проектирует/
   арбитрирует (тиры выше). Наследование родительской модели — осознанное исключение, не дефолт.
3. **Не поллить фоновые агенты** — уведомление приходит само; циклы опроса / `ScheduleWakeup`
   жгут контекст-кэш впустую.
4. **Промпты детерминированы — ради resume-кэша**: никаких timestamp/random; model/effort-
   override — отдельным параметром вызова. В большом фан-ауте логируй `budget.remaining()` после волны.
5. **Параллель — только по независимым файлам** (общая ветка = общее дерево).

Бакет `python` тонкий: канон фреймворков и pytest — в промптах агентов и `rules/`.
