"""Explicit Layout-v2 plan fixtures plus one isolated retired-layout rejection fixture."""
import sys
from pathlib import Path

# In case of direct launch (`cd packages/task && python3 -m unittest discover -s tests`,
# without prior PYTHONPATH) — guarantee lib/ in the path, as in maind/tests/fixtures.py.
_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))
_REPO_ROOT = Path(__file__).resolve().parents[3]
if (_REPO_ROOT / "core").is_dir() and str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def plan_md(plan_id, *, phase_id="P1", items_cell="1/1", phase_status="🟢 Done",
            closure_protocol=None, decision_log_rows=None, layout="v2"):
    # `closure_protocol` (P8.1/D42) — opt-in Meta-field `Closure Protocol`; None = no line
    # at all (additivity: a plan without a field must be linted byte-for-byte as before P8.1).
    closure_row = f"\n| Closure Protocol | {closure_protocol} |" if closure_protocol else ""
    layout_row = f"\n| Layout | {layout} |" if layout else ""
    # `decision_log_rows` (P8.2/D103-D105, research/23 §4): D-log is parameterized, not
    # is sewn in one line - gate `Consequences` runs tests on DIFFERENT cell contents
    # `Solution`/`Date`; None = old single line (byte-compat with do-P8.2 fixture).
    if decision_log_rows is None:
        decision_log_rows = "| D1 | 2026-07-02 | test | test |"
    decision_log = ("Solutions catalog: `decisions/`; collect: "
                    "`python3 packages/task/scripts/plan-views.py decisions`."
                    if layout == "v2" else
                    "| D# | Date | Solution | Why |\n|:--|:--|:--|:--|\n" + decision_log_rows)
    if layout == "v2":
        return f"""# {plan_id} — Demo plan

## 0. Meta

| Field | Meaning |
|:--|:--|
| Plan ID | {plan_id} |
| Title | Demo plan |
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

Demo for unittest plan_lint.

## 2. Execution Rules

- One item at a time.

## 3. Routing

## 5. Decision Log

{decision_log}
"""
    return f"""# {plan_id} — Demo plan

## 0. Meta

| Field | Meaning |
|:--|:--|
| Plan ID | {plan_id} |
| Title | Demo plan |
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

Demo for unittest plan_lint.

## 2. Execution Rules

- One item at a time.

## 3. Routing

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/total | Status |
|:--|:--|:--|:--|
| {phase_id} | Phase times | {items_cell} | {phase_status} |

## 5. Decision Log

{decision_log}

## 6. Update Log

| Date | Who (role/model) | What |
|:--|:--|:--|
| 2026-07-02 | issue-planner/opus | Plan created |
"""


def legacy_phase_md(phase_id="P1", *, item_id="P1.1"):
    """Return the one explicit retired-layout fixture used by rejection tests."""
    return f"""# {phase_id} — Phase times

## Phase Context

Demo phase.

## Phase Status

| ID | Title | Status | Updated |
|:--|:--|:--|:--|
| {item_id} | Config validation | 🟢 Done | 2026-07-02 |

### {item_id} — Config validation

**Status:** 🟢 Done
**Intent:** Add check.
**Why:** Diagnostics are expensive.
**Scope Included:** load_config().
**Scope Excluded:** config format.
**Inputs:** list of keys.
**Files:** lib/pkg/config.py
**Required Reads:** 1) lib/pkg/config.py
**Implementation Rules:** stdlib-only.
**Code Guidance:** manual check dict-keys.
**Validation:** bash scripts/test.sh — green.
**Deliverables:** validation + test.
**Completion Notes:** done, test green
**Pending Work:** —
**Known Deviations:** —
**Escalation Needed:** —

## Phase Handoff

Phase completed: everything is green.
"""


def phase_index_md(phase_id="P1", *, handoff_text="Phase completed: everything is green."):
    """Thin phase index v2: without statuses and without item-blocks."""
    return f"""# {phase_id} — Phase times

## Phase Context

Demo phase.

## Phase Handoff

{handoff_text}
"""


def item_spec_md(item_id="P1.1"):
    return f"""### {item_id} — Config validation

**Intent:** Add check.
**Why:** Diagnostics are expensive.
**Scope Included:** load_config().
**Scope Excluded:** config format.
**Inputs:** `lib/pkg/config.py`.
**Files:** lib/pkg/config.py
**Required Reads:** 1) lib/pkg/config.py
**Implementation Rules:** stdlib-only.
**Code Guidance:** manual check dict-keys.
**Validation:** bash scripts/test.sh — green.
**Deliverables:** validation + test.
"""


def item_state_md(*, item_status="🟢 Done", completion_notes="done, test green",
                  pending_work="—", known_deviations="—", escalation_needed="—"):
    return f"""**Status:** {item_status}
**Completion Notes:** {completion_notes}
**Pending Work:** {pending_work}
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


def write_v2_carriers(plan_dir, *, phase_id="P1", item_id=None, item_spec=None,
                      item_state=None, phase_index=None, refresh_views=True):
    """Write explicit Layout-v2 carriers without parsing a retired monolith."""
    plan_dir = Path(plan_dir)
    item_id = item_id or f"{phase_id}.1"
    phase_dir = plan_dir / "phases" / phase_id
    phase_dir.mkdir(parents=True, exist_ok=True)
    (phase_dir / f"{phase_id}.md").write_text(
        phase_index or phase_index_md(phase_id), encoding="utf-8")
    (phase_dir / f"{item_id}.md").write_text(
        item_spec or item_spec_md(item_id), encoding="utf-8")
    (phase_dir / f"{item_id}.state.md").write_text(
        item_state or item_state_md(), encoding="utf-8")

    if refresh_views:
        from task import plan_bundle, plan_decisions, plan_item_state, plan_status
        state_text = item_state or item_state_md()
        if "**Status:** 🟡 In progress" in state_text:
            import json

            journal_path = plan_dir / "journal.jsonl"
            entries = [json.loads(row) for row in journal_path.read_text(
                encoding="utf-8").splitlines() if row.strip()]
            entries[-1].update({
                "plan_id": plan_dir.name,
                "item_id": item_id,
                "result": "in-progress",
                "note": None,
            })
            journal_path.write_text("".join(
                json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"
                for entry in entries), encoding="utf-8")
            plan_item_state.build_states(plan_dir, item_id=item_id)
        plan_decisions.build_views(plan_dir)
        plan_status.build_status(plan_dir)
        plan_bundle.build(plan_dir, item_id)
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
        f"## Solution\n\n{decision}\n\n"
        f"## Why\n\n{reason}\n",
        encoding="utf-8")
    return path


def handoff_md(plan_id, *, item_id="P1.1"):
    # Next carries launch-block (table `| Model |` + code-block) — canon 2.0;
    # without it green-path would catch warning «Next without launch-block».
    return f"""# HANDOFF — 2026-07-02 — after {item_id}

