"""The review stage: when a piece is reviewed (the policy, or a risk score that adds one), the reviewer route, the
focus of its prompt, and the review-verdict record of every round."""
from __future__ import annotations

import hashlib
import json

from orch.conductor.domain import fix_brief

from orch.conductor import checks as checks_mod, contract, prompts, records, risk as risk_mod, scope as scopes
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.domain.report import finding_key, findings_problems
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import write_json
from orch.conductor.infrastructure import work_source
from orch.conductor.policies import review_strategy
from orch.conductor.policies.routing import CLASS_RANK, PLAN_REVIEW_SOURCE, exact_reviewer
from orch.conductor.prompts.blocks import Block, CONDUCTOR


def review_enabled(self, item: Item) -> bool:
    if item.input_doc.get("provenance", {}).get("kind") == "review":
        return True
    if review_strategy.per_piece_off(self.state.get("review_strategy")):  # the batch is reviewed by group (or not at all): review.strategy
        return False
    if item.input_doc.get("review_mode") in ("none", "self"):  # the plan declares no independent review for this piece
        return False
    review = item.policy.get("review") or {}
    return bool(review.get("enabled")) and item.options["limits"]["review_rounds"] > 0


def requested_off(self, item: Item) -> None:
    """The plan asks for a review of the piece (``review_mode: requested``) and the run reviews nothing (its policy has no
    review, or the review strategy of the batch is ``none``): whether a run reviews is the run's decision, so no review
    is added, but the gap is said once per piece
    (``REVIEW_REQUESTED_POLICY_OFF``) instead of passing in silence."""
    strategy = (self.state.get("review_strategy") or {}).get("mode")
    if item.input_doc.get("review_mode") != "requested" or strategy in ("groups", "single") or self._reviewing(item) \
            or item.state.get("review_requested_announced"):
        return  # reviewed on its own or with its group
    review = item.policy.get("review") or {}
    why = ("the review strategy of the batch is none" if strategy == "none"
           else f"the run policy {item.policy.get('policy_id', '-')} "
                + ("has no review" if not review.get("enabled") else "allows 0 review rounds"))
    self.progress.emit("info", item=item.ref, reason_code="REVIEW_REQUESTED_POLICY_OFF",
                       message=f"{item.ref}: the plan requests a review, but {why}; the piece is not reviewed "
                               "(choose a scenario or a review strategy with review to have it)")
    item.state["review_requested_announced"] = True
    self._save()


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
    if review_strategy.per_piece_off(self.state.get("review_strategy")) or self._review_enabled(item) or not review["dynamic"] or limits["review_rounds"] <= 0:
        return
    found = item.state.get("risk")
    if found is None:
        changed = self._changed(item)
        facts = self._risk_facts(item, report, changed=changed, outside=self._outside(item),
                                 diff_lines=scopes.diff_lines(self.project, changed))
        found = dict(risk_mod.score(facts, self.conductor.get("risk")), facts=facts,
                     threshold=review["dynamic_threshold"])
        found["added"] = found["score"] >= found["threshold"] or bool(found.get("critical"))
        item.state["risk"] = found
        if found["added"]:
            item.state["dynamic_review"] = True
        self._save()
    records.write(item.directory / "risk.json", dict(found, item=item.ref, run=self.run_id), "risk")
    if not found["added"] or found.get("announced"):
        return
    if not item.routes.get("reviewer"):
        for role in ("reviewer", self._triage_role(item)):
            item.routes[role] = self._selected(item, role, True)
        self._route_minimum(item)
        self._preflight(item)
        records.write(item.directory / "routes.json", item.routes, "item-routes")
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


def unresolved(item: Item, number: int) -> list:
    """The confirmed findings review round ``number`` has to see fixed: those of the round before it and, still, those of
    the rounds earlier than that. A later report that does not name an earlier finding is no proof that it was fixed
    (a review that looks at fewer lines can miss it), so the finding stays an obligation of every later round, at any
    severity triage confirmed; one found again keeps its latest form."""
    found: dict = {}
    for previous in range(1, number):
        for entry in corrected(item, previous):
            name = (entry.get("location"), entry.get("failure_scenario"))
            found.pop(name, None)
            found[name] = dict(entry, id=entry["id"] if previous == number - 1 else f"{entry['id']} (review {previous})")
    return list(found.values())


