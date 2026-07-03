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
Скоуп срезов задаёт человек через `args.slices` (`{id,title,goal,acceptance_criteria,
skills?,risk?}`). `risk` (`LOW|MED|HIGH`) → Lean-tiering: impl `LOW→haiku` иначе `sonnet`,
review `LOW→sonnet · MED→opus/high · HIGH→opus/xhigh`. Нет `risk` → дефолт `MED`; глубина/
модель ревью — по `risk_level`, который вернул test-writer.

## Гейты

- **SubagentStop** → `review-gate.sh` (`{{CHECK_CMD}}`, режим в `review-gate.env.ini`).
- **PostToolUse** (Edit/Write `*.dart`) → `validate-flutter.sh`: advisory `dart analyze` →
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

Бакет `mobile` тонкий: архитектура/state/FFI/POS живут в промптах агентов и `rules/`.
