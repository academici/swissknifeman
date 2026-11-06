"""The review plan of a batch: chosen once before the first piece runs, carried out after the last piece of each group.

``decide`` chooses how the batch is reviewed by the rules (``review.strategist: rules``, the default) or asks the strategist (a
small model call, ``review.strategist: model``) (``policies/review_strategy.py``) and keeps the answer in ``state.review_strategy`` and ``review-strategy.json`` of the
run. ``group_review_due`` runs after every piece: when the piece is the last of its group and the group is done it reads the
commits of the group once (``review_batch``) and keeps the reply in ``group-review-<n>.md`` of the run folder; Blocker and Major
findings are announced (``GROUP_REVIEW``) with a follow-up input to correct them in a commit of their own. A Blocker stops the run
(``GROUP_REVIEW_BLOCKER``) until ``settle --group`` accepts that follow-up; a failed review of requested pieces stops it
(``GROUP_REVIEW_FAILED``) and is repeated once on resume."""
from __future__ import annotations

import json
import shlex
import time
from typing import Optional

from orch import adhoc, launch
from orch.contracts import canonical_digest
from orch.conductor import options as opts, records, review_batch
from orch.conductor.application import budget_service as token_budget
from orch.conductor.domain.item import Item
from orch.conductor.domain import fix_brief
from orch.conductor.domain.report import finding_key
from orch.conductor import contract
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import results, sessions
from orch.conductor.infrastructure.clock import utc_now
from orch.conductor.infrastructure.files import read_json, safe, write_json
from orch.conductor.policies import review_strategy as strategy
from orch.conductor.policies.routing import CLASS_RANK

PER_PIECE_OFF = strategy.PER_PIECE_OFF  # the strategy modes in which a piece is not reviewed on its own
GROUP_ATTEMPTS = 2  # a group review that failed is repeated once (on resume) before the group stays unreviewed
STRATEGY_FILE = "review-strategy.json"  # records/v1 review-strategy


def piece_item(self, answer: dict) -> Item:
    state = self.state["items"].setdefault(answer["ref"], {"steps": {}, "retries_used": 0, "orch_run": answer["run_id"]})
    return Item(ref=answer["ref"], orch_run=answer["run_id"], state=state, directory=self.directory / safe(answer["ref"]),
                claim=answer)


def forced(mode: str, pieces: list, proposal: dict) -> dict:
    """``review.strategy`` named a mode: the groups it implies (the rules' groups for ``groups`` when they are some). A piece
    whose plan says ``review.mode none`` is in no group: the plan gave it no review, a strategy does not add one."""
    refs = [piece["ref"] for piece in pieces if piece.get("review_mode") != "none"]
    if mode == "none":
        groups = []
    elif mode == "single":
        groups = [refs] if len(refs) <= 12 else [refs[i:i + 12] for i in range(0, len(refs), 12)]
    elif mode == "each":
        groups = [[ref] for ref in refs]
    else:
        groups = [[ref for ref in group if ref in refs] for group in proposal["groups"]] if proposal["mode"] == "groups" else \
            [refs[i:i + strategy.MAX_GROUP] for i in range(0, len(refs), strategy.MAX_GROUP)]
        groups = [group for group in groups if group]
    return {"mode": mode, "groups": groups, "reviewer": proposal["reviewer"], "reason": f"review.strategy: {mode}",
            "source": "option"}


def run_agent(self, item: Item, key: str, role: str, route: dict, prompt: str, raw, timeout_s: int):
    """Batch roles get the same process ownership record as per-piece roles.

    ``key`` is their logical stage (``group-review-<n>``, ``review-strategist``): admission and usage stay on that
    stage, and the caller's stage is restored when the call returns.
    """
    previous = token_budget.bind_stage(self, item, key)
    try:
        return _run_agent(self, item, key, role, route, prompt, raw, timeout_s)
    finally:
        token_budget.restore_stage(self, previous)