def finding_paths(findings: list) -> list:
    """The files the ``location`` (``path:line``) of the findings name."""
    paths = []
    for entry in findings:
        name = str(entry.get("location") or "").split(":", 1)[0].strip()
        if name and not name.startswith("/") and ".." not in name.split("/") and name not in paths:
            paths.append(name)
    return paths


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
    sandbox rule); a suggestion at or below the route, or a higher class that resolves to the same provider/model/effort,
    changes nothing (no beacon, no routes.json rewrite), the class is never lowered. The upgrade is kept
    in ``route_overrides``, so a resume starts from it, and announced once (``ROUTE_UPGRADED``)."""
    if exact_reviewer(item.options, item.sources, item.input_doc):
        return
    wanted = max((advice["suggested_model_class"] for advice in self._executor_advice(item)
                  if advice.get("suggested_model_class") in CLASS_RANK), key=lambda name: CLASS_RANK[name], default=None)
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
    if route.get("model") and self.label(higher) == self.label(route):  # the same resolved model: nothing to upgrade
        item.state["reviewer_upgrade_refused"] = wanted
        self._save()
        return
    item.routes["reviewer"] = higher
    item.state.setdefault("route_overrides", {})["reviewer"] = {
        key: higher[key] for key in ("provider", "model_class", "effort") if higher.get(key)}
    self._save()
    records.write(item.directory / "routes.json", item.routes, "item-routes")
    self.progress.emit("info", item=item.ref, role="reviewer", route=self.label(higher), reason_code="ROUTE_UPGRADED",
                       message=f"reviewer: {self.label(route)} -> {self.label(higher)} "
                               f"({route['model_class']} -> {wanted}; the executor suggested it)")


def review_base(self, item: Item) -> str:
    """The revision a review of the piece compares the tree with: HEAD, or in a split run (``state.commits``, the checkpoint
    commit before the review) the parent of the first commit of the piece. HEAD would make the diff of the review empty
    once the implementation is committed."""
    commits = item.state.get("commits") or []
    return commits[0]["parent"] if commits else checks_mod.head(self.project)


def fix_commit_paths(self, item: Item) -> set:
    """The paths the fix commits of a split run changed: a correction that is committed before the next review leaves no
    dirty path for the audit of the corrected scope to see."""
    found = set()
    for row in item.state.get("commits") or []:
        if row["stage"] != "implementation":
            found.update(filter(None, checks_mod.git(self.project, "diff", "--name-only", "-z", row["parent"],
                                                     row["sha"]).split("\0")))
    return found


def review(self, item: Item, number: int, rows: list, pending: bool = False, cancel=None) -> dict:
    self._upgrade_reviewer(item)
    route = item.routes["reviewer"]
    key = f"review.{number}"
    focus, focus_origin = self._review_focus(item)

    def run() -> dict:
        provenance = item.input_doc.get("provenance", {})
        review_only = provenance.get("kind") == "review"
        base = (checks_mod.git(self.project, "rev-parse", "--verify", provenance["base"] + "^{commit}").strip()
                if review_only else self._review_base(item))
        paths = self._changed(item)
        if review_only:
            paths = scopes.own(list(filter(None, checks_mod.git(self.project, "diff", "--name-only", "-z", base).split("\0")))
                               + checks_mod.untracked(self.project), self._not_the_role(item))
        candidate = checks_mod.candidate(self.project, paths)
        outside = checks_mod.review_outside(self.project, base, candidate["paths"], self._not_the_role(item))
        target = provenance.get("head") if review_only else None
        if target and target != "WORKTREE":
            candidate = item.recovery_candidate or revision_candidate(self.project, base, target)
            outside = {}  # the subject is an immutable revision, independent of the checked-out worktree
        dirty = checks_mod.dirty_files(self.project)  # without what the conductor writes (reports, artifacts, plan folder)
        tree = {path: dirty[path] for path in scopes.own(dirty, self._not_the_role(item))}
        with self.store.mutating():  # the tree this review starts from: the next review reads what changed after it
            item.state.setdefault("review_marks", {})[str(number)] = tree
            self._save()
        audit = number > 1 and item.options["review"]["audit_scope"] == "corrected"
        corrected = self._unresolved(item, number) if audit else []
        before = (item.state.get("review_marks") or {}).get(str(number - 1))
        if target and target != "WORKTREE":
            diff = (f"# Review revision {candidate['head']}; read its files with git show REV:path.\n"
                    + checks_mod.git(self.project, "diff", base, candidate["head"],
                                     *(["--", *[f":(literal){path}" for path in candidate["paths"]]]
                                       if item.recovery_candidate else [])))
            scope = "full"
        elif audit and isinstance(before, dict):  # round 1 and audit_scope full see the whole diff, and so does a run without marks
            paths = sorted(set(checks_mod.changed_files(before, tree)) | set(self._finding_paths(corrected))
                           | fix_commit_paths(self, item))  # what the fix commits took is clean in the tree
            diff, scope = checks_mod.diff(self.project, base, paths=paths), "changed"
        else:
            diff, scope = checks_mod.diff(self.project, base, paths=list(candidate["paths"])), "full"
        prompt = prompts.reviewer(item.input_doc, item=item.ref, step=key, base=base, corrected=corrected,
                                  diff=diff, diff_scope=scope, checks=rows, round_no=number,
                                  pre_final=number > 1 and item.options["review"]["pre_final"],
                                  min_severity=item.options["review"]["correct_min_severity"],
                                  roles_dir=self.roles_dir, stub=self._stub("reviewer", route), skills=self._skills(item, "reviewer"),
                                  checks_pending=pending, outside=self._outside(item), focus=focus,
                                  focus_origin=focus_origin, repo_rules=self._repo_rules(item, "reviewer"),
                                  skill_texts=self._skill_texts(item, "reviewer"))
        if item.recovery_candidate and number > 2:
            prompt.append(Block("result_contract", CONDUCTOR,
                                "MANDATORY FINAL OUTPUT: End with exactly one fenced `review-findings` JSON block "
                                "as specified above, even for GREEN with no findings. A prose-only verdict is invalid."))
        findings, meta = self._role(item, key, "reviewer", prompt, "review-findings", extra=findings_problems,
                                    cancel=cancel)
        return {"findings": findings, "finding_keys": {f["id"]: finding_key(f) for f in findings["findings"]},
                "base": base, "candidate": candidate, "outside": outside, **meta}

    found = self._step(item, key, run, role="reviewer", route=self.label(route),
                       verdict=lambda result: f"{result['findings']['verdict']} "
                                              f"{len(result['findings']['findings'])} finding(s)")
    self._verdict_file(item)
    return found["findings"]


def review_changed(self, item: Item, number: int) -> bool:
    """A cached overlap review without a combined correction must still describe the current product."""
    if number in item.state.get("combined_done", []):
        return False  # the loop audits the combined correction or records corrected_after at its review wall
    step = done_steps(item.state.get("steps", {})).get(f"review.{number}")
    reviewed = (step or {}).get("result") or {}
    if "candidate" not in reviewed:
        return False  # legacy steps have no content binding to compare
    provenance = item.input_doc.get("provenance", {})
    if provenance.get("kind") == "review" and provenance.get("head") != "WORKTREE":
        return revision_candidate(self.project, reviewed["base"], provenance["head"]) != reviewed["candidate"]
    paths = set(reviewed["candidate"]["paths"]) | set(self._changed(item))
    current = checks_mod.candidate(self.project, paths)["paths"]
    outside = checks_mod.review_outside(self.project, reviewed["base"], paths, self._not_the_role(item))
    return (current != reviewed["candidate"]["paths"] or outside != reviewed.get("outside", {})
            or "other" in current.values() or "other" in outside.values())


def revision_candidate(project, base: str, target: str) -> dict:
    """Bind a named review revision to its Git blobs, including deleted paths and executable modes."""
    head = checks_mod.git(project, "rev-parse", "--verify", target + "^{commit}").strip()
    names = checks_mod.git(project, "diff", "--name-only", "-z", base, head).split("\0")
    found = {}
    for path in sorted(filter(None, names)):
        entry = checks_mod.git(project, "ls-tree", head, "--", f":(literal){path}").split("\t", 1)[0].split()
        found[path] = f"{entry[0]} {entry[2]}" if entry else "absent"
    payload = "\n".join(f"{path}\t{value}" for path, value in found.items())
    return {"head": head, "digest": "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest(), "paths": found}


def verdict_file(self, item: Item, corrected_after=None) -> None:
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
            **({"base": review["base"], "candidate_digest": review["candidate"]["digest"]}
               if "candidate" in review else {}),
            "findings": [{**finding, "key": (review.get("finding_keys") or {}).get(finding["id"], finding_key(finding)),
                          **({"triage_reproduction": reproduced[finding["id"]]}
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
    if item.input_doc.get("review_route") and not item.sources.get("reviewer"):
        doc["reviewer_source"] = PLAN_REVIEW_SOURCE  # the rounds ran on the plan's review route, not on the selector
    # records/v1 review-verdict, checked before the artifact writer (same bytes as records.write) replaces the file
    self._write_artifact(item, "review-verdict.json",
                         records.check(doc, "review-verdict", f"review-verdict.json of {item.ref}",
                                       hint=records.WRITER_HINT))
    if rounds and "candidate" in steps[f"review.{rounds[-1]['round']}"]["result"]:
        receipt_file(self, item, rounds, steps, corrected_after)


def receipt_file(self, item: Item, rounds: list, steps: dict, corrected_after=None) -> None:
    """Write the last completed review's binding, retaining earlier findings by conductor key."""
    last = rounds[-1]
    review = steps[f"review.{last['round']}"]["result"]
    findings = {}
    severity = {"Blocker": 0, "Major": 1, "Minor": 2, "Nit": 3}
    floor = severity[item.options["review"]["correct_min_severity"]]
    deferred = {(entry["key"], entry["id"]) for entry in item.state.get("deferred_findings", [])}
    for row in rounds:
        triage = row.get("triage") or {}
        confirmed = set(triage.get("confirmed", []))
        rejected = {entry["finding"] for entry in triage.get("rejected", [])}
        for found in row["findings"]:
            status = "rejected" if found["id"] in rejected else "open"
            if found["id"] in confirmed:
                status = "deferred" if severity[found["severity"]] > floor else "confirmed"
                if status == "confirmed" and (row["round"] < last["round"] or
                                               corrected_after and row["round"] == corrected_after["round"]):
                    status = "corrected"
            if (found["key"], found["id"]) in deferred:
                status = "deferred"
            # Distinct findings can have the same normalized key. Keep each id; a later lower severity must not
            # erase a Blocker merely because its scenario differs only in numeric examples.
            findings[(found["key"], found["id"])] = {k: v for k, v in dict(found, status=status).items()
                                                     if k != "triage_reproduction"}
    values = list(findings.values())
    route = {k: last[k] for k in ("provider", "model", "effort", "session") if last.get(k)}
    route["selector_source"] = item.sources.get("reviewer") or (PLAN_REVIEW_SOURCE if item.input_doc.get("review_route") else "defaults")
    policy = item.options["review"]
    provenance = item.input_doc.get("provenance", {})
    subject = (f"{provenance['plan']}.{provenance['item']}" if provenance.get("kind") == "review"
               and provenance.get("plan") and provenance.get("item") else
               checks_mod.subject_of(item.input_doc) if provenance.get("kind") == "plan" else item.input_doc["input_id"])
    doc = {"$schema": "urn:swissknifeman:orch:conductor:review-receipt:v1",
           "subject": subject, "item": item.ref, "run": self.run_id,
           "round": last["round"], "base": review["base"], "candidate": review["candidate"],
           "outside": review.get("outside", {}), "reviewer": route,
           "policy": {"review_mode": item.input_doc.get("review_mode", "requested"),
                      "strategy": (self.state.get("review_strategy") or {}).get("mode", "each"),
                      "rounds_max": item.options["limits"]["review_rounds"],
                      **{k: policy[k] for k in ("correct_min_severity", "pre_final")},
                      "source": item.sources.get("review") or "run:review"},
           "verdict": last["verdict"], "findings": values,
           "open": {name.lower(): sum(f["severity"] == name and f["status"] in ("confirmed", "deferred", "open") for f in values)
                    for name in ("Blocker", "Major")},
           "questions": review["findings"].get("questions", []),
           "residual_risk": review["findings"].get("residual_risk", ""),
           "corrected_after": corrected_after, "at": checks_mod._utc(),
           "producer": {"kind": "orch-conductor", "version": "0.1.0"}}
    if item.claim.get("attempt_id"):
        doc["attempt_id"] = item.claim["attempt_id"]
    write_receipt(self, item, doc)


