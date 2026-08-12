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
_REPO_ROOT = Path(__file__).resolve().parents[3]
if (_REPO_ROOT / "core").is_dir() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def plan_md(plan_id, *, phase_id="P1", items_cell="1/1", phase_status="🟢 Done",
            closure_protocol=None, decision_log_rows=None, layout="v2"):
    # `closure_protocol` (P8.1/D42) — opt-in Meta-поле `Closure Protocol`; None = строки нет
    # вовсе (аддитивность: план без поля обязан линтоваться байт-в-байт как до P8.1).
    closure_row = f"\n| Closure Protocol | {closure_protocol} |" if closure_protocol else ""
    layout_row = f"\n| Layout | {layout} |" if layout else ""
    # `decision_log_rows` (P8.2/D103-D105, research/23 §4): D-лог параметризован, а не
    # зашит одной строкой — гейт `Consequences` гоняет тесты на РАЗНОМ содержимом ячейки
    # `Решение`/`Дата`; None = прежняя единственная строка (byte-compat с до-P8.2 фикстурой).
    if decision_log_rows is None:
        decision_log_rows = "| D1 | 2026-07-02 | тест | тест |"
    decision_log = ("Каталог решений: `decisions/`; собрать: "
                    "`python3 packages/task/scripts/plan-views.py decisions`."
                    if layout == "v2" else
                    "| D# | Дата | Решение | Почему |\n|:--|:--|:--|:--|\n" + decision_log_rows)
    if layout == "v2":
        return f"""# {plan_id} — Демо-план

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | {plan_id} |
| Title | Демо-план |
| Layout | v2 |{closure_row}
| Document Type | Executable Master Plan |
| Authoring Model | opus |
| Repository | swissknifeman |
| Related Packages | task |
| Execution Mode | phase-first |
| Target Operator Models | sonnet (exec) · haiku (LOW) · opus (design/audit) |
| Approval Owner | dv |
| Home | repo:swissknifeman |
| Design Passes | 1/1 |
| visibility | private |

## 1. Context

Демо для unittest plan_lint.

## 2. Execution Rules

- Один item за раз.

## 3. Routing

## 5. Decision Log

{decision_log}
"""
    return f"""# {plan_id} — Демо-план

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | {plan_id} |
| Title | Демо-план |
| Version | 0.1.0 |
| Status | {phase_status} |{closure_row}{layout_row}
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

{decision_log}

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-02 | issue-planner/opus | План создан |
"""


def phase_md(phase_id="P1", *, item_id="P1.1", item_status="🟢 Done",
             completion_notes="сделано, тест зелёный", known_deviations="—",
             escalation_needed="—", handoff_text="Фаза сдана: всё зелёное.",
             updated="2026-07-02"):
    return f"""# {phase_id} — Фаза раз

## Phase Context

Демо-фаза.

## Phase Status

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| {item_id} | Валидация конфига | {item_status} | {updated} |

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


def phase_index_md(phase_id="P1", *, handoff_text="Фаза сдана: всё зелёное."):
    """Тонкий индекс фазы v2: без статусов и без item-блоков."""
    return f"""# {phase_id} — Фаза раз

## Phase Context

Демо-фаза.

## Phase Handoff

{handoff_text}
"""


def item_spec_md(item_id="P1.1"):
    return f"""### {item_id} — Валидация конфига

**Intent:** Добавить проверку.
**Why:** Диагностика дорогая.
**Scope Included:** load_config().
**Scope Excluded:** формат конфига.
**Inputs:** `lib/pkg/config.py`.
**Files:** lib/pkg/config.py
**Required Reads:** 1) lib/pkg/config.py
**Implementation Rules:** stdlib-only.
**Code Guidance:** ручная проверка dict-ключей.
**Validation:** bash scripts/test.sh — зелёный.
**Deliverables:** валидация + тест.
"""


def item_state_md(*, item_status="🟢 Done", completion_notes="сделано, тест зелёный",
                  known_deviations="—", escalation_needed="—"):
    return f"""**Status:** {item_status}
