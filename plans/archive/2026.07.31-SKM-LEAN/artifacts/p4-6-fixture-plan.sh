#!/usr/bin/env bash
# P4.6 — строитель ИЗОЛИРОВАННОЙ фикстуры для двупронговой приёмки драйвера exec-волны
# (`harness run`, D33): временный каталог со СВОИМ git-репозиторием, синтетический план
# `P4-6-FIXTURE` (фаза P1, два item'а `Exec = plan-exec`), настоящие `claude -p`-воркеры.
#
# Рабочее дерево ЭТОГО репозитория (swissknifeman) волной НЕ трогается (Implementation
# Rule 4, P4.6): фикстура — отдельный git-репозиторий в mktemp-каталоге. Плагин `task`
# доступен фикстуре БЕЗ копирования пакета — `.claude/settings.local.json` фикстуры
# регистрирует РЕАЛЬНЫЙ монорепо swissknifeman как directory-marketplace (абсолютный
# путь, тот же паттерн, что уже несёт `.claude/settings.local.json` этого репозитория:
# `extraKnownMarketplaces.swissknifeman.source.path`), плюс символическая ссылка
# `packages/task -> <монорепо>/packages/task` — она резолвит ТОЛЬКО тот единственный
# cwd-относительный путь, которым сами команды `plan-exec.md`/`plan-run.md` пользуются
# буквально (`PYTHONPATH=packages/task/lib`); `${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py`
# резолвится провайдером через переменную окружения плагина, символической ссылки не
# требует. `defaultMode: bypassPermissions` — политика ЭТОЙ фикстуры (Scope Excluded P4.6
# запрещает воркеру ставить `--permission-mode` САМОМУ — проектная настройка фикстуры не
# тот же рычаг, это её собственное окружение владельца, тем же паттерном, что несёт
# `.claude/settings.local.json` самого swissknifeman).
#
# Повторный прогон даёт ТУ ЖЕ фикстуру (то же содержимое plan.md/phases/P1.md/handoff.md
# по фиксированному шаблону ниже) в НОВОМ временном каталоге — Implementation Rule 4
# («воспроизводится строителем»), не байт-в-байт тот же путь (mktemp -d).
#
# Использование: p4-6-fixture-plan.sh [TARGET_DIR]
#   TARGET_DIR — опционально, каталог фикстуры (дефолт — mktemp -d). Печатает
#   АБСОЛЮТНЫЙ путь готовой фикстуры в stdout последней строкой (для скрипта-обёртки
#   приёмки: `--plans-root "$(p4-6-fixture-plan.sh)"/plans`).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAL_REPO="$(cd "$SCRIPT_DIR/../../.." && pwd)"
FIXTURE_PLAN_ID="P4-6-FIXTURE"

TARGET="${1:-$(mktemp -d)}"
mkdir -p "$TARGET"
cd "$TARGET"

git init -q
git config user.email "p4-6-fixture@example.com"
git config user.name "p4-6-fixture"

mkdir -p .claude packages "plans/$FIXTURE_PLAN_ID/phases" src tests

ln -sfn "$REAL_REPO/packages/task" packages/task

cat > .claude/settings.local.json <<EOF
{
  "permissions": {"defaultMode": "bypassPermissions"},
  "extraKnownMarketplaces": {
    "swissknifeman": {"source": {"source": "directory", "path": "$REAL_REPO"}}
  },
  "enabledPlugins": {"task@swissknifeman": true}
}
EOF

cat > "plans/$FIXTURE_PLAN_ID/plan.md" <<EOF
# $FIXTURE_PLAN_ID — Изолированная фикстура приёмки драйвера exec-волны (P4.6)

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | $FIXTURE_PLAN_ID |
| Title | Фикстура приёмки harness run (P4.6, план 2026.07.31-SKM-LEAN) |
| Version | 0.1.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Repository | p4-6-fixture (изолированный, вне swissknifeman) |
| Approval Owner | dv |

## 1. Context