def write_receipt(self, item: Item, doc: dict) -> None:
    problems = contract.problems(doc, "review-receipt")
    if problems:
        raise ValueError("invalid review-receipt: " + "; ".join(problems))
    self._write_artifact(item, "review-receipt.json", doc)


def corrected_receipt(self, item: Item, number: int) -> None:
    """Bind an unreviewed correction to the paths it actually changed, keeping the reviewed candidate intact."""
    review = done_steps(item.state.get("steps", {}))[f"review.{number}"]["result"]
    if "candidate" not in review:  # old persisted steps cannot acquire a retrospective review binding
        return
    before = {**review.get("outside", {}), **review["candidate"]["paths"]}
    after = checks_mod.review_outside(self.project, review["base"], [], self._not_the_role(item))
    paths = sorted(path for path in set(before) | set(after)
                   if before.get(path, "absent") != checks_mod.path_fingerprint(self.project, path))
    if paths:
        self._verdict_file(item, corrected_after={"round": number, "paths": paths})

def review_correction(self, item: Item, executor: int, number: int, findings: dict, triage: dict, sources: dict) -> str:
    """Persist and validate the exact handoff before rendering; replay uses the same artifact."""
    path = item.directory / "fix-briefs" / f"executor.{executor}.json"
    if path.exists():
        doc = json.loads(path.read_text(encoding="utf-8"))
    else:
        step = done_steps(item.state.get("steps", {})).get(f"review.{number}", {}).get("result", {})
        doc = fix_brief.build(findings, triage,
            {row["id"]: finding_key(row) for row in findings["findings"]}, item.options["review"]["fix_brief"], {
                "review": {"run": self.run_id, "item": item.ref, "round": number,
                           "receipt": self._relative(work_source.artifact_path(item, "review-receipt.json"))},
                "base": step.get("base", ""), "findings": self._relative(work_source.artifact_path(item, "review-verdict.json")),
                "scope_constraints": ["Change only paths inside scope.write_set",
                                      "Do not change public interfaces unless the finding says so"],
                "required_checks": [row["id"] for row in item.input_doc["acceptance"]["checks"]]})
    problems = contract.problems(doc, "fix-brief")
    if problems:
        raise ValueError("invalid fix-brief: " + "; ".join(problems))
    if not path.exists():
        delivered = {row["id"] for row in doc["findings"]}
        active = {entry["finding"] for entry in triage["confirmed"]}
        item.state["deferred_findings"] = [source for name, source in sources.items()
                                           if name in active and name not in delivered]
        self._save()
        write_json(path, doc)  # state first: a persisted handoff never loses the queue on a crash before save
        self._verdict_file(item)
    if (len(doc["findings"]) > doc["limits"]["max_findings"]
            or len(fix_brief.render(doc)) > doc["limits"]["max_chars"]):
        self.progress.emit("info", item=item.ref, reason_code="FIX_BRIEF_OVER",
                           message=f"Blockers retained: {len(doc['findings'])} findings, {len(fix_brief.render(doc))} characters; "
                                   f"limits {doc['limits']['max_findings']}/{doc['limits']['max_chars']}")
    return prompts.review_correction(doc)