**Completion Notes:** {completion_notes}
**Pending Work:** —
**Known Deviations:** {known_deviations}
**Escalation Needed:** {escalation_needed}
"""


def phase_index_path(plan_dir, phase_id="P1"):
    """Return the v2 phase-index carrier path used by fixture mutations."""
    return Path(plan_dir) / "phases" / phase_id / f"{phase_id}.md"


def item_spec_path(plan_dir, item_id="P1.1"):
    """Return the v2 immutable item-spec carrier path."""
    phase_id = item_id.split(".", 1)[0]
    return Path(plan_dir) / "phases" / phase_id / f"{item_id}.md"


def item_state_path(plan_dir, item_id="P1.1"):
    """Return the v2 generated outcome carrier path."""
    phase_id = item_id.split(".", 1)[0]
    return Path(plan_dir) / "phases" / phase_id / f"{item_id}.state.md"


def write_v2_phase_from_legacy(plan_dir, text, *, phase_id="P1", refresh_views=True):
    """Split a legacy combined phase fixture into the canonical v2 test carriers.

    This is a test migration adapter, not a runtime compatibility path.  It lets
    focused tests keep expressing one malformed semantic condition with the old
    compact builder while every executable fixture on disk remains Layout v2.
    """
    import re

    plan_dir = Path(plan_dir)
    phase_dir = plan_dir / "phases" / phase_id
    phase_dir.mkdir(parents=True, exist_ok=True)
    item_match = re.search(r"(?ms)^### (P\d+\.\d+) — .+?(?=^## Phase Handoff\s*$|\Z)", text)
    if item_match:
        item_block = item_match.group(0).replace(
            "**Inputs:** список ключей.", "**Inputs:** `lib/pkg/config.py`.").rstrip() + "\n"
        item_id = item_match.group(1)
        lines = item_block.splitlines()
        spec_fields = set(("Intent", "Why", "Scope Included", "Scope Excluded", "Inputs",
                           "Files", "Required Reads", "Implementation Rules", "Code Guidance",
                           "Validation", "Deliverables"))
        state_fields = set(("Status", "Completion Notes", "Pending Work", "Known Deviations",
                            "Escalation Needed"))
        spec = [lines[0], ""]
        state = []
        extras = []
        last_target = None
        for line in lines[1:]:
            field = re.match(r"^\*\*([^*]+):\*\*", line)
            if field and field.group(1) in spec_fields:
                spec.append(line)
                last_target = spec
            elif field and field.group(1) in state_fields:
                state.append(line)
                last_target = state
            elif line.startswith(">"):
                extras.append(line)
            elif line.strip() and not field:
                (last_target if last_target is not None else extras).append(line)
        if extras:
            spec.extend(("", *extras))
        (phase_dir / f"{item_id}.md").write_text("\n".join(spec).rstrip() + "\n", encoding="utf-8")
        (phase_dir / f"{item_id}.state.md").write_text(
            "\n".join(state).rstrip() + "\n", encoding="utf-8")

    context = re.search(r"(?ms)^## Phase Context\s*\n(.*?)(?=^## |^### |\Z)", text)
    handoff = re.search(r"(?ms)^## Phase Handoff\s*\n(.*?)(?=^## |\Z)", text)
    title = next((line for line in text.splitlines() if line.startswith("# ")), f"# {phase_id} — Фаза")
    index = (f"{title}\n\n## Phase Context\n\n"
             f"{(context.group(1).strip() if context else '')}\n\n"
             f"## Phase Handoff\n\n{(handoff.group(1).strip() if handoff else '')}\n")
    (phase_dir / f"{phase_id}.md").write_text(index, encoding="utf-8")

    if refresh_views:
        try:
            import json as _json
            from task import plan_bundle, plan_decisions, plan_item_state, plan_status
            status_value = next((line.split(":**", 1)[1].strip() for line in state
                                 if line.startswith("**Status:**")), "") if item_match else ""
            if status_value == "🟡 In progress":
                journal_path = plan_dir / "journal.jsonl"
                entries = [_json.loads(row) for row in journal_path.read_text(
                    encoding="utf-8").splitlines() if row.strip()]
                entries[-1]["result"] = "in-progress"
                entries[-1]["note"] = None
                journal_path.write_text("".join(
                    _json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
                    for entry in entries), encoding="utf-8")
                plan_item_state.build_states(plan_dir, item_id=item_match.group(1))
            plan_decisions.build_views(plan_dir)
            plan_status.build_status(plan_dir)
            if item_match:
                plan_bundle.build(plan_dir, item_match.group(1))
        except Exception:
            # Malformed fixtures intentionally exercise the owning linter error.
            pass
    return phase_dir


def write_decision_record(plan_dir, identifier, *, decision="test", reason="RAG:—",
                          item_id="P1.1", date="2026-07-20"):
    """Write one canonical v2 decision fixture."""
    path = Path(plan_dir) / "decisions" / f"{identifier}-fixture.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"id: {identifier}\n"
        f"date: {date}\n"
        "status: accepted\n"
        f"item: {item_id}\n"
        f"items: [{item_id}]\n"
        "supersedes: []\n"
        "superseded_by: null\n"
        "---\n"
        f"## Решение\n\n{decision}\n\n"
        f"## Почему\n\n{reason}\n",
        encoding="utf-8")
    return path


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


def roadmap_md(plan_id):
    return f"""# Roadmap исполнения — {plan_id}

