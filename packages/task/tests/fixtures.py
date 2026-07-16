"""Фикстуры-шаблоны plan-протокола для unittest: строки plan.md/phases/Pn.md/handoff.md
байт-в-байт по `packages/skiller/skills/general/plan-protocol/snippets/*-template.md`
(один item на фазу — минимум, покрывающий все обязательные секции/поля). Тесты
мутируют эти строки точечными `.replace(...)`, чтобы получить один конкретный дефект
на кейс (не пересобирают шаблон руками — меньше шанса случайно сломать НЕ то поле)."""
import sys
from pathlib import Path

# На случай прямого запуска (`cd packages/task && python3 -m unittest discover -s tests`,
# без предварительного PYTHONPATH) — гарантируем lib/ в пути, как в maind/tests/fixtures.py.
_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))


def plan_md(plan_id, *, phase_id="P1", items_cell="1/1", phase_status="🟢 Done"):
    return f"""# {plan_id} — Демо-план

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | {plan_id} |
| Title | Демо-план |
| Version | 0.1.0 |
| Status | {phase_status} |
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Last Updated | 2026-07-02 |
| Repository | swissknifeman |
| Related Packages | task |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · haiku (LOW) · opus (design/audit) |
| Approval Owner | dv |

## 1. Context

Демо для unittest plan_lint.

## 2. Execution Rules

- Один item за раз.

## 3. Routing

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| {phase_id} | Фаза раз | {items_cell} | {phase_status} |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-02 | тест | тест |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-02 | issue-planner/opus | План создан |
"""


def phase_md(phase_id="P1", *, item_id="P1.1", item_status="🟢 Done",
             completion_notes="сделано, тест зелёный", known_deviations="—",
             escalation_needed="—", handoff_text="Фаза сдана: всё зелёное."):
    return f"""# {phase_id} — Фаза раз

## Phase Context

Демо-фаза.

## Phase Status

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| {item_id} | Валидация конфига | {item_status} | 2026-07-02 |

### {item_id} — Валидация конфига

**Status:** {item_status}
**Intent:** Добавить проверку.
**Why:** Диагностика дорогая.
**Scope Included:** load_config().
**Scope Excluded:** формат конфига.
**Inputs:** список ключей.
**Files:** lib/pkg/config.py
**Required Reads:** 1) lib/pkg/config.py
**Implementation Rules:** stdlib-only.
**Code Guidance:** ручная проверка dict-ключей.
**Validation:** bash scripts/test.sh — зелёный.
**Deliverables:** валидация + тест.
**Completion Notes:** {completion_notes}
**Pending Work:** —
**Known Deviations:** {known_deviations}
**Escalation Needed:** {escalation_needed}

## Phase Handoff

{handoff_text}
"""


def handoff_md(plan_id, *, item_id="P1.1"):
    # Next несёт launch-block (таблица `| Model |` + code-block) — канон 2.0;
    # без него green-path ловил бы warning «Next без launch-block».
    return f"""# HANDOFF — 2026-07-02 — after {item_id}

**Next:** /task:plan-exec {plan_id} {item_id}

| Параметр | Значение |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | fresh session |
| Суть | закрыть следующий item |

````
/task:plan-exec {plan_id} {item_id}
````

**Done:** {item_id} закрыт.
**Remaining:** ничего.
**Sources of truth:** plans/{plan_id}/plan.md · plans/{plan_id}/phases/P1.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
"""


def contracts_section(*, exported=(), consumed=()):
    """Опциональная секция `## 7. Contracts` (m7/D10) — дописывается к plan_md().
    `exported`: (контракт, версия, потребители); `consumed`: (контракт, донор, pinned)."""
    out = ["\n## 7. Contracts\n"]
    if exported:
        out.append("\n### Exported\n\n")
        out.append("| Контракт | Версия | Статус | Потребители | Уведомлены |\n")
        out.append("|:--|:--|:--|:--|:--|\n")
        for contract, version, consumers in exported:
            out.append(f"| {contract} | {version} | frozen | {consumers} | 2026-07-13 |\n")
    if consumed:
        out.append("\n### Consumed\n\n")
        out.append("| Контракт | Донор-план | Pinned | Замечено | Реакция |\n")
        out.append("|:--|:--|:--|:--|:--|\n")
        for contract, donor, pinned in consumed:
            out.append(f"| {contract} | {donor} | {pinned} | — | P1.1 — поднять |\n")
    return "".join(out)


def active_md(value="DEMO-1", *, updated="2026-07-02"):
    """plans/ACTIVE.md — канонический формат (4 строки, Phase Context SKM-MASTER-003/P1):
    `# ACTIVE`, пустая строка, `**Active:** <PLAN-ID>` (или «—»), `**Updated:** <дата>`."""
    return f"""# ACTIVE

**Active:** {value}
**Updated:** {updated}
"""


def brief_md(plan_id):
    return f"""# Бриф — {plan_id}

Переформулированный вход владельца: демо-план для тестов линтера.
"""


def write_valid_plan(root, plan_id="DEMO-1"):
    """Пишет полностью валидный план (plan-lint должен вернуть 0 ошибок/предупреждений).
    Возвращает Path на plans/<plan_id>."""
    plan_dir = Path(root) / "plans" / plan_id
    (plan_dir / "phases").mkdir(parents=True, exist_ok=True)
    (plan_dir / "brief").mkdir(parents=True, exist_ok=True)
    (plan_dir / "plan.md").write_text(plan_md(plan_id), encoding="utf-8")
    (plan_dir / "phases" / "P1.md").write_text(phase_md(), encoding="utf-8")
    (plan_dir / "handoff.md").write_text(handoff_md(plan_id), encoding="utf-8")
    (plan_dir / "brief" / "00-brief.md").write_text(brief_md(plan_id), encoding="utf-8")
    return plan_dir
