"""The review stage: when a piece is reviewed (the policy, or a risk score that adds one), the reviewer route, the
focus of its prompt, and the review-verdict record of every round."""
from __future__ import annotations

from orch.conductor import checks as checks_mod, prompts, risk as risk_mod
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.domain.report import findings_problems
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import write_json
from orch.conductor.policies.routing import CLASS_RANK


def review_enabled(self, item: Item) -> bool:
    if self._per_piece_review_off():  # the batch is reviewed by group (or not at all): review.strategy
        return False
    if item.input_doc.get("review_mode") in ("none", "self"):  # the plan declares no independent review for this piece
        return False
    review = item.policy.get("review") or {}
    return bool(review.get("enabled")) and item.options["limits"]["review_rounds"] > 0


def reviewing(self, item: Item) -> bool:
    """The run policy asks for a review, or the risk score of the piece added one (``state.dynamic_review``)."""
    return self._review_enabled(item) or bool(item.state.get("dynamic_review"))


def dynamic_review(self, item: Item, report: dict) -> None:
    """P7.2: a piece whose policy has no review gets one when its risk score reaches ``review.dynamic_threshold``.
    The score is computed once from the facts after the executor and check rounds and kept in ``state.risk`` and
    ``<item>/risk.json``; a resume reads it again instead of asking the tree."""
    review, limits = item.options["review"], item.options["limits"]
    if item.input_doc.get("review_mode") in ("none", "self"):  # the plan decided: no risk score adds a review to it
        return
    if self._per_piece_review_off() or self._review_enabled(item) or not review["dynamic"] or limits["review_rounds"] <= 0:
        return
    found = item.state.get("risk")
    if found is None:
        facts = self._risk_facts(item, report)
        found = dict(risk_mod.score(facts, self.conductor.get("risk")), facts=facts,
                     threshold=review["dynamic_threshold"])
        found["added"] = found["score"] >= found["threshold"] or bool(found.get("critical"))
        item.state["risk"] = found
        if found["added"]:
            item.state["dynamic_review"] = True
        self._save()
    write_json(item.directory / "risk.json", dict(found, item=item.ref, run=self.run_id))
    if not found["added"] or found.get("announced"):
        return
    if not item.routes.get("reviewer"):
        for role in ("reviewer", self._triage_role(item)):
            item.routes[role] = self._selected(item, role, True)
        self._route_minimum(item)
        self._preflight(item)
        write_json(item.directory / "routes.json", item.routes)
    names = ", ".join(f"{row['name']}+{row['weight']}" for row in found["features"])
    why = (f"risk score {found['score']} reached {found['threshold']}" if found["score"] >= found["threshold"]
           else f"critical feature {', '.join(found['critical'])} (score {found['score']} below {found['threshold']})")
    text = f"{why} ({names}); the policy has no review, so a review and its triage were added"
    self.progress.emit("info", item=item.ref, reason_code="REVIEW_ADDED", message=text)
    self._beacon_event("orch.review.added", item, {
        "score": found["score"], "threshold": found["threshold"],
        "features": [{"name": row["name"], "weight": row["weight"]} for row in found["features"]]})
    self._plan_note(item, text)
    found["announced"] = True  # a stop at the preflight above leaves it open: the resume announces it
    self._save()


def corrected(item: Item, previous: int) -> list:
    """The confirmed findings of review round ``previous`` that the correction after it had to fix."""
    steps = done_steps(item.state.get("steps", {}))
    findings = ((steps.get(f"review.{previous}") or {}).get("result") or {}).get("findings") or {}
    triage = ((steps.get(f"triage.{previous}-a") or steps.get(f"triage.{previous}") or {}).get("result") or {}
              ).get("triage") or {}
    by_id = {found.get("id"): found for found in findings.get("findings", [])}
    return [dict(by_id.get(entry["finding"], {}), id=entry["finding"], fix=entry.get("fix", ""))
            for entry in triage.get("confirmed", [])]


def executor_advice(self, item: Item) -> list:
    """The ``review_recommendation`` of every executor round that gave one, in order."""
    return [advice for key, step in done_steps(item.state.get("steps", {})).items()
            if key.startswith("executor.") and isinstance(step.get("result"), dict)
            for advice in [((step["result"].get("report") or {}).get("review_recommendation"))]
            if isinstance(advice, dict)]


def review_focus(self, item: Item) -> tuple:
    """``(lines, origin)`` of the ``focus`` block of the reviewer prompt (knowledge/p9-prompt#focus): what the executor
    advised to check first (``review_recommendation.focus``) and the features of ``risk.json``. The block asks for no
    narrower review; with neither source there is no block."""
    lines = []
    for advice in self._executor_advice(item):
        lines += [text for text in advice.get("focus") or [] if isinstance(text, str) and text and text not in lines]
    origins = ["stage-report"] if lines else []
    features = (item.state.get("risk") or {}).get("features") or []
    if features:
        lines += [f"risk {row['name']} (+{row['weight']}): {row['evidence']}" for row in features]
        origins.append("risk.json")
    return lines, "+".join(origins)


