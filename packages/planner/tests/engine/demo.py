"""Demo plan builder for store/ops/check tests: examples E1-E5 laid out as a v3 plan directory."""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path

_LIB = Path(__file__).resolve().parents[2] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from planner.plan import store, views  # noqa: E402

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


# Templates are private to this worker process and are never handed to a test.
# Each caller receives a separate tree; construction always exercises the public CLI.
@lru_cache(maxsize=8)
def _cli_seed(commands, environment):
    temporary = tempfile.TemporaryDirectory(prefix="planner-fixture-seed-")
    plans = Path(temporary.name) / "plans"
    cli = Path(__file__).resolve().parents[2] / "scripts" / "plan.py"
    # Run the real CLI with a deterministic store clock. Each invocation resumes
    # the previous one's counter, as the original in-process fixture did.
    runner = """import itertools
import runpy
import sys
from datetime import datetime, timedelta, timezone

main = runpy.run_path(sys.argv[2])["main"]
from planner.plan import store
clock = itertools.count(int(sys.argv[1]))
base = datetime(2026, 10, 7, tzinfo=timezone.utc)
store.now = lambda: (base + timedelta(seconds=next(clock))).strftime("%Y-%m-%dT%H:%M:%SZ")
code = main(sys.argv[3:])
print(next(clock))
raise SystemExit(code)
"""
    ticks = 0
    try:
        for command in commands:
            done = subprocess.run([sys.executable, "-c", runner, str(ticks), str(cli),
                                   *command, "--plans-root", str(plans)],
                                  env=dict(environment), capture_output=True, text=True, timeout=60)
            if done.returncode:
                raise RuntimeError(f"fixture CLI failed: {command}: {done.stderr}")
            ticks = int(done.stdout.splitlines()[-1])
        for path in Path(temporary.name).rglob("*"):
            path.chmod(path.stat().st_mode & ~0o222)
        return temporary, ticks
    except BaseException:
        temporary.cleanup()
        raise


def copy_cli_seed(plans_root, commands, *, clock):
    """Copy an immutable CLI-built seed, keyed by commands and the worker's environment."""
    environment = tuple(sorted(dict(os.environ, SKM_AICORE_EVENTS__DELIVERY="off").items()))
    seed, ticks = _cli_seed(tuple(tuple(c) for c in commands), environment)
    source = Path(seed.name)
    shutil.copytree(source, Path(plans_root).parent, dirs_exist_ok=True)
    for original in source.rglob("*"):
        path = Path(plans_root).parent / original.relative_to(source)
        path.chmod(path.stat().st_mode | (0o700 if path.is_dir() else 0o200))
    # Advance only this case's clock; cached seeds keep no mutable clock state.
    for _ in range(ticks):
        next(clock)
    return next(Path(plans_root).iterdir())
