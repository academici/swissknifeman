"""Demo plan builder for store/ops/check tests: examples E1-E5 laid out as a v3 plan directory."""
import copy
import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from task.plan import store, views  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "valid"
PLAN_ID = "2026.10.05-№1-DEMO"
AUTHORING = {"provider": "claude-code", "model": "claude-opus-5-5", "effort": "high"}


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def write_doc(path: Path, doc: dict, kind: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(store.canonical_dump(doc, kind), encoding="utf-8")


def make_demo_plan(plans_root: Path) -> Path:
    """Plan PLAN7 with phase P1 (detailed; P1.1 done, P1.2 todo), decisions D1/D2 and a three-event log."""
    root = plans_root / PLAN_ID
    write_doc(root / "plan.json", fixture("plan-e1"), "plan")
    write_doc(root / "brief.json", fixture("brief-basic"), "brief")
    write_doc(root / "phases" / "P1" / "phase.json", fixture("phase-e2"), "phase")
    first = fixture("item-e3")
    write_doc(root / "phases" / "P1" / "P1.1.json", first, "item")
    second = copy.deepcopy(first)
    second.update(id="P1.2", title="Validate types", status="todo", depends_on=["P1.1"], related=[], decisions=[],
                  artifacts=[], result=None)
    write_doc(root / "phases" / "P1" / "P1.2.json", second, "item")
    accepted = fixture("decision-e4-accepted")
    accepted.update(id="D1", title="Collect all errors", supersedes=[], applies_to=["P1"])
    write_doc(root / "decisions" / "D1.json", accepted, "decision")
    write_doc(root / "decisions" / "D2.json", fixture("decision-e4-open"), "decision")
    events = [store.new_event("plan_created", "plan PLAN7 created", AUTHORING)]
    events += [fixture(f"log-event-e5-{name}") for name in ("start", "difficulty", "finish")]
    (root / "log.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in events), encoding="utf-8")
    views.render_all(store.load_plan(root))
    return root


def rewrite(root: Path, rel: str, change) -> None:
    """Mutate a JSON file in place with ``change(doc)``, bypassing the store (to build broken plans)."""
    path = root / rel
    doc = json.loads(path.read_text(encoding="utf-8"))
    change(doc)  # mutates in place; the return value is ignored
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