def _run_agent(self, item: Item, key: str, role: str, route: dict, prompt: str, raw, timeout_s: int):
    if item.options:
        self._admit_budget(item, "attempt")
    prompt_file = item.directory / "prompts" / f"{key}.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")
    handle = self._agent_start(item, key, role, route, prompt_file, 1)
    try:
        run = self._launch(item, handle, role, route, prompt, attempt=1, raw=raw, timeout_s=timeout_s,
                           provider=route["provider"])
        self._tokens(item, run.usage, usage_complete=run.usage_complete, attempt=self._relative(raw),
                     accounting=run.usage_accounting)
        results.observe_isolation(self, item, key, role, route, run.init, handle)  # ISOLATION_DRIFT, result.json
        handle.update(last_exit=run.exit, stream=self._relative(raw), lingered=run.lingered)
    except BaseException as error:
        self._agent_end(handle, {"code": type(error).__name__, "message": str(error)[:300] or type(error).__name__})
        raise
    self._agent_end(handle, {"code": run.error, "message": run.detail or run.error} if run.error else None)
    return run


def ask_strategist(self, item: Item, pieces: list, proposal: dict) -> Optional[dict]:
    """The model's choice, or ``None`` when it cannot be had or is not sound (the rules' choice stands then)."""
    try:
        route = self._route(item, "triager")
        raw = self.directory / "streams" / "review-strategist.txt"
        raw.parent.mkdir(parents=True, exist_ok=True)
        run = run_agent(self, item, "review-strategist", "triager", route, strategy.prompt(pieces, proposal), raw, 300)
    except Exception as error:  # noqa: BLE001 — the strategist is advice; the rules decide when it fails
        if isinstance(error, Stop) and error.code == "TOKEN_BUDGET":
            raise
        self.progress.emit("info", reason_code="STRATEGIST_FAILED", message=f"{type(error).__name__}: {error}"[:200])
        return None
    if run.error:
        self.progress.emit("info", reason_code="STRATEGIST_FAILED", message=f"{run.error}: {run.detail}"[:200])
        return None
    chosen = strategy.check(strategy.parse(run.text), [piece["ref"] for piece in pieces])
    if chosen is None:
        self.progress.emit("info", reason_code="STRATEGIST_UNSOUND", message="the strategist's answer is not a partition "
                           "of the batch in order; the rules decide")
    return chosen


def decide(self, answers: list) -> None:
    """Choose the review plan of this batch once (a resume reads the kept plan: ``state.review_strategy``, else the
    ``review-strategy.json`` a run that died before its next save had already written)."""
    if self.state.get("review_strategy") is not None:
        return
    kept = records.read(self.directory / STRATEGY_FILE, "review-strategy")
    if kept is not None:
        self.state["review_strategy"] = {key: value for key, value in kept.items() if key != "$schema"}
        self._save()
        return
    if len(answers) < 2:
        self.state["review_strategy"] = {"mode": "each", "groups": [[a["ref"] for a in answers]], "source": "single piece",
                                         "reviewer": {"effort": "medium"}, "reason": "one piece"}
        self._save()
        return
    first = piece_item(self, answers[0])
    self._resolve(first, persist=False)
    review = first.options["review"]
    pieces = [strategy.facts(a["ref"], a.get("title") or a["ref"], self._brief_doc(a)) for a in answers]
    proposal = strategy.rules(pieces)
    mode = review.get("strategy", "auto")
    skipped = [piece["ref"] for piece in pieces if piece.get("review_mode") == "none"] if mode != "auto" else []
    if mode != "auto":
        plan = forced(mode, pieces, proposal)
    elif review.get("strategist", "rules") == "rules" or strategy.unreviewed(pieces):
        plan = proposal  # the plan gave no piece a review: nothing for a strategist to weigh
    else:
        plan = ask_strategist(self, first, pieces, proposal) or proposal
    plan = dict(plan, decided_at=utc_now())
    self.state["review_strategy"] = plan
    records.write(self.directory / STRATEGY_FILE, plan, "review-strategy")
    self._save()
    groups = "; ".join(" + ".join(group) for group in plan["groups"]) or "none"
    effort = group_effort(self, first.options["reviewer"], plan["reviewer"]["effort"])
    self.progress.emit("info", reason_code="REVIEW_STRATEGY",
                       message=f"{plan['mode']} ({plan['source']}): {groups} at effort {effort}; {plan['reason']}")
    if skipped:
        self.progress.emit("info", reason_code="REVIEW_MODE_NONE_SKIPPED",
                           message=f"review.strategy {mode} leaves out {', '.join(skipped)}: the plan gives them review.mode none, "
                                   "so no group reads them")