def review_shape_evidence(self, item: Item) -> list:
    """Record the default shape procedure from already validated review and triage documents."""
    # Prove the review input's default findings-shape procedure from the validated documents. No command check runs.
    from orch.adhoc import REVIEW_PROCEDURE
    from orch.contracts import validate
    rows = []
    for check in item.input_doc["acceptance"]["checks"]:
        if check.get("procedure") != REVIEW_PROCEDURE or check.get("cmd"):
            continue
        path = work_source.evidence_dir(item) / f"{check['id']}.json"
        doc = {"$schema": "urn:swissknifeman:orch:exec:check-evidence:v1", "contract_version": "exec/v1",
               "evidence_id": f"{self.run_id}:{item.ref}:{check['id']}", "check_id": check["id"],
               "subject": item.input_doc["input_id"], "procedure": {"procedure": REVIEW_PROCEDURE},
               "candidate": {"head": checks_mod.head(self.project)}, "verdict": "pass",
               "observation": "The conductor validated review-findings, triage-result and the bound review receipt.",
               "started_at": checks_mod._utc(), "finished_at": checks_mod._utc(), "producer": {"kind": "engine"}}
        errors = [issue for issue in validate(doc, "check-evidence") if issue.level == "error"]
        if errors:
            raise ValueError("invalid review shape evidence: " + str(errors[0]))
        write_json(path, doc)
        rows.append({"id": check["id"], "kind": "acceptance", "green": True,
                     "verdict": "pass", "evidence": self._relative(path)})
    return rows