| Item | Batch | Запуск | Model/Thinking | Гейт владельца | Примечание |
|---|---|---|---|---|---|
| P1.1 | solo | plan-exec | sonnet/medium | — | единственный item демо-плана |
"""


def journal_jsonl(plan_id, *, item_id="P1.1"):
    """journal.jsonl (P1.1) — одна валидная финальная запись (схема §2 контракта)."""
    import json as _json
    entry = {
        "ts": "2026-07-02T00:00:00Z", "plan_id": plan_id, "item_id": item_id,
        "command": "plan-exec", "session_id": None, "run_id": None, "attempt": 1,
        "actor": "sonnet/medium", "friction": [], "result": "closed-green",
        "cost_usd": None, "num_turns": None, "duration_ms": None, "note": "тест",
    }
    return _json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"


def closure_json(plan_id, *, phase_id="P1", item_id="P1.1", item_status="🟢 Done",
                 phase_status="🟢 Done", evidence_class="real",
                 evidence="bash packages/task/scripts/validate.sh — exit 0 (на abc1234)"):
    """closure/<Pn>.json (P8.1/D42) — отчёт закрытия фазы, схема v1 (research/11 §1).
    Все ключи обязательны: «нет числа» выражается ЗНАЧЕНИЕМ (`baseline_pending` + причина),
    а не отсутствием ключа."""
    import json as _json
    report = {
        "schema_version": 1,
        "plan": plan_id,
        "phase": phase_id,
        "closed_at": "2026-07-02",
        "closed_by": {"command": "plan-close", "actor": "implementation/low"},
        "phase_status": phase_status,
        "git": {"head_sha": "0" * 40, "branch": "main", "dirty": False},
        "inputs_sha256": {"plan.md": "1" * 64, f"phases/{phase_id}.md": "2" * 64},
        "items": [{"id": item_id, "status": item_status,
                   "evidence_class": evidence_class, "evidence": evidence}],
        "gates": [{"id": "validate.sh:task", "status": "PASS", "evidence_class": "real",
                   "evidence": "bash packages/task/scripts/validate.sh — exit 0 (на abc1234)"}],
        "metrics": [{"name": "lint_new_from_closure", "value": "0", "label": "real"}],
        "limitations": ["демо-фикстура, не полевой прогон"],
        "external_side_effects": [],
    }
    return _json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_closure(plan_dir, **kwargs):
    """Кладёт closure/<Pn>.json рядом с планом (каталог создаётся)."""
    plan_dir = Path(plan_dir)
    phase_id = kwargs.get("phase_id", "P1")
    (plan_dir / "closure").mkdir(parents=True, exist_ok=True)
    path = plan_dir / "closure" / f"{phase_id}.json"
    path.write_text(closure_json(plan_dir.name, **kwargs), encoding="utf-8")
    return path


def index_md(plan_id):
    return f"""# Индекс — {plan_id}

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | мастер-план |

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
"""


def write_valid_plan(root, plan_id="DEMO-1", *, layout="v2"):
    """Пишет полностью валидный план (plan-lint должен вернуть 0 ошибок/предупреждений).
    Возвращает Path на plans/<plan_id>."""
    plan_dir = Path(root) / "plans" / plan_id
    (plan_dir / "phases").mkdir(parents=True, exist_ok=True)
    (plan_dir / "brief").mkdir(parents=True, exist_ok=True)
    config = plan_dir / "lib" / "pkg" / "config.py"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text("VALUE = 'fixture'\n", encoding="utf-8")
    (plan_dir / "plan.md").write_text(plan_md(plan_id, layout=layout), encoding="utf-8")
    phase_path = plan_dir / "phases" / "P1.md"
    if layout == "v2":
        phase_path = plan_dir / "phases" / "P1" / "P1.md"
        phase_path.parent.mkdir()
        (plan_dir / "decisions").mkdir()
        contract = plan_dir / "root" / "contracts" / "read-budget-v1.md"
        contract.parent.mkdir(parents=True, exist_ok=True)
        contract.write_text(
            "# read-budget fixture\n\n**Version:** `1.1.0`\n\n"
            "```text\npass_item(i) = estimated_required_read_tokens(i) <= 100000\n```\n",
            encoding="utf-8")
        phase_path.write_text(phase_index_md(), encoding="utf-8")
        (phase_path.parent / "P1.1.md").write_text(item_spec_md(), encoding="utf-8")
    else:
        phase_path.write_text(phase_md(), encoding="utf-8")
    (plan_dir / "handoff.md").write_text(handoff_md(plan_id), encoding="utf-8")
    (plan_dir / "brief" / "00-brief.md").write_text(brief_md(plan_id), encoding="utf-8")
    (plan_dir / "roadmap.md").write_text(roadmap_md(plan_id), encoding="utf-8")
    (plan_dir / "journal.jsonl").write_text(journal_jsonl(plan_id), encoding="utf-8")
    (plan_dir / "index.md").write_text(index_md(plan_id), encoding="utf-8")
    if layout == "v2":
        from task import plan_bundle, plan_item_state, plan_status
        plan_item_state.build_states(plan_dir, item_id="P1.1")
        plan_bundle.build(plan_dir, "P1.1")
        plan_status.build_status(plan_dir)
    return plan_dir
