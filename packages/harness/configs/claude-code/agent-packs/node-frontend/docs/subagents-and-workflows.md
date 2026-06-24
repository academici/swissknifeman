# Субагенты и dev-loop — {{PACK_PREFIX}} (Vue/Vite frontend)

Этот пак раздал в проект роли-субагенты и последовательный workflow. Стек: Vue/Vite,
вариант {{VUE_VARIANT}}, менеджер `{{PKG_MANAGER}}`.

## Роли (`.claude/agents/{{PACK_PREFIX}}-*.md`)

| Роль | Когда | Инструменты |
|:--|:--|:--|
| `component-builder` | одна переиспользуемая UI-единица (SFC + composable) | Edit/Write |
| `slice-builder` | вертикальный срез страницы/фичи (route→page→store→api) | Edit/Write |
| `test-writer` | тесты Vitest+test-utils по готовому коду до зелёного | Edit/Write |
| `reviewer` | read-only ревью: tsc/eslint, типы, структура, a11y | read-only |
| `spec-writer` (опц.) | tech-spec перед крупной многоэкранной фичей | Write(docs) |
| `orchestrator` (из `_common`) | разбивка крупной задачи на план Task→@role | read-only |

## dev-loop

`.claude/workflows/{{PACK_PREFIX}}-dev-loop.js` — на ОДНОЙ ветке по каждому срезу:
impl → tests-to-green → review-gate. Скоуп срезов задаёт человек:

```
args = { branch: 'feat/...', base: '{{BASE_BRANCH}}', max_slices: 3,
         slices: [ { id, title, goal, acceptance_criteria, skills? } ] }
```

## Гейты

- **SubagentStop** → `review-gate.sh` (`REVIEW_GATE_MODE` в `.claude/review-gate.env.ini`):
  быстрый `{{CHECK_CMD}}`.
- **PostToolUse** (Edit/Write `*.ts|*.vue`) → `validate-frontend.sh`: advisory, инжектит
  ошибки tsc/eslint в контекст, НЕ блокирует.

Модельные тиры агентов выставляет профиль `node-frontend` (`model_tiers`); по умолчанию
`inherit`.