Синтетический план — приёмочная фикстура для \`harness run\` (P4.6, D33). НЕ боевой план,
не читается никаким другим item'ом swissknifeman. Два item'а с настоящей правкой файла,
тестом и двумя коммитами каждый — доказывают, что волна замыкает цикл end-to-end.

## 2. Execution Rules

- Один item за раз; статус обновляется в плане до завершения работы.
- Статусы — 6 канонических строк байт-в-байт (\`plan-protocol\` §6).
- Закрытие item'а — ДВА коммита: item-коммит по путям \`Files\`, затем bookkeeping-коммит.
  \`git add -A\` / \`git commit -a\` запрещены.
- Перед закрытием — \`python3 -m pytest tests/ -q\` зелёный.
- \`plan-lint\` прогоняется ПОСЛЕ перезаписи \`handoff.md\`, счёт публикуется с атрибуцией
  (\`--baseline HEAD\`).

## 3. Routing

| Items | Model class/effort | Exec | Почему |
|:--|:--|:--|:--|
| P1.1 | implementation/medium | plan-exec | фикстура приёмки P4.6 — механическая правка |
| P1.2 | implementation/medium | plan-exec | фикстура приёмки P4.6 — механическая правка |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P1 | Фикстурная фаза | 0/2 | 🟡 In progress |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-08-01 | Два item'а, оба \`Exec=plan-exec\`, оба с реальной правкой | покрыть \`harness run\` end-to-end без утяжеления фикстуры |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-08-01 | package-implementer/sonnet | Фикстура создана (P4.6, \`p4-6-fixture-plan.sh\`) |
EOF

cat > "plans/$FIXTURE_PLAN_ID/phases/P1.md" <<EOF
# P1 — Фикстурная фаза

## Phase Context

Синтетическая фаза приёмочной фикстуры \`harness run\` (P4.6, план 2026.07.31-SKM-LEAN).
Оба item'а — механические правки одного крошечного модуля \`src/greet.py\`, специально
без design-решений: цель фазы — проверить ЦИКЛ драйвера, не квалификацию воркера.

## Phase Status

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| P1.1 | \`greet()\` — модуль + тест | ⬜ Not started | 2026-08-01 |
| P1.2 | \`farewell()\` — вторая функция + тест | ⬜ Not started | 2026-08-01 |

### P1.1 — \`greet()\` — модуль + тест

**Status:** ⬜ Not started
**Intent:** Создать модуль \`src/greet.py\` с функцией \`greet(name: str) -> str\`,
возвращающей \`f"Hello, {name}!"\`, и тест \`tests/test_greet.py\`, проверяющий
\`greet("World") == "Hello, World!"\`.
**Why:** Минимальная РЕАЛЬНАЯ единица работы (файл + тест + два коммита) для приёмки
драйвера — сложность предмета не нужна, нужен ПРАВДОПОДОБНЫЙ полный цикл plan-exec.
**Scope Included:** \`src/greet.py\` (функция \`greet\`), \`tests/test_greet.py\` (один
кейс), зелёный \`python3 -m pytest tests/ -q\`.
**Scope Excluded:** любая другая функциональность; \`farewell\` (Scope P1.2).
**Inputs:** —
**Files:** \`src/greet.py\`, \`tests/test_greet.py\`
**Required Reads:** 1) \`plans/$FIXTURE_PLAN_ID/plan.md\` (контекст и §2 Execution Rules —
committed execution input этого item'а, tier \`committed-bundle\` требует непустой список).
**Implementation Rules:** (1) Только stdlib. (2) Сигнатура РОВНО \`def greet(name: str) -> str\`.
**Code Guidance:** Без docstring-простыней — одна строка тела функции.
**Validation:** \`python3 -m pytest tests/test_greet.py -q\` — зелёный.
**Deliverables:** \`src/greet.py\`, \`tests/test_greet.py\`, зелёный прогон pytest.
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** no

### P1.2 — \`farewell()\` — вторая функция + тест

**Status:** ⬜ Not started
**Intent:** Добавить в \`src/greet.py\` функцию \`farewell(name: str) -> str\`, возвращающую
\`f"Goodbye, {name}!"\`, и тест-кейс в \`tests/test_greet.py\`, проверяющий
\`farewell("World") == "Goodbye, World!"\`.
**Why:** Второй РЕАЛЬНЫЙ item очереди — проверяет, что волна доезжает до ВТОРОГО item'а
после закрытия первого (не только «один прогон работает»).
**Scope Included:** правка \`src/greet.py\` (добавление \`farewell\`, \`greet\` не трогается),
новый тест-кейс в \`tests/test_greet.py\`, зелёный \`python3 -m pytest tests/ -q\` (оба теста).
**Scope Excluded:** любая другая функциональность.
**Inputs:** \`src/greet.py\` (Deliverable P1.1 — модуль уже существует).
**Files:** \`src/greet.py\`, \`tests/test_greet.py\`
**Required Reads:** 1) \`src/greet.py\` целиком (существующая форма модуля, Deliverable P1.1).
**Implementation Rules:** (1) Только stdlib. (2) Сигнатура РОВНО \`def farewell(name: str) -> str\`.
**Code Guidance:** Без docstring-простыней — одна строка тела функции.
**Validation:** \`python3 -m pytest tests/ -q\` — зелёный (оба теста).
**Deliverables:** обновлённый \`src/greet.py\`, обновлённый \`tests/test_greet.py\`, зелёный
прогон pytest.
**Completion Notes:** —
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** no

## Phase Handoff

<Заполняется при закрытии фазы.>
EOF

cat > "plans/$FIXTURE_PLAN_ID/handoff.md" <<EOF
# HANDOFF — 2026-08-01 — after P0.0

**Next:** exec-items: task:plan-exec $FIXTURE_PLAN_ID P1.1

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | medium |
| Context | continue (/clear) |
| Суть | фикстура приёмки \`harness run\` (P4.6) — план ещё не тронут |

\`\`\`
/task:plan-exec $FIXTURE_PLAN_ID P1.1
\`\`\`

**Done:** —
**Remaining:** P1.1, P1.2.
**Sources of truth:** plans/$FIXTURE_PLAN_ID/plan.md · plans/$FIXTURE_PLAN_ID/phases/P1.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
EOF

git add -A
git commit -q -m "фикстура: $FIXTURE_PLAN_ID создан (P4.6, p4-6-fixture-plan.sh)"

echo "$TARGET"
