"""Canonical Layout-v2 fixtures shared by Harness black-box Task tests."""

import json
from pathlib import Path


def write_v2_plan(root, *, plan_id, items, routing_rows, next_line):
    """Create a generated v2 plan without hand-writing state, status, or bundles."""
    from packages.task.tests.fixtures import item_spec_md, phase_index_md, write_valid_plan
    from task import plan_bundle, plan_decisions, plan_item_state, plan_status

    root = Path(root)
    plan_dir = write_valid_plan(root, plan_id)
    phase_id = items[0][0].split(".", 1)[0]
    if any(item_id.split(".", 1)[0] != phase_id for item_id, _status in items):
        raise ValueError("fixture items must belong to one phase")
    source_phase_dir = plan_dir / "phases" / "P1"
    phase_dir = plan_dir / "phases" / phase_id
    if phase_dir != source_phase_dir:
        source_phase_dir.rename(phase_dir)
        for path in phase_dir.glob("P1*"):
            path.rename(phase_dir / path.name.replace("P1", phase_id, 1))
    first_item = items[0][0]

    (phase_dir / f"{phase_id}.md").write_text(phase_index_md(phase_id), encoding="utf-8")
    for item_id, _status in items:
        spec = item_spec_md(item_id).replace(
            f"### {item_id} — Config validation",
            f"### {item_id} — Harness fixture",
        )
        (phase_dir / f"{item_id}.md").write_text(spec, encoding="utf-8")

    routing = "\n".join(
        f"| solo | {row[2:]}" if row.startswith("| ") else row
        for row in routing_rows
    )
    plan_path = plan_dir / "plan.md"
    plan_path.write_text(
        plan_path.read_text(encoding="utf-8").replace(
            "## 3. Routing\n\n",
            "## 3. Routing\n\n"
            "| Batch | Items | Model class/effort | Exec | Why |\n"
            "|:--|:--|:--|:--|:--|\n"
            f"{routing}\n\n",
        ),
        encoding="utf-8",
    )

    (plan_dir / "handoff.md").write_text(
        f"""# HANDOFF — 2026-08-01 — after {first_item}

**Next:** {next_line}

| Parameter | Meaning |
|:--|:--|
| Batch | solo |
| Model class | implementation |
| Effort | medium |
| Capabilities | fixture |
| Context | continue-root |
| The bottom line | v2 Harness fixture |
| Command | `{next_line}` |

**Done:** —
**Remaining:** fixture items.
**Sources of truth:** plan.md · phases/{phase_id}/{phase_id}.md
**Open risks:** —
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: —
- open_questions: —
""",
        encoding="utf-8",
    )
    (plan_dir / "roadmap.md").write_text(
        "# Roadmap executions - fixture\n\n"
        "| Item | Batch | Launch | Model/Thinking | Owner Gate | Note |\n"
        "|---|---|---|---|---|---|\n" + "".join(
            f"| {item_id} | solo | run | implementation/medium | — | fixture |\n"
            for item_id, _status in items
        ),
        encoding="utf-8",
    )

    events = []
    result_for_status = {
        "⬜ Not started": "in-progress",
        "🟡 In progress": "in-progress",
        "🟢 Done": "closed-green",
        "🟠 Done with deviations": "closed-deviations",
        "🔴 Blocked": "blocked",
    }
    for index, (item_id, status) in enumerate(items, start=1):
        events.append({
            "actor": "implementation/medium", "attempt": 1, "command": "plan-run",
            "cost_usd": None, "duration_ms": None, "friction": [], "item_id": item_id,
            "note": "v2 Harness fixture", "num_turns": None, "plan_id": plan_id,
            "result": result_for_status[status], "run_id": f"{index:064x}",
            "session_id": "fixture", "ts": f"2026-08-01T00:00:0{index}Z",
        })
    (plan_dir / "journal.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n" for event in events),
        encoding="utf-8",
    )
    for item_id, _status in items:
        plan_item_state.build_states(plan_dir, item_id=item_id)
        plan_bundle.build(plan_dir, item_id)
    plan_status.build_status(plan_dir)
    plan_decisions.build_views(plan_dir)
    return plan_dir
