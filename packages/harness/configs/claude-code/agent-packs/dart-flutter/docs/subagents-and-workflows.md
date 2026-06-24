# Субагенты и dev-loop — {{PACK_PREFIX}} (Flutter/Dart)

Стек: Flutter/Dart, цель {{TARGET_KIND}}, state {{STATE_MGMT}}; FFI: see `rules/ffi.md`.

## Роли (`.claude/agents/{{PACK_PREFIX}}-*.md`)

| Роль | Когда | Инструменты |
|:--|:--|:--|
| `slice-builder` | вертикальный срез экрана (экран→виджеты→state→repo) | Edit/Write |
| `test-writer` | flutter-тесты (widget+unit/golden) до зелёного | Edit/Write |
| `reviewer` | read-only: analyze/format, state, dispose, POS-embedded | read-only |
| `ffi-reviewer` (опц.) | узкий ревью FFI/нативной границы (память/ABI/isolate) | read-only |
| `spec-writer` (опц.) | tech-spec перед крупной фичей/интеграцией периферии | Write(docs) |
| `orchestrator` (из `_common`) | план Task→@role для крупной задачи | read-only |

## dev-loop

`.claude/workflows/{{PACK_PREFIX}}-dev-loop.js` — impl→tests-to-green→review на одной ветке.
Скоуп срезов задаёт человек через `args.slices`.

## Гейты

- **SubagentStop** → `review-gate.sh` (`{{CHECK_CMD}}`, режим в `review-gate.env.ini`).
- **PostToolUse** (Edit/Write `*.dart`) → `validate-flutter.sh`: advisory `dart analyze` →
  additionalContext, НЕ блокирует.

Модельные тиры — из профиля `dart-flutter` (`model_tiers`); по умолчанию `inherit`.
Бакет `mobile` тонкий: архитектура/state/FFI/POS живут в промптах агентов и `rules/`.
