# Шаблон phases/Pn.md — файл фазы мастер-плана

Скелет фазы по протоколу `plan-protocol`: контекст, статус-таблица, items,
phase handoff. Первый item (P1.1) — полностью заполненный ОБРАЗЕЦ (какой уровень
детализации обязателен), второй (Pn.m) — пустой скелет с каноническим «—».

```markdown
# P1 — <Title фазы>

## Phase Context

<5–10 строк, самодостаточно: что делает фаза, на чём стоит, что считается
её завершением. Фаза исполнима без чтения других фаз.>

## Phase Status

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| P1.1 | Валидация конфига при загрузке | ⬜ Not started | <YYYY-MM-DD> |
| P1.2 | <title> | ⬜ Not started | <YYYY-MM-DD> |

### P1.1 — Валидация конфига при загрузке

**Status:** ⬜ Not started
**Intent:** Добавить в load_config() проверку обязательных ключей и типов до первого использования.
**Why:** Битый конфиг сейчас падает глубоко в рантайме с невнятным KeyError — диагностика дорогая.
**Scope Included:** функция load_config() и её тесты.
**Scope Excluded:** формат самого конфига; миграция существующих конфигов; CLI-флаги.
**Inputs:** список обязательных ключей — в докстринге load_config(); схема — schema/config.json.
**Files:** lib/pkg/config.py · tests/test_config.py
**Required Reads:** 1) lib/pkg/config.py 2) tests/test_config.py 3) schema/config.json
**Implementation Rules:** stdlib-only; сообщения die() на русском; существующее поведение валидных конфигов не менять.
**Code Guidance:** ручная проверка dict-ключей (НЕ jsonschema — pip запрещён); ошибки собирать списком и падать одним die() со всеми сразу; новые абстракции не вводить; обязательный тест на каждый класс ошибки (missing key, wrong type); запрещено глотать исключения через try/except pass.
**Validation:** bash scripts/test.sh — зелёный; ручной прогон с битым конфигом даёт внятную ошибку.
**Deliverables:** валидация в config.py + ≥3 новых теста. (Если item несёт RAG-выжимку/recon —
задекларируй файл здесь: `plans/<PLAN-ID>/findings/P1-config-validation.md`.)
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** —

### Pn.m — <Title>

**Status:** ⬜ Not started
**Intent:** —
**Why:** —
**Scope Included:** —
**Scope Excluded:** —
**Inputs:** —
**Files:** —
**Required Reads:** —
**Implementation Rules:** —
**Code Guidance:** —
**Validation:** —
**Deliverables:** —
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** —

## Phase Handoff

<Заполняется при закрытии фазы: что сдали, известные отклонения, что дальше.>
```