**Next:** /task:plan-run {plan_id} {item_id}

| Parameter | Meaning |
|:--|:--|
| Model | sonnet |
| Thinking | medium |
| Context | fresh session |
| The bottom line | close next item |

````
/task:plan-run {plan_id} {item_id}
````

**Done:** {item_id} is closed.
**Remaining:** nothing.
**Sources of truth:** plans/{plan_id}/plan.md · plans/{plan_id}/phases/P1.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
"""


def contracts_section(*, exported=(), consumed=()):
    """Optional section `## 7. Contracts` (m7/D10) — is appended to plan_md().
    `exported`: (contract, version, consumers); `consumed`: (contract, donor, pinned)."""
    out = ["\n## 7. Contracts\n"]
    if exported:
        out.append("\n### Exported\n\n")
        out.append("| Contract | Version | Status | Consumers | Notified |\n")
        out.append("|:--|:--|:--|:--|:--|\n")
        for contract, version, consumers in exported:
            out.append(f"| {contract} | {version} | frozen | {consumers} | 2026-07-13 |\n")
    if consumed:
        out.append("\n### Consumed\n\n")
        out.append("| Contract | Donor plan | Pinned | Spotted | Reaction |\n")
        out.append("|:--|:--|:--|:--|:--|\n")
        for contract, donor, pinned in consumed:
            out.append(f"| {contract} | {donor} | {pinned} | — | P1.1 — raise |\n")
    return "".join(out)


def active_md(value="DEMO-1", *, updated="2026-07-02"):
    """plans/ACTIVE.md — canonical format (4 lines, Phase Context SKM-MASTER-003/P1):
    `# ACTIVE`, empty string, `**Active:** <PLAN-ID>` (or «—»), `**Updated:** <date>`."""
    return f"""# ACTIVE

**Active:** {value}
**Updated:** {updated}
"""


def brief_md(plan_id):
    return f"""# Brief — {plan_id}

Reworded owner input: demo plan for linter tests.
"""


def roadmap_md(plan_id):
    return f"""# Roadmap executions - {plan_id}

| Item | Batch | Launch | Model/Thinking | Owner Gate | Note |
|---|---|---|---|---|---|
| P1.1 | solo | run | sonnet/medium | — | the only one item demo plan |
"""


def journal_jsonl(plan_id, *, item_id="P1.1"):
    """journal.jsonl (P1.1) — one valid final record (diagram §2 contract)."""
    import json as _json
    entry = {
        "ts": "2026-07-02T00:00:00Z", "plan_id": plan_id, "item_id": item_id,
        "command": "plan-run", "session_id": None, "run_id": None, "attempt": 1,
        "actor": "sonnet/medium", "friction": [], "result": "closed-green",
        "cost_usd": None, "num_turns": None, "duration_ms": None, "note": "test",
    }
    return _json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n"


def closure_json(plan_id, *, phase_id="P1", item_id="P1.1", item_status="🟢 Done",
                 phase_status="🟢 Done", evidence_class="real",
                 evidence="bash packages/task/scripts/validate.sh — exit 0 (on abc1234)"):
    """closure/<Pn>.json (P8.1/D42) — phase closure report, diagram v1 (research/11 §1).
    All keys are required: «no number» is expressed by VALUE (`baseline_pending` + reason),
    and not the absence of a key."""
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
                   "evidence": "bash packages/task/scripts/validate.sh — exit 0 (on abc1234)"}],
        "metrics": [{"name": "lint_new_from_closure", "value": "0", "label": "real"}],
        "limitations": ["demo fixture, not field run"],
        "external_side_effects": [],
    }
    return _json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def write_closure(plan_dir, **kwargs):
    """Places closure/<Pn>.json next to the plan (directory is being created)."""
    plan_dir = Path(plan_dir)
    phase_id = kwargs.get("phase_id", "P1")
    (plan_dir / "closure").mkdir(parents=True, exist_ok=True)
    path = plan_dir / "closure" / f"{phase_id}.json"
    path.write_text(closure_json(plan_dir.name, **kwargs), encoding="utf-8")
    return path


def index_md(plan_id):
    return f"""# Index - {plan_id}

## Directory map

| Path | Purpose |
|:--|:--|
| `plan.md` | master plan |

## Provenance

| Source | Layer | Nourishes | The bottom line |
|:--|:--|:--|:--|
"""


def write_valid_plan(root, plan_id="DEMO-1", *, layout="v2"):
    """Writes a fully valid plan (plan-lint should return 0 errors/warnings).
    Returns Path on plans/<plan_id>."""
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
        phase_path.write_text(legacy_phase_md(), encoding="utf-8")
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