def per_piece_off(self) -> bool:
    return strategy.per_piece_off(self.state.get("review_strategy"))


def group_review_due(self, ref: str) -> None:
    """After a piece: the review of its group when it was the group's last piece and every piece of the group is done."""
    plan = self.state.get("review_strategy") or {}
    if plan.get("mode") not in ("groups", "single"):
        return
    for number, group in enumerate(plan["groups"], 1):
        if ref != group[-1]:
            continue
        done = [self.state["items"].get(r, {}).get("outcome") in ("done", "done_with_deviations") for r in group]
        if not all(done):
            return
        kept = (self.state.get("group_reviews") or {}).get(str(number))
        unread = kept is not None and failed(kept) and requested(self, group)
        if kept is None or (unread and kept.get("attempts", 1) < GROUP_ATTEMPTS):
            group_review(self, number, group, plan["reviewer"]["effort"])  # a failed review of requested pieces is repeated
        elif unread:
            raise failed_group(number, group, kept)  # past the cap no review is asked again, and a resume is no waiver
        elif kept.get("blocking") and not kept.get("resolved"):
            raise blocked_group(self, number, group, kept)  # a resume does not lift a Blocker: only a settled follow-up does
        return



def review_left(self) -> None:
    """At the end of a run that went through all its pieces: a group whose pieces all ended, some done and some blocked
    (``on_blocked: report``), is reviewed over its done pieces; else nobody would read them."""
    plan = self.state.get("review_strategy") or {}
    items = self.state.get("items") or {}
    for number, done, open_ in strategy.unreviewed_groups(self.state):
        if all((items.get(ref) or {}).get("outcome") == "blocked" for ref in open_):
            group_review(self, number, done, plan["reviewer"]["effort"])


def note_unreviewed(self) -> None:
    """``GROUP_REVIEW_PENDING`` for each group with done pieces and no review when the run ends: a stopped run reviews it
    on the resume that ends the group; a piece closed outside the run leaves the done ones to a review of their own."""
    for number, done, open_ in strategy.unreviewed_groups(self.state):
        self.progress.emit("info", reason_code="GROUP_REVIEW_PENDING",
                           message=f"group {number}: {', '.join(done)} done and not reviewed"
                                   + (f"; the review waits for {', '.join(open_)} (resume --run {self.run_id} --retry "
                                      f"{open_[0]}); a piece closed outside the run leaves them to a review of their own"
                                      if open_ else ""))

def failed_group(number: int, group: list, kept: dict) -> Stop:
    """``GROUP_REVIEW_FAILED``: the group review failed and a piece of the group has ``review_mode: requested``, which no
    other review covers. The first failure is repeated once on resume; after that the stop stays until a review reads."""
    attempts = kept.get("attempts", 1)
    again = "resume repeats it once" if attempts < GROUP_ATTEMPTS else \
        f"{attempts} attempts failed: no review is asked again and a resume does not waive it"
    why = kept.get("error") or "the reply is not in the asked format"
    return Stop("GROUP_REVIEW_FAILED", f"group {number} ({', '.join(group)}): the review failed ({why}) and the group has "
                                       f"pieces with a requested review that nobody read; {again}")


