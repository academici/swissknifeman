"""Re-review an unchanged committed candidate in its original conductor run."""
from __future__ import annotations

from pathlib import Path
from typing import cast

from aicore.util.io import durable_replace
from orch import policies
from orch.conductor import checks, contract, records
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import work_source
from orch.conductor.infrastructure.files import RunStore, read_json, safe
from orch.conductor.policies.routing import exact_reviewer
from orch.conductor.stages import review as review_stage


def recover(conductor, run_id: str, ref: str, commit: str, *, owner_extra_round: bool = False) -> dict:
    store = RunStore(conductor.project, run_id)
    with store.ownership("recover-review", checkout=True):
        loaded_run, loaded_state = store.load()
        run, state = cast(dict, loaded_run), cast(dict, loaded_state)
        piece = (state.get("items") or {}).get(ref)
        if state.get("status") != "finished" or not piece or piece.get("outcome") not in ("done", "done_with_deviations"):
            raise Stop("RECOVERY_REFUSED", "the original item must be closed in a finished run")
        if not piece.get("orch_run") or not run.get("plan"):
            raise Stop("RECOVERY_REFUSED", "the original source run or plan is missing")
        steps = piece.get("steps") or {}
        prior = ((steps.get("review.1") or {}).get("result") or {})
        if not prior.get("repaired_from_text") or prior.get("findings", {}).get("findings"):
            raise Stop("RECOVERY_REFUSED", "the original review must be a repaired-from-text review with no findings")
        number = 3 if owner_extra_round else 2
        later = [key for key in steps if key.startswith("review.") and key != "review.1"]
        completed = (steps.get(f"review.{number}") or {}).get("status") == "done"
        second = steps.get("review.2") or {}
        extra_valid = owner_extra_round and second.get("status") == "stopped" and second.get("code") == "ROLE_OUTPUT_INVALID" and \
            piece.get("review_rounds_used") in (2, 3) and all(key in ("review.2", "review.3") for key in later) and \
            ("review.3" not in later or completed)
        if later and not extra_valid and (later != ["review.2"] or not completed or owner_extra_round):
            raise Stop("RECOVERY_REFUSED", "a second review is unfinished; preserve it and reconcile the original run")
        folder = store.directory / safe(ref)
        options = records.read(folder / "options.json", "item-options")
        input_doc = read_json(folder / "input.json")
        routes = records.read(folder / "routes.json", "item-routes")
        if not options or not input_doc or not routes or not exact_reviewer(options["options"], options["sources"], input_doc):
            raise Stop("RECOVERY_REFUSED", "the original item does not pin a reviewer")
        if owner_extra_round and not extra_valid:
            raise Stop("RECOVERY_REFUSED", "owner extra round requires an invalid stopped second review")
        if options["options"]["limits"]["review_rounds"] < 2 or (not completed and piece.get("review_rounds_used", 0) >= number):
            raise Stop("REVIEW_LIMIT", "the original run has no remaining review round")
        recorded_commit = ((steps.get("commit") or {}).get("result") or {}).get("sha")
        if not recorded_commit or commit != recorded_commit or checks.head(conductor.project) != commit:
            raise Stop("RECOVERY_REFUSED", "the checked-out commit does not match the original scoped commit")
        candidate = prior.get("candidate") or {}
        base = prior.get("base")
        committed = review_stage.revision_candidate(conductor.project, base, commit) if base else {}
        committed_paths = committed.get("paths") or {}
        plan_dir = (input_doc.get("provenance") or {}).get("plan_dir", "")
        plan_parts = Path(plan_dir).parts if isinstance(plan_dir, str) else ()
        local_plan = (len(plan_parts) >= 2 and plan_parts[0] == "plans" and
                      all(part not in (".", "..") for part in plan_parts))
        extra = set(committed_paths) - set(candidate.get("paths") or {})
        if not candidate.get("paths") or any(committed_paths.get(path) != value for path, value in candidate["paths"].items()) or \
                any(not local_plan or not path.startswith(plan_dir.rstrip("/") + "/") for path in extra):
            raise Stop("RECOVERY_REFUSED", "the committed candidate differs from the original review")
        current = checks.candidate(conductor.project, candidate["paths"])
        if current["paths"] != candidate["paths"] or current["digest"] != candidate.get("digest"):
            raise Stop("RECOVERY_REFUSED", "the working candidate differs from the committed review")
        outside = prior.get("outside") or {}
        if any(checks.path_fingerprint(conductor.project, path) != fingerprint for path, fingerprint in outside.items()):
            raise Stop("RECOVERY_REFUSED", "an outside path changed since the original review")
        brief = (steps.get("brief") or {}).get("result") or {}
        if not brief.get("artifacts_dir"):
            raise Stop("RECOVERY_REFUSED", "the original artifact directory is missing")
        conductor._open(run_id, run, state, store)
        item = Item(ref=ref, orch_run=piece["orch_run"], state=piece, directory=folder, claim={})
        conductor._open_artifacts(item, brief)
        receipt_path = work_source.artifact_path(item, "review-receipt.json")
        history = folder / "review-recovery"
        receipt = read_json(history / "review-receipt.json") if completed or owner_extra_round else read_json(receipt_path)
        if not receipt or contract.problems(receipt, "review-receipt") or receipt.get("run") != run_id or \
                receipt.get("item") != ref or receipt.get("round") != 1 or \
                receipt.get("candidate", {}).get("paths") != candidate["paths"] or \
                receipt.get("candidate", {}).get("digest") != candidate.get("digest") or \
                receipt.get("attempt_id") != f"att-{piece['orch_run']}-{ref}":
            raise Stop("RECOVERY_REFUSED", "the original receipt is missing or does not match the candidate")
        subject = receipt.get("subject", "")
        if not subject.endswith("." + ref):
            raise Stop("RECOVERY_REFUSED", "the original receipt subject does not match the item")
        history.mkdir(parents=True, exist_ok=True)
        for name in ("review-receipt.json", "review-verdict.json"):
            source, target = work_source.artifact_path(item, name), history / name
            if source.is_file() and not target.exists():
                durable_replace(target, source.read_bytes())
            elif not completed and not owner_extra_round and source.is_file() and target.read_bytes() != source.read_bytes():
                raise Stop("RECOVERY_REFUSED", "archived original review differs from the current artifact")
        item.claim = {"attempt_id": receipt["attempt_id"], "scenario": options["scenario"], "route": options.get("claim_route") or {}}
        item.options, item.sources = records.options_effective(options["options"]), options["sources"]
        if owner_extra_round:
            item.options["limits"]["review_rounds"] = 3
            item.options["limits"]["retries"] = 0
        item.policy = policies.load(options["scenario"], conductor.settings, warn=lambda _message: None)
        item.launch_plan = ((steps.get("prepare") or {}).get("result") or {})
        item.input_doc = dict(input_doc, provenance={"kind": "review", "base": base, "head": commit,
                                                     "plan": subject[:-(len(ref) + 1)], "item": ref})
        item.recovery_candidate = {"head": commit, "digest": candidate["digest"], "paths": candidate["paths"]}
        route = conductor._selected(item, "reviewer", False)
        expected = conductor._reviewer_selector(item)[0]
        if any(route.get(key) != expected.get(key) for key in ("provider", "model", "effort")):
            raise Stop("EXACT_ROUTE_MISMATCH", "recovery reviewer differs from the original pinned selector")
        if any((receipt.get("reviewer") or {}).get(key) != route.get(key) for key in ("provider", "model", "effort")):
            raise Stop("EXACT_ROUTE_MISMATCH", "the original receipt names a different reviewer")
        problem = conductor._admit(item, "reviewer", route)
        if problem:
            raise Stop("RECOVERY_REFUSED", problem)
        item.routes = {"reviewer": route}
        rows = ((steps.get("checks.2") or steps.get("checks.1") or {}).get("result") or [])
        if completed:
            findings = steps[f"review.{number}"]["result"]["findings"]
        else:
            piece["review_rounds_used"] = number
            conductor._save()
            conductor.progress.emit("info", item=ref, role="reviewer", reason_code="REVIEW_RECOVERY_STARTED",
                                    message=f"original run, review round {number}; prior receipt archived" +
                                            ("; one extra round authorized by owner" if owner_extra_round else ""))
            findings = conductor._review(item, number, rows)
        if findings.get("verdict") != "GREEN" or findings.get("findings") or findings.get("questions"):
            raise Stop("RECOVERY_REVIEW_RED", "the second review was not green; preserve its result and stop")
        result = done_steps(piece["steps"])[f"review.{number}"]["result"]
        if result.get("repaired_from_text") or not result.get("session") or \
                (result.get("model") and result["model"] != route["model"]) or \
                result.get("candidate", {}).get("paths") != candidate["paths"]:
            raise Stop("RECOVERY_REFUSED", "the second review is not a valid receipt for the original candidate")
        result["outside"] = outside
        round_two = {"round": number, "provider": route["provider"], "model": route["model"], "effort": route["effort"],
                     "session": result.get("session"), "verdict": "GREEN", "findings": [], "triage": None}
        review_stage.receipt_file(conductor, item, [round_two], done_steps(piece["steps"]))
        conductor._save()
        return {"run": run_id, "item": ref, "round": number, "attempt_id": receipt["attempt_id"],
                "commit": commit, "receipt": str(receipt_path), "prior_receipt": str(history / "review-receipt.json")}
