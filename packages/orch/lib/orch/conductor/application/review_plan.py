"""The review plan of a batch: chosen once before the first piece runs, carried out after the last piece of each group.

``decide`` asks the strategist (a small model call, ``review.strategist: model``; ``rules`` skips the call) how the batch is
reviewed (``policies/review_strategy.py``) and keeps the answer in ``state.review_strategy`` and ``review-strategy.json`` of the
run. ``group_review_due`` runs after every piece: when the piece is the last of its group and the group is done it reads the
commits of the group once (``review_batch``) and keeps the reply in ``group-review-<n>.md`` of the run folder; Blocker and Major
findings are announced (``GROUP_REVIEW``) and left to the owner or the observer to correct in a commit of their own."""
from __future__ import annotations

import json
import shlex
import time
from typing import Optional

from orch import adhoc, launch
from orch.conductor import options as opts, process, review_batch
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.clock import utc_now
from orch.conductor.infrastructure.files import read_json, safe, write_json
from orch.conductor.policies import review_strategy as strategy
from orch.conductor.policies.routing import CLASS_RANK

PER_PIECE_OFF = ("groups", "single", "none")  # the strategy modes in which a piece is not reviewed on its own


def piece_item(self, answer: dict) -> Item:
    state = self.state["items"].setdefault(answer["ref"], {"steps": {}, "retries_used": 0, "orch_run": answer["run_id"]})
    return Item(ref=answer["ref"], orch_run=answer["run_id"], state=state, directory=self.directory / safe(answer["ref"]),
                claim=answer)


def forced(mode: str, pieces: list, proposal: dict) -> dict:
    """``review.strategy`` named a mode: the groups it implies (the rules' groups for ``groups`` when they are some)."""
    refs = [piece["ref"] for piece in pieces]
    if mode == "none":
        groups = []
    elif mode == "single":
        groups = [refs] if len(refs) <= 12 else [refs[i:i + 12] for i in range(0, len(refs), 12)]
    elif mode == "each":
        groups = [[ref] for ref in refs]
    else:
        groups = proposal["groups"] if proposal["mode"] == "groups" else \
            [refs[i:i + strategy.MAX_GROUP] for i in range(0, len(refs), strategy.MAX_GROUP)]
    return {"mode": mode, "groups": groups, "reviewer": proposal["reviewer"], "reason": f"review.strategy: {mode}",
            "source": "option"}


def run_agent(self, item: Item, key: str, role: str, route: dict, prompt: str, raw, timeout_s: int):
    """Batch roles get the same process ownership record as per-piece roles."""
    if item.options:
        self._admit_budget(item)
    prompt_file = item.directory / "prompts" / f"{key}.md"
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(prompt, encoding="utf-8")
    handle = self._agent_start(item, key, role, route, prompt_file, 1)
    try:
        run = process.run_role(self._role_argv(item, role, route), prompt, transport=route["transport"], cwd=self.project,
                               timeout_s=timeout_s, raw_path=raw, env=self._role_env(item, role, route),
                               provider=route["provider"], agent_directory=handle["directory"])
        self._tokens(item, run.usage, usage_complete=run.usage_complete, attempt=self._relative(raw))
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
    """Choose the review plan of this batch once (a resume reads the kept plan)."""
    if self.state.get("review_strategy") is not None:
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
    if mode != "auto":
        plan = forced(mode, pieces, proposal)
    elif review.get("strategist", "model") == "rules" or strategy.unreviewed(pieces):
        plan = proposal  # the plan gave no piece a review: nothing for a strategist to weigh
    else:
        plan = ask_strategist(self, first, pieces, proposal) or proposal
    plan = dict(plan, decided_at=utc_now())
    self.state["review_strategy"] = plan
    write_json(self.directory / "review-strategy.json", plan)
    self._save()
    groups = "; ".join(" + ".join(group) for group in plan["groups"]) or "none"
    effort = group_effort(self, first.options["reviewer"], plan["reviewer"]["effort"])
    self.progress.emit("info", reason_code="REVIEW_STRATEGY",
                       message=f"{plan['mode']} ({plan['source']}): {groups} at effort {effort}; {plan['reason']}")


def per_piece_off(self) -> bool:
    plan = self.state.get("review_strategy") or {}
    return plan.get("mode") in PER_PIECE_OFF