def failed(kept: dict) -> bool:
    """The kept group review is a failure (the role failed or its reply is not in the asked format), not a review. An empty
    production diff is no failure of the review: there is nothing to repeat."""
    return kept.get("format") == "malformed" or bool(kept.get("error") and kept.get("format") != "empty")


def requested(self, group: list) -> bool:
    """Whether the plan asked for a review of at least one piece of the group (``review_mode: requested``): the group review
    is then the only review those pieces get (``PER_PIECE_OFF``)."""
    return any((read_json(self.directory / safe(ref) / "input.json") or {}).get("review_mode") == "requested"
               for ref in group)


def followup_target(self, number: int) -> str:
    return self._relative(self.directory / f"group-review-{number}.followup.json")


def blocked_group(self, number: int, group: list, kept: dict) -> Stop:
    """``GROUP_REVIEW_BLOCKER``: the group review found Blocker findings. The way out is a follow-up run that corrects
    them in a commit of its own, then ``settle --group`` (the run itself never lifts the stop)."""
    target = kept.get("followup") or followup_target(self, number)
    return Stop("GROUP_REVIEW_BLOCKER",
                f"group {number} ({', '.join(group)}): {kept['counts']['Blocker']} Blocker finding(s) in {kept['file']}; correct them "
                f"with `orch conduct run --input {target} --commit` (a follow-up input written by hand at that path when none "
                f"was built), then `orch conduct settle --run {self.run_id} --group {number} --followup-run <FOLLOWUP_RUN> "
                "--reason <why>`, then resume")


def reviewer_effort(selector: dict, planned: str) -> str:
    """The effort of the group review: the one the ``reviewer`` option names, else the strategy's."""
    return selector.get("effort") or planned


def group_effort(self, reviewer: str, planned: str) -> str:
    """The effort a group review runs at, as ``REVIEW_STRATEGY`` announces it: the strategy's under a fixed reviewer
    command line (``conductor.argv``), else the one the ``reviewer`` option names, else the strategy's."""
    if (self.conductor.get("argv") or {}).get("reviewer"):
        return planned
    return reviewer_effort(opts.parse_selector(reviewer), planned)


def group_route(self, number: int, group: list, item: Item) -> None:
    """The reviewer route of a group review, set on ``item`` (the last piece): the reviewer of the run when a global layer sets
    one; else the ``review_route`` the pieces of the group share, or, when they differ, the one of the strongest class
    (``CLASS_RANK``, the first in group order on a tie) with a ``GROUP_REVIEW_ROUTE_CONFLICT`` beacon naming them all."""
    documents = [(ref, read_json(self.directory / safe(ref) / "input.json") or {}) for ref in group]
    last = next((doc for ref, doc in documents if ref == item.ref), {})
    source = item.sources.get("reviewer") or ""
    if source and (source.startswith("item:") or last.get("review_mode") in ("none", "self")) \
            and not source.startswith(("config:", "invocation:")):
        item.sources.pop("reviewer", None)  # an item-local or disabled piece's selector is not a group override
    if item.sources.get("reviewer"):
        return
    planned = [(ref, doc["review_route"]) for ref, doc in documents
               if doc.get("review_mode") not in ("none", "self") and doc.get("review_route")]
    if not planned:
        item.input_doc = {key: value for key, value in item.input_doc.items() if key != "review_route"}
        return
    chosen = max(planned, key=lambda pair: CLASS_RANK.get(pair[1].get("class"), -1))
    item.input_doc = dict(item.input_doc, review_route=chosen[1])
    if len({json.dumps(route, sort_keys=True) for _, route in planned}) > 1:
        named = "; ".join(f"{ref}: {route_text(route)}" for ref, route in planned)
        self.progress.emit("info", reason_code="GROUP_REVIEW_ROUTE_CONFLICT",
                           message=f"group {number}: the pieces ask for different review routes ({named}); "
                                   f"the strongest class is used: {chosen[0]}: {route_text(chosen[1])}")


