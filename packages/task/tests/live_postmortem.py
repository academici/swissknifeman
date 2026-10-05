#!/usr/bin/env python3
"""Opt-in native reviewer acceptance on an isolated frozen Git fixture."""
import argparse
import json
from pathlib import Path
import shutil
import sys
import time

REPOSITORY = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY / "packages/task/lib"))
sys.path.insert(0, str(REPOSITORY))
from test_postmortem_execution import ExecutionFixtureTests
from task import plan_work, review_packet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reviewer", required=True, help="explicit owner-authorized native reviewer selector")
    parser.add_argument("--resume", action="store_true", help="continue the repaired candidate after a diagnosed incomplete transport")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "repo").exists() and not args.resume:
        parser.error("use a fresh output directory; native attempts are immutable")
    case = ExecutionFixtureTests("test_no_helpers_prepare_validate_close_and_resume")
    case.setUp()
    if not args.resume:
        shutil.copytree(case.root, output / "repo")
    case.doCleanups()
    case.root = output / "repo"
    case.plan = case.root / "plans/FLOW"
    case.spec = case.plan / "phases/P1/P1.1.md"
    case.actual["cwd"] = str(case.root)
    case.spec.write_text(case.spec.read_text().replace(
        "**Files:** lib/pkg/config.py", "**Files:** `lib/pkg/config.py`, `scripts/check.py`"))
    if not args.resume:
        case.spec.write_text(case.spec.read_text().replace(
            "**Intent:**", "**Intent:** Acceptance: config must define value = 2. Any other value is a major correctness defect. The declared check is intentionally a smoke test. "))
    # Source fixture route is synthetic and labelled; only the reviewer route is
    # attested by a real native session. This is not a live executor comparison.
    started = time.monotonic()
    report = {"fixture": "native-review-two-rounds", "executor_route": "synthetic-fixture",
              "requested_reviewer": args.reviewer, "rounds": [], "handwritten_workflow_helpers": 0}
    if args.resume:
        report = json.loads((output / "result.json").read_text())
        (output / "result-before-resume.json").write_text(json.dumps(report, indent=2) + "\n")
        report.pop("error", None)
    try:
        if not args.resume:
            case.prepare(reviewer=args.reviewer)
            plan_work.validate(case.plan, "P1.1", attempt_id="smoke-before-fix")
            candidate = plan_work.close(case.plan, "P1.1")
            if candidate["action"] != "review-ready":
                raise ValueError(f"expected review-ready, got {candidate['action']}")
            receipt = review_packet.run(case.plan, candidate["manifest"])
            report["rounds"].append(review_packet.summary(receipt, review_packet._location(case.plan, "P1.1")))
            if receipt["status"] != "complete" or receipt["verdict"]["verdict"] != "FINDINGS":
                raise ValueError("seeded defect must produce a completed FINDINGS verdict")
        (case.plan / "lib/pkg/config.py").write_text(
            "value = 2\n\ndef load_config(config=None):\n"
            "    candidate = {'value': value} if config is None else config\n"
            "    if not isinstance(candidate, dict) or set(candidate) != {'value'}:\n"
            "        raise ValueError('expected exactly the value key')\n"
            "    if candidate['value'] != 2:\n"
            "        raise ValueError('expected value = 2')\n"
            "    return dict(candidate)\n")
        (case.root / "scripts/check.py").write_text(
            "import runpy\n"
            "module = runpy.run_path('plans/FLOW/lib/pkg/config.py')\n"
            "load = module['load_config']\n"
            "assert module['value'] == 2 and load() == {'value': 2}\n"
            "assert load({'value': 2}) == {'value': 2}\n"
            "for invalid in ([], {}, {'value': 3}, {'unexpected': 2}, {'value': 2, 'extra': 1}):\n"
            "    try: load(invalid)\n"
            "    except ValueError: pass\n"
            "    else: raise AssertionError('missing dict-key validation')\n")
        case.prepare(reviewer=args.reviewer)
        plan_work.validate(case.plan, "P1.1", attempt_id="checked-owning-fix")
        candidate = plan_work.close(case.plan, "P1.1")
        receipt = review_packet.run(case.plan, candidate["manifest"])
        report["rounds"].append(review_packet.summary(receipt, review_packet._location(case.plan, "P1.1")))
        if receipt["status"] != "complete" or receipt["verdict"]["verdict"] != "GREEN":
            raise ValueError("owning fix must produce a completed GREEN verdict")
        closed = plan_work.close(case.plan, "P1.1")
        report.update(complete=closed["action"] == "complete", action=closed["action"])
    except (OSError, ValueError) as exc:
        report.update(complete=False, error=str(exc))
    finally:
        report["wall_seconds"] = round(report.get("wall_seconds", 0) + time.monotonic() - started, 3)
        (output / "result.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"complete": report["complete"], "rounds": len(report["rounds"]),
                      "result": str(output / "result.json"), "error": report.get("error")}))
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