def group_review_due(self, ref: str) -> None:
    """After a piece: the review of its group when it was the group's last piece and every piece of the group is done."""
    plan = self.state.get("review_strategy") or {}
    if plan.get("mode") not in ("groups", "single"):
        return
    for number, group in enumerate(plan["groups"], 1):
        if ref != group[-1]:
            continue
        done = [self.state["items"].get(r, {}).get("outcome") in ("done", "done_with_deviations") for r in group]
        if all(done) and str(number) not in (self.state.get("group_reviews") or {}):
            group_review(self, number, group, plan["reviewer"]["effort"])
        return


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
    """The reviewer route of a group review, set on ``item`` (the last piece): the reviewer of the run when a layer sets
    one; else the ``review_route`` the pieces of the group share, or, when they differ, the one of the strongest class
    (``CLASS_RANK``, the first in group order on a tie) with a ``GROUP_REVIEW_ROUTE_CONFLICT`` beacon naming them all."""
    if item.sources.get("reviewer"):
        return
    planned = [(ref, doc["review_route"]) for ref in group
               for doc in [read_json(self.directory / safe(ref) / "input.json") or {}] if doc.get("review_route")]
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
    if not review_batch.has_hunks(diff):  # nothing to read: the model is not asked (it would answer "none" to an empty page)
        self.state.setdefault("group_reviews", {})[str(number)] = {"refs": refs, "format": "empty", "error": "EMPTY_DIFF",
                                                                   "counts": {"Blocker": 0, "Major": 0, "Minor": 0}}
        self._save()
        self.progress.emit("info", reason_code="GROUP_REVIEW_FAILED",
                           message=f"group {number} ({', '.join(refs)}): the production diff is empty (the commits changed only "
                                   "tests, docs, fixtures or other excluded paths); not reviewed")
        return
    item = piece_item(self, next(a for a in (self._claim(f"item-{safe(r)}", [r]) for r in group[-1:]) if a))
    self._resolve(item, persist=False)
    group_route(self, number, group, item)
    self._admit_budget(item)
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
    run = run_agent(self, item, f"group-review-{number}", "reviewer", route, prompt, raw, 0)
    text = run.text if not run.error else ""
    read = review_batch.verdict(text)
    found = read["counts"]
    path = self.directory / f"group-review-{number}.md"
    path.write_text(text or f"(no reply: {run.error}: {run.detail})", encoding="utf-8")
    kept = {"refs": refs, "file": self._relative(path), "counts": found, "effort": effort, "format": read["format"],
            "seconds": round(time.monotonic() - began, 1), "error": run.error}
    loud = found["Blocker"] + found["Major"]
    followup = followup_input(self, number, refs, read, self._route(item, "executor").get("effort")) if loud else None
    if followup:
        kept["followup"] = followup
    self.state.setdefault("group_reviews", {})[str(number)] = kept
    self._save()
    seconds = f"in {kept['seconds']} s; {kept['file']}"
    if run.error:
        self.progress.emit("info", reason_code="GROUP_REVIEW_FAILED", message=f"group {number}: {run.error}: {run.detail}")
    elif read["format"] == "malformed":  # never reported as a clean review: the reply is not in the asked format
        self.progress.emit("info", reason_code="GROUP_REVIEW_FAILED", message=f"group {number}: the reply has no readable "
                           f"'## Findings' section (neither [Severity] lines nor 'none'); read {kept['file']}")
    else:
        self.progress.emit("info", reason_code="GROUP_REVIEW",
                           message=f"group {number}: {found['Blocker']} Blocker, {found['Major']} Major, {found['Minor']} Minor "
                                   f"{seconds}" + (f"; to correct them: orch conduct run --input {followup} --commit" if followup
                                                   else ""))


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


def followup_input(self, number: int, refs: list, read: dict, effort: Optional[str] = None) -> Optional[str]:
    """The Blocker and Major findings of a group review as a ready execution-input (``provenance: review_followup``): one
    command corrects them in a commit of their own, with the file source (``run --input FILE --commit``). The route minimum
    is the effort of the executor of the run (``high`` when it has none): a run configured for a lighter executor must be
    able to start its own follow-up (``ROUTE_UNDERSHOOT`` otherwise)."""
    paths = review_batch.followup_paths(read["findings"])
    loud = [row for row in read["findings"] if row["severity"] in ("Blocker", "Major")]
    if not paths or not loud:
        return None
    goal = ("Correct these confirmed review findings of the pieces " + ", ".join(refs) + ", each in the file it names; change "
            "nothing else:\n" + "\n".join(f"- [{row['severity']}] {row['text']}" for row in loud))
    commands = piece_checks(self, refs)
    # the reviewed pieces' own command checks decide when they exist: a procedure check (a verdict the executor must report)
    # cost a round and a full checks pass whenever the executor forgot it; only a follow-up without commands keeps one
    checks = [f"V{index}={command}" for index, command in enumerate(commands, 1)]
    procedures = [] if commands else ["V1=every listed finding is fixed and the tests that cover the touched code pass"]
    try:
        doc = adhoc.build_adhoc_input(goal, paths, checks=checks, procedures=procedures,
                                      why=f"group review {number} of this run",
                                      route={"class": "implementation", "effort": effort or "high"},
                                      provenance=adhoc.support_provenance("review_followup"))
    except adhoc.AdhocError as error:
        self.progress.emit("info", reason_code="GROUP_REVIEW_FOLLOWUP_FAILED", message=f"group {number}: {error}"[:200])
        return None
    target = self.directory / f"group-review-{number}.followup.json"
    write_json(target, doc)
    return self._relative(target)
