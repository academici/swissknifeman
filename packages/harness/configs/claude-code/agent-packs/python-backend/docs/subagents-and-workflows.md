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
одной ветке. Скоуп срезов задаёт человек через `args.slices`.

## Гейты

- **SubagentStop** → `review-gate.sh` (`{{CHECK_CMD}}`).
- **PostToolUse** (Edit/Write `*.py`) → `validate-python.sh`: advisory ruff →
  additionalContext, НЕ блокирует.

Модельные тиры — из профиля `python-backend` (`model_tiers`); по умолчанию `inherit`.
Бакет `python` тонкий: канон фреймворков и pytest — в промптах агентов и `rules/`.