def route_text(route: dict) -> str:
    return "/".join(str(route[key]) for key in ("provider", "model", "class", "effort") if route.get(key)) or "-"


def group_review(self, number: int, group: list, effort: str) -> None:
    refs, shas = review_batch.commits_of_state({"items": {r: self.state["items"][r] for r in group}})
    if not shas:
        self.progress.emit("info", reason_code="GROUP_REVIEW_FAILED",
                           message=f"group {number} ({', '.join(group)}): no commit of the group to read; not reviewed")
        return
    diff = review_batch.diff_of(self.project, shas, review_batch.INCLUDE, list(review_batch.EXCLUDED))
    attempts = ((self.state.get("group_reviews") or {}).get(str(number)) or {}).get("attempts", 0) + 1
    if not review_batch.has_hunks(diff):  # nothing to read: the model is not asked (it would answer "none" to an empty page)
        self.state.setdefault("group_reviews", {})[str(number)] = {"refs": refs, "format": "empty", "error": "EMPTY_DIFF",
                                                                   "counts": {"Blocker": 0, "Major": 0, "Minor": 0},
                                                                   "attempts": attempts}
        self._save()
        self.progress.emit("info", reason_code="GROUP_REVIEW_FAILED",
                           message=f"group {number} ({', '.join(refs)}): the production diff is empty (the commits changed only "
                                   "tests, docs, fixtures or other excluded paths); not reviewed")
        return
    item = piece_item(self, next(a for a in (self._claim(f"item-{safe(r)}", [r], actor=self._claim_actor(),
                                                         actor_source=self._claim_actor_source())
                                             for r in group[-1:]) if a))
    self._resolve(item, persist=False)
    group_route(self, number, group, item)
    # The group review is its own logical stage: the cap is the stage's, not whichever piece step ran last.
    previous = self._bind_stage(item, f"group-review-{number}")
    try:
        self._admit_budget(item, "attempt")
        route = self._route(item, "reviewer")
        if not (self.conductor.get("argv") or {}).get("reviewer"):  # the catalog route; an effort the option names wins
            effort = reviewer_effort(self._reviewer_selector(item)[0], effort)
            route = dict(route, effort=effort, argv=launch.build_argv(self._launch_catalog(), "reviewer", route["provider"],
                                                                      model=route["model"], effort=effort, cwd=self.project,
                                                                      access=self._launch_access()))
        provider, model = route["provider"], route.get("model")
        prompt = review_batch.PROMPT.format(refs=", ".join(refs), max_tools=12) + diff
        raw = self.directory / "streams" / f"group-review-{number}.jsonl"
        raw.parent.mkdir(parents=True, exist_ok=True)
        began = time.monotonic()
        self.progress.emit("info", reason_code="GROUP_REVIEW_START",
                           message=f"group {number} ({', '.join(refs)}): {provider}/{model}/{effort}, {len(prompt) // 1000} KB")
        limits = item.options["limits"]  # the wall of a reviewer role, as ``route`` gives it a streaming role
        wall = limits.get("stage_timeout_s") or (limits.get("role_timeout_s") or {}).get("reviewer", 0)
        run = run_agent(self, item, f"group-review-{number}", "reviewer", route, prompt, raw, wall)
    finally:
        self._restore_stage(previous)
    text = run.text if not run.error else ""
    read = review_batch.verdict(text)
    found = read["counts"]
    path = self.directory / f"group-review-{number}.md"
    path.write_text(text or f"(no reply: {run.error}: {run.detail})", encoding="utf-8")
    kept = {"refs": refs, "file": self._relative(path), "counts": found, "effort": effort, "format": read["format"],
            "seconds": round(time.monotonic() - began, 1), "error": run.error, "attempts": attempts}
    loud = found["Blocker"] + found["Major"]
    followup = followup_input(self, number, refs, read, self._route(item, "executor").get("effort")) if loud else None
    if followup:
        kept["followup"] = followup
    if found["Blocker"]:
        kept["blocking"] = True
    self.state.setdefault("group_reviews", {})[str(number)] = kept
    self._save()
    seconds = f"in {kept['seconds']} s; {kept['file']}"
    if run.error:
        self.progress.emit("info", reason_code="GROUP_REVIEW_FAILED", message=f"group {number}: {run.error}: {run.detail}")
    elif read["format"] == "malformed":  # never reported as a clean review: the reply is not in the asked format
        self.progress.emit("info", reason_code="GROUP_REVIEW_FAILED", message=f"group {number}: malformed review-findings JSON; read {kept['file']}")
    else:
        self.progress.emit("info", reason_code="GROUP_REVIEW",
                           message=f"group {number}: {found['Blocker']} Blocker, {found['Major']} Major, {found['Minor']} Minor "
                                   f"{seconds}" + (f"; to correct them: orch conduct run --input {followup} --commit" if followup
                                                   else ""))
    if found["Blocker"]:  # a Blocker is not announced and forgotten: the run stops until a follow-up is settled (Major is not a stop)
        raise blocked_group(self, number, group, kept)
    if failed(kept) and requested(self, group):  # the pieces of the group were not reviewed on their own: nobody read them
        raise failed_group(number, group, kept)


