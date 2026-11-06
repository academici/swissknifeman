"""Restore a pinned reviewer after a recorded, interrupted automatic route upgrade."""
import json
from pathlib import Path

from orch import contracts
from orch.conductor import checks, progress, records
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import RunStore, read_json, safe, write_json
from orch.conductor.policies.routing import exact_reviewer


def add_parser(verbs):
    parser = verbs.add_parser("restore-reviewer", help="restore a pinned reviewer after an interrupted automatic upgrade")
    parser.add_argument("--run", required=True)
    parser.add_argument("--item", required=True)
    parser.add_argument("--expected-digest", required=True)


def run(args, project):
    print(json.dumps(restore(project, args.run, args.item, args.expected_digest), ensure_ascii=False))
    return 0


def restore(project: Path, run_id: str, ref: str, expected_digest: str) -> dict:
    store = RunStore(project, run_id)
    with store.ownership("restore-reviewer", checkout=True):
        run, state = store.load()
        item = (state.get("items") or {}).get(ref)
        if state.get("status") not in ("stopped", "waiting") or not item:
            raise Stop("RESTORE_REFUSED", "run must be stopped and contain the item")
        overrides = item.get("route_overrides") or {}
        previous = overrides.get("reviewer")
        if not previous:
            raise Stop("RESTORE_REFUSED", "no saved reviewer override")
        folder = store.directory / safe(ref)
        options = records.read(folder / "options.json", "item-options")
        input_doc = read_json(folder / "input.json")
        if not options or not input_doc or not exact_reviewer(options["options"], options["sources"], input_doc):
            raise Stop("RESTORE_REFUSED", "item does not have a pinned reviewer without fallback")
        lines = progress.read_lines(store.directory)
        upgrades = [line for line in lines if line.get("item") == ref and line.get("reason_code") == "ROUTE_UPGRADED"]
        if not upgrades:
            raise Stop("RESTORE_REFUSED", "no recorded automatic reviewer upgrade")
        steps = item.get("steps") or {}
        reviews = [value for key, value in steps.items() if key.startswith("review.")]
        if any(row.get("status") == "done" for row in reviews):
            raise Stop("RESTORE_REFUSED", "completed review requires separate reconciliation")
        green = [value for key, value in steps.items() if key.startswith("checks.") and value.get("verdict") == "green"]
        if not green:
            raise Stop("RESTORE_REFUSED", "no successful acceptance check")
        rows = green[-1].get("result") or []
        evidence_paths = [row.get("evidence") for row in rows if row.get("green") and row.get("evidence")]
        if not evidence_paths:
            raise Stop("RESTORE_REFUSED", "missing successful check evidence")
        for name in evidence_paths:
            path = (project / name).resolve()
            if not path.is_relative_to(project.resolve()):
                raise Stop("RESTORE_REFUSED", "evidence path leaves project")
            evidence = read_json(path)
            if not isinstance(evidence, dict) or any(x.level == "error" for x in contracts.validate(evidence, "check-evidence")):
                raise Stop("RESTORE_REFUSED", "invalid check evidence")
            candidate = (evidence or {}).get("candidate") or {}
            exclude = [str(path.parent.relative_to(project.resolve()))]
            passed = evidence.get("exit") == 0 or (evidence.get("verdict") == "pass" and
                                                   (evidence.get("producer") or {}).get("kind") == "executor")
            if not passed or candidate.get("dirty_digest") != expected_digest or \
                    candidate.get("head") != checks.head(project) or \
                    checks.dirty_digest(project, exclude=exclude) != expected_digest:
                raise Stop("RESTORE_REFUSED", "candidate or successful evidence changed")
        receipt_dir = folder / "route-restorations"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        number = len(list(receipt_dir.glob("*.json"))) + 1
        receipt = {"item": ref, "run": run_id, "previous": previous, "expected_digest": expected_digest,
                   "selector": options["options"]["reviewer"], "upgrade": upgrades[-1],
                   "review_steps": reviews, "check_evidence": evidence_paths}
        write_json(receipt_dir / f"{number}.json", receipt)
        del overrides["reviewer"]
        store.save(state)
        progress.Progress(run_id, store.directory, mode="quiet").emit(
            "info", item=ref, role="reviewer", reason_code="REVIEWER_ROUTE_RESTORED",
            message=f"restored {receipt['selector']}; prior override and evidence in route-restorations/{number}.json")
        return receipt