def upgrade_reviewer(self, item: Item) -> None:
    """P9.4: the class an executor round suggested (``review_recommendation.suggested_model_class``) is taken for the
    reviewer when it is above the class of its route and the higher route is admitted (startable here, not gated, the
    sandbox rule); a suggestion at or below the route changes nothing, the class is never lowered. The upgrade is kept
    in ``route_overrides``, so a resume starts from it, and announced once (``ROUTE_UPGRADED``)."""
    wanted = max((advice["suggested_model_class"] for advice in self._executor_advice(item)
                  if advice.get("suggested_model_class") in CLASS_RANK), key=CLASS_RANK.get, default=None)
    route = item.routes["reviewer"]
    if wanted is None or CLASS_RANK[wanted] <= CLASS_RANK.get(route["model_class"], -1) \
            or item.state.get("reviewer_upgrade_refused") == wanted:
        return
    try:
        higher = self._route(item, "reviewer", {"provider": route["provider"], "model_class": wanted,
                                                "effort": route.get("effort")})
        problem = self._admit(item, "reviewer", higher)
    except Stop as stop:
        problem = f"{stop.code}: {stop.message}"
    if problem is not None:
        item.state["reviewer_upgrade_refused"] = wanted
        self._save()
        self.progress.emit("info", item=item.ref, role="reviewer", route=self.label(route),
                           message=f"reviewer: the suggested class {wanted} is not taken ({problem})")
        return
    item.routes["reviewer"] = higher
    item.state.setdefault("route_overrides", {})["reviewer"] = {
        key: higher[key] for key in ("provider", "model_class", "effort") if higher.get(key)}
    self._save()
    write_json(item.directory / "routes.json", item.routes)
    self.progress.emit("info", item=item.ref, role="reviewer", route=self.label(higher), reason_code="ROUTE_UPGRADED",
                       message=f"reviewer: {self.label(route)} -> {self.label(higher)} "
                               f"({route['model_class']} -> {wanted}; the executor suggested it)")


def review(self, item: Item, number: int, rows: list, pending: bool = False, cancel=None) -> dict:
    self._upgrade_reviewer(item)
    route = item.routes["reviewer"]
    key = f"review.{number}"
    focus, focus_origin = self._review_focus(item)

    def run() -> dict:
        base = checks_mod.head(self.project)  # not the claim-time base: commits made meanwhile are not the candidate
        corrected = self._corrected(item, number - 1) if number > 1 and item.options["review"]["audit_scope"] == "corrected" else []
        prompt = prompts.reviewer(item.input_doc, item=item.ref, step=key, base=base, corrected=corrected,
                                  diff=checks_mod.diff(self.project, base), checks=rows, round_no=number,
                                  pre_final=number > 1 and item.options["review"]["pre_final"],
                                  min_severity=item.options["review"]["correct_min_severity"],
                                  roles_dir=self.roles_dir, stub=self._stub("reviewer", route), skills=self._skills(item, "reviewer"),
                                  checks_pending=pending, outside=self._outside(item), focus=focus,
                                  focus_origin=focus_origin, repo_rules=self._repo_rules(item, "reviewer"),
                                  skill_texts=self._skill_texts(item, "reviewer"))
        findings, meta = self._role(item, key, "reviewer", prompt, "review-findings", extra=findings_problems,
                                    cancel=cancel)
        return {"findings": findings, **meta}

    found = self._step(item, key, run, role="reviewer", route=self.label(route),
                       verdict=lambda result: f"{result['findings']['verdict']} "
                                              f"{len(result['findings']['findings'])} finding(s)")
    self._verdict_file(item)
    return found["findings"]


def verdict_file(self, item: Item) -> None:
    """``review-verdict.json`` in the item's artifacts: the short committed record of every review round; the
    streams stay in the ignored runtime folder."""
    steps = done_steps(item.state.get("steps", {}))
    rounds = []
    number = 1
    while f"review.{number}" in steps:
        review = steps[f"review.{number}"]["result"]
        triage = (steps.get(f"triage.{number}-a") or steps.get(f"triage.{number}") or {}).get("result") or {}
        triaged = triage.get("triage") or {}
        reproduced = {entry["finding"]: entry["reproduction"] for entry in triaged.get("confirmed", [])}
        route = item.routes.get("reviewer", {})
        rounds.append({
            "round": number, "provider": route.get("provider"), "model": review.get("model") or route.get("model"),
            "effort": route.get("effort"), "session": review.get("session"),
            "verdict": review["findings"]["verdict"],
            "findings": [{**finding, **({"triage_reproduction": reproduced[finding["id"]]}
                                        if finding["id"] in reproduced else {})}
                         for finding in review["findings"]["findings"]],
            "triage": {"confirmed": [entry["finding"] for entry in triaged.get("confirmed", [])],
                       "rejected": [{"finding": entry["finding"], "reason": entry["reason"]}
                                    for entry in triaged.get("rejected", [])],
                       "session": triage.get("session")} if triage else None,
            "stream": review.get("stream")})
        number += 1
    doc = {"schema": "orch-conductor-review-verdict/v1", "item": item.ref, "run": self.run_id,
           "selector": item.options.get("reviewer"), "rounds": rounds}
    self._write_artifact(item, "review-verdict.json", doc)