def piece_checks(self, refs: list) -> list:
    """The command acceptance checks of the reviewed pieces, once each and in order (a check of ``cadence: phase`` is the
    broad pass of a phase, not a check of a correction): the follow-up must pass the tests the pieces passed. A check run
    in another folder keeps it as ``cd DIR && CMD``."""
    seen, found = set(), []
    for ref in refs:
        try:
            doc = json.loads((self.directory / safe(ref) / "input.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for check in (doc.get("acceptance") or {}).get("checks") or []:
            if check.get("kind", "acceptance") != "acceptance" or not check.get("cmd") or check.get("cadence") == "phase":
                continue
            folder = check.get("cwd") or "."
            command = check["cmd"] if folder in (".", "./") else f"cd {shlex.quote(folder)} && {check['cmd']}"
            if command not in seen:
                seen.add(command)
                found.append(command)
    return found


def session_ref(self, refs: list) -> dict:
    """``provenance.session_ref`` of a follow-up: where the reviewed group comes from (the run and every piece, so that a
    follow-up that starts fresh can be told what they did) and, when the last piece of the group kept a session with a
    fingerprint, that session with the digest of the identity a follow-up shares with it (``sessions.identity_digest``).
    A provider that cannot resume, a failed session or a slot migrated from an older state leave the origin alone."""
    slots = self.state.get("executor_sessions") or {}
    last = refs[-1]
    found = {"run": self.run_id, "item": last, "items": list(refs)}
    slot = slots.get(last) or slots.get(sessions.SHARED_KEY) or {}
    if slot.get("session") and slot.get("fingerprint") and slot.get("provider"):
        found.update(session=slot["session"], provider=slot["provider"],
                     fingerprint_digest=sessions.identity_digest(slot["fingerprint"]))
    return found


def followup_input(self, number: int, refs: list, read: dict, effort: Optional[str] = None,
                   name: Optional[str] = None) -> Optional[str]:
    """The Blocker and Major findings of a group review as a ready execution-input (``provenance: review_followup``): one
    command corrects them in a commit of their own, with the file source (``run --input FILE --commit``). The route minimum
    is the effort of the executor of the run (``high`` when it has none): a run configured for a lighter executor must be
    able to start its own follow-up (``ROUTE_UNDERSHOOT`` otherwise)."""
    stem = name or f"group-review-{number}"  # the files of the review: a run's group review, or batch-review.py's
    paths = review_batch.followup_paths(read["findings"])
    loud = [row for row in read["findings"] if row["severity"] in ("Blocker", "Major")]
    if not paths or not loud:
        return None
    # The group reviewer reports scenarios, not executed triage evidence. Do not invent an exit or a verified fix.
    confirmed = [{"finding": row["id"], "reproduction": {
        "cmd": row.get("reproduction") or "Reproduce the reported failure scenario",
        "observed": row["failure_scenario"]},
        "fix": "Reproduce this scenario, correct its cause inside the named scope, and add a regression check."}
        for row in loud]
    brief = fix_brief.build({"findings": loud}, {"confirmed": confirmed},
                            {row["id"]: finding_key(row) for row in loud}, {}, {
        "review": {"run": self.run_id, "item": ", ".join(refs), "round": number, "receipt": ""},
        "base": checks_base(self, refs), "findings": self._relative(self.directory / f"{stem}.md"),
        "scope_constraints": ["Change only the files named by these findings"], "required_checks": []})
    issues = contract.problems(brief, "fix-brief")
    if issues:
        raise ValueError("invalid group fix-brief: " + "; ".join(issues))
    write_json(self.directory / f"{stem}.fix-brief.json", brief)
    backlog = []
    remaining = loud
    pending = brief
    while pending["deferred"]["count"]:
        delivered = {row["id"] for row in pending["findings"]}
        remaining = [row for row in remaining if row["id"] not in delivered]
        pending = fix_brief.build({"findings": remaining}, {"confirmed": confirmed},
                                  {row["id"]: finding_key(row) for row in remaining}, brief["limits"], {
                                      "review": brief["review"], "base": brief["base"],
                                      "findings": brief["deferred"]["ref"],
                                      "scope_constraints": brief["scope_constraints"], "required_checks": []})
        issues = contract.problems(pending, "fix-brief")
        if issues or not pending["findings"]:
            raise ValueError("invalid follow-up fix-brief: " + "; ".join(issues or ["no finding fits the limits"]))
        path = self.directory / f"{stem}.fix-brief.{len(backlog) + 2}.json"
        write_json(path, pending)
        backlog.append({"path": self._relative(path), "digest": canonical_digest(pending)})
    goal = ("Correct the review findings of pieces " + ", ".join(refs) + ". "
            "The reproduction below is reported by the reviewer and must be verified before correction.\n"
            + fix_brief.render(brief))
    reference = session_ref(self, refs)
    run_doc = getattr(self, "run_doc", None) or {}  # scripts/batch-review.py owns no run document
    plan = None if (run_doc.get("source") or {}).get("kind") == "file" else run_doc.get("plan")  # the plan of the pieces
    commands = piece_checks(self, refs)
    # the reviewed pieces' own command checks decide when they exist: a procedure check (a verdict the executor must report)
    # cost a round and a full checks pass whenever the executor forgot it; only a follow-up without commands keeps one
    checks = [f"V{index}={command}" for index, command in enumerate(commands, 1)]
    procedures = [] if commands else ["V1=every listed finding is fixed and the tests that cover the touched code pass"]
    try:
        doc = adhoc.build_adhoc_input(goal, paths, checks=checks, procedures=procedures,
                                      why=f"group review {number} of this run",
                                      route={"class": "implementation", "effort": effort or "high"},
            provenance={**adhoc.support_provenance("review_followup", plan=plan, items=list(refs),
                                                   findings=[finding_key(row) for row in loud]),
                        **({"fix_briefs": backlog} if backlog else {}),
                        **({"session_ref": reference} if reference else {})})
    except adhoc.AdhocError as error:
        self.progress.emit("info", reason_code="GROUP_REVIEW_FOLLOWUP_FAILED", message=f"group {number}: {error}"[:200])
        return None
    target = self.directory / f"{stem}.followup.json"
    write_json(target, doc)
    return self._relative(target)


def checks_base(self, refs: list) -> str:
    """The first piece's recorded base, when present, for the follow-up brief."""
    for ref in refs:
        step = ((self.state.get("items", {}).get(ref, {}).get("steps") or {}).get("brief") or {})
        base = (step.get("result") or {}).get("base")
        if base:
            return base
    return ""
