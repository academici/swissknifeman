"""The advisor (P10.4): advice on a blocking question, on checks that stay red and on findings the triager rejected;
advice that only the owner may apply waits as a question."""
from __future__ import annotations

import json
from typing import Callable, NamedTuple, Optional

from orch.contracts import required_digest
from orch.conductor import checks as checks_mod, contract, prompts, questions as questions_mod, risk, scope
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock

ADVICE_DIFF_CHARS = 40_000  # the diff an advisor reads is cut here


def advisor_cfg(self) -> dict:
    return getattr(self.settings, "advisor", None) or {}


def advisor_on(self) -> bool:
    return bool(self._advisor_cfg().get("enabled"))


def advice_slot(self, item: Item, ref: str) -> Optional[int]:
    """The ordinal of the advice on problem ``ref``: the earlier one when the problem was advised on (a resume walks it
    again and must not count it twice), a new one while ``orch.advisor.max_rounds`` allows, else ``None``."""
    known = item.state.setdefault("advice_of", {})
    if ref in known:
        return known[ref]
    if len(known) >= int(self._advisor_cfg().get("max_rounds") or 0):
        self.progress.emit("info", item=item.ref, reason_code="ADVISOR_LIMIT",
                           message=f"no advice on {ref}: orch.advisor.max_rounds ({len(known)}) is spent")
        return None
    known[ref] = len(known) + 1
    self._save()
    return known[ref]


def advise(self, item: Item, number: int, ref: str, problem: str, evidence: list, *, fixed: bool = False
           ) -> Optional[dict]:
    """One advice round: the advisor role reads ``problem`` and the local ``evidence`` (and may ask the research
    sources) and answers a closed ``advice``, kept as ``advice-<n>.json`` in the artifacts of the piece. The agent run
    names the problem as its ``causation``. ``None`` when the advisor failed: an advice is help, never a reason for a
    piece to stop, so the problem goes on as it would without one.

    With ``orch.advisor.panel`` the round may be a panel (see :func:`advise_panel`): first, for the trigger ``always``;
    after the single advice, for ``low_confidence``. The panel is still one round of ``max_rounds`` and returns the same
    closed advice (and ``panel: True``), so the gates of :func:`reading` read it like any other. ``fixed``: the problem
    names the option ids (a question with options); otherwise each member names its own ways and the panel compares
    them by content (see :func:`tally`)."""
    on = self._advisor_cfg().get("panel_on") or ["low_confidence"]
    if panel_members(self) and "always" in on:
        found = advise_panel(self, item, number, ref, problem, evidence, fixed=fixed)
        if found is not None:
            return found
    found = advise_single(self, item, number, ref, problem, evidence)
    if found is not None and "low_confidence" in on and found["advice"]["confidence"] == "low" and panel_members(self):
        panelled = advise_panel(self, item, number, ref, problem, evidence, first=found, fixed=fixed)
        if panelled is not None:
            return panelled
    return found


def advise_single(self, item: Item, number: int, ref: str, problem: str, evidence: list) -> Optional[dict]:
    try:
        return self._step(item, f"advice.{number}", lambda: call_advisor(
            self, item, f"advice.{number}", f"advice-{number}.json", f"query-{number}.txt", ref, problem, evidence,
            item.routes["advisor"]), role="advisor", route=self.label(item.routes["advisor"]), verdict=said)
    except Stop as stop:
        self.progress.emit("info", item=item.ref, stage=f"advice.{number}", reason_code="ADVISOR_FAILED",
                           message=f"{stop.code}: {stop.message}"[:300])
        return None


def said(result: dict) -> str:
    return f"{result['advice']['recommendation']} ({result['advice']['confidence']})"


def call_advisor(self, item: Item, key: str, artifact: str, query: str, ref: str, problem: str, evidence: list,
                 route: dict, panel: tuple = ()) -> dict:
    """The advisor role on ``route`` as step ``key``: its closed advice saved as ``artifact``."""
    from orch import research as research_mod
    sources = [source.id for source in research_mod.sources_from(self.settings)]
    role = "advisor"
    command = ""
    if sources:
        query_file = item.directory / "advice" / query
        query_file.parent.mkdir(parents=True, exist_ok=True)
        query_file.write_text(problem + "\n", encoding="utf-8")
        command = self._research_command(sources, query_file)
    prompt = prompts.advisor(item.input_doc, item=item.ref, step=key, problem_ref=ref, problem=problem,
                             evidence=evidence, sources=sources, command=command, roles_dir=self.roles_dir, stub=self._stub(role, route),
                             skills=self._skills(item, role), repo_rules=self._repo_rules(item, role),
                             skill_texts=self._skill_texts(item, role), panel=panel)
    doc, meta = self._role(item, key, role, prompt, "advice", extra=lambda found: contract.advice_problems(ref, found),
                           causation=ref)
    saved = self._write_artifact(item, artifact, doc)
    return {"advice": doc, "file": self._relative(saved), **meta}


# ---------------------------------------------------------------------------------------------------------- the panel

PANEL_MAX = 3


class PanelPorts(NamedTuple):
    """The two lookups of a panel member that live above the stages (``Conductor.panel_ports``): its route, and why it may
    not start (``None`` when it may)."""
    route: Callable
    admit: Callable


CATEGORIES = ("security", "destructive", "public-api", "scope-expansion", "other")  # the strictest first
CONFIDENCE = ("low", "medium", "high")


def panel_members(self) -> list:
    """The routes of ``orch.advisor.panel`` (at most three); fewer than two is no panel."""
    members = list(self._advisor_cfg().get("panel") or [])[:PANEL_MAX]
    return members if len(members) >= 2 else []


def tally(advices: list, *, fixed: bool = True) -> tuple:
    """``(kind, chosen id, indices that chose it)``: ``agreement`` (all recommend the same option), ``majority`` (more than
    half) or ``split``. A tie takes the group of the earliest member. Without ``fixed`` option ids each member names its
    own ways, so the same id may mean different things: members agree only on the same id with the same text."""
    groups: dict = {}
    for index, advice in enumerate(advices):
        groups.setdefault(vote(advice, fixed), []).append(index)
    _, agree = max(groups.items(), key=lambda row: (len(row[1]), -row[1][0]))
    chosen = advices[agree[0]]["recommendation"]
    kind = "agreement" if len(agree) == len(advices) else "majority" if len(agree) * 2 > len(advices) else "split"
    return kind, chosen, agree


def vote(advice: dict, fixed: bool = True) -> object:
    """What a member votes for: the recommended id, or with ids of its own the id and the text of that option."""
    if fixed:
        return advice["recommendation"]
    text = next((row["text"] for row in advice["options"] if row["id"] == advice["recommendation"]), "")
    return advice["recommendation"], " ".join(text.split()).casefold()


def merged(ref: str, advices: list, stand: list, chosen: str, *, owner: bool = False) -> dict:
    """The one advice a panel stands for. ``stand`` are the indices behind ``chosen``: their options come first (the rest
    follow, so the owner sees every way) and they give the strictest category, the lowest confidence, the sources and any
    need of the owner. ``owner`` forces ``needs_owner`` (a majority the critic did not confirm, a split)."""
    order = list(stand) + [index for index in range(len(advices)) if index not in stand]
    options: list = []
    for index in order:
        options += [option for option in advices[index]["options"] if option["id"] not in {row["id"] for row in options}]
    behind = [advices[index] for index in stand]
    sources: list = []
    for advice in behind:
        sources += [row for row in advice["sources"] if row not in sources]
    doc = {"problem_ref": ref, "options": options, "recommendation": chosen,
           "confidence": min((advice["confidence"] for advice in behind), key=CONFIDENCE.index), "sources": sources,
           "needs_owner": owner or any(advice["needs_owner"] for advice in behind)}
    categories = [advice["category"] for advice in behind if advice.get("category")]
    if categories:
        doc["category"] = min(categories, key=CATEGORIES.index)
    return doc


def positions(advices: list) -> list:
    """The anonymised positions the critic reads."""
    return [{"recommendation": advice["recommendation"], "confidence": advice["confidence"],
             "options": advice["options"]} for advice in advices]


def advise_panel(self, item: Item, number: int, ref: str, problem: str, evidence: list, first: Optional[dict] = None,
                 *, fixed: bool = True) -> Optional[dict]:
    """The advisor panel on one problem: each member of ``orch.advisor.panel`` advises on its own route without seeing the
    others (``advice.<n>.p<i>``); a synthesis follows. ``agreement`` is applied; a ``majority`` gets one round of critique
    by the first dissenting member, who sees the anonymised positions and must cite evidence: when the critic recommends
    the majority's option the majority stands, else the owner decides (``needs_owner``); a ``split`` is the owner's. The
    result is a closed advice with ``panel: True`` and the panel record ``advice-<n>-panel.json``. At most ``len(panel)+1``
    calls, each admitted by the budget like any step. A member that cannot start is skipped (``ADVISOR_PANEL_FAILED``);
    with fewer than two answers ``None`` is returned and the single advisor decides (``first``, when it was asked)."""
    members, answers = panel_members(self), []
    for index, member in enumerate(members, 1):
        found = member_advice(self, item, f"advice-p{index}.{number}", f"advice-{number}-p{index}.json",
                              f"query-{number}-p{index}.txt", ref, problem, evidence, member)
        if found is not None:
            answers.append((index, member, found))
    if len(answers) < 2:
        self.progress.emit("info", item=item.ref, stage=f"advice.{number}", reason_code="ADVISOR_PANEL_FAILED",
                           message=f"{len(answers)} of {len(members)} panel members answered: the single advisor decides")
        return None
    advices = [found["advice"] for _, _, found in answers]
    kind, chosen, agree = tally(advices, fixed=fixed)
    critic, everyone = None, list(range(len(advices)))
    if kind == "agreement":
        advice = merged(ref, advices, agree, chosen)
    elif kind == "majority":
        dissent = next(i for i in range(len(advices)) if i not in agree)
        index, member, _ = answers[dissent]
        asked = member_advice(self, item, f"advice-critic.{number}", f"advice-{number}-critic.json",
                                f"query-{number}-critic.txt", ref, problem, evidence, member, panel=tuple(positions(advices)))
        if asked is None:  # a critic that cannot answer confirms nothing
            critic = {"member": index, "recommendation": None, "agrees": False}
            advice = merged(ref, advices, agree, chosen, owner=True)
        else:
            opinion = asked["advice"]
            agrees = (vote(opinion, fixed) == vote(advices[agree[0]], fixed)
                      and bool(opinion["sources"]))  # the critic must cite evidence
            critic = {"member": index, "recommendation": opinion["recommendation"], "agrees": agrees,
                      "sources": opinion["sources"], "file": asked["file"]}
            advice = merged(ref, advices + [opinion], agree + [len(advices)] if agrees else agree, chosen,
                            owner=not agrees)
    else:
        advice = merged(ref, advices, everyone, chosen, owner=True)
    record = {"problem_ref": ref, "members": [{"member": index, "route": found["route"], "file": found["file"],
                                               "advice": found["advice"]} for index, _, found in answers],
              "synthesis": {"kind": kind, "chosen": chosen, "advice": advice, **({"critic": critic} if critic else {})}}
    if first is not None:
        record["trigger"] = {"file": first["file"], "confidence": first["advice"]["confidence"]}
    invalid = contract.problems(record, "advice-panel")
    if invalid:  # never written unchecked; an advice is help, so the single advisor decides as without a panel
        self.progress.emit("info", item=item.ref, stage=f"advice.{number}", reason_code="ADVISOR_PANEL_FAILED",
                           message="invalid advice-panel: " + "; ".join(invalid[:3]))
        return None
    saved = self._write_artifact(item, f"advice-{number}-panel.json", record)
    self.progress.emit("info", item=item.ref, stage=f"advice.{number}", reason_code="ADVISOR_PANEL",
                       message=f"panel {kind}: {chosen} ({len(answers)} of {len(members)} members"
                               + (f", critic {'agrees' if critic['agrees'] else 'does not agree'}" if critic else "") + ")")
    return {"advice": advice, "file": self._relative(saved), "panel": True}


def member_advice(self, item: Item, key: str, artifact: str, query: str, ref: str, problem: str, evidence: list,
                  member: dict, panel: tuple = ()) -> Optional[dict]:
    """One panel call on the route of ``member`` (``None`` and ``ADVISOR_PANEL_FAILED`` when it cannot start or fails)."""
    try:
        route = self.panel_ports.route(item, "advisor", member)
        refused = self.panel_ports.admit(item, "advisor", route)
        if refused:
            raise Stop("PROVIDER_UNAVAILABLE", refused)
        kept = item.routes["advisor"], dict(item.state.get("route_overrides") or {})
        item.routes["advisor"] = route
        try:
            return self._step(item, key, lambda: {**call_advisor(self, item, key, artifact, query, ref, problem, evidence,
                                                                 route, panel), "route": self.label(route)},
                              role="advisor", route=self.label(route), verdict=said)
        finally:  # the route of a panel member never becomes the route of the advisor
            item.routes["advisor"] = kept[0]
            overrides = item.state.get("route_overrides")
            if overrides is not None and "advisor" in overrides and "advisor" not in kept[1]:
                del overrides["advisor"]
    except Stop as stop:
        self.progress.emit("info", item=item.ref, stage=key, reason_code="ADVISOR_PANEL_FAILED",
                           message=f"{member.get('provider')}: {stop.code}: {stop.message}"[:300])
        return None


def category_paths(self, item: Item) -> dict:
    """Path evidence for owner categories: effective patterns may add to the builtin/trusted floor."""
    changed = set(self._changed(item)) | set((item.input_doc.get("scope") or {}).get("write_set") or [])
    effective = (self.settings.conductor.get("risk") or {}).get("patterns") or {}
    floor = self.settings.conductor.get("_category_patterns") or {}
    patterns = {feature: set(risk.DEFAULT_PATTERNS[feature]) | set(floor.get(feature) or [])
                         | set(effective.get(feature) or [])
                for feature in ("security", "public_cli", "schema")}
    categories = {}
    for category, features in (("security", ("security",)), ("public-api", ("public_cli", "schema"))):
        hits = sorted(path for path in changed
                      if any(scope.matches(path, pattern) for feature in features for pattern in patterns[feature]))
        if hits:
            categories[category] = hits
    outside = self._outside(item)
    if outside:
        categories["scope-expansion"] = sorted(outside)
    return categories


def code_categories(self, item: Item) -> set:
    """Categories established by code, independently of the model's category."""
    return set(category_paths(self, item))


def authority(self, item: Item, mode: str, confidence: Optional[str] = None) -> dict:
    """The effective authority behind an automatic question resolution; defaults have no model confidence."""
    return {"mode": mode, "gate": sorted(self._advisor_cfg().get("human_gate") or []),
            "code_categories": sorted(code_categories(self, item)), "confidence": confidence}


def reading(self, advice: dict, item: Item) -> tuple:
    """``(recommended option, why the owner must decide or None)``; model output never lowers a gate."""
    option = next(entry for entry in advice["options"] if entry["id"] == advice["recommendation"])
    gate = set(self._advisor_cfg().get("human_gate") or [])
    reasons = []
    if advice["needs_owner"]:
        reasons.append("advisor: the advisor says only the owner can decide")
    if advice.get("category") in gate:
        reasons.append(f"advisor: category {advice['category']} is held by orch.advisor.human_gate")
    paths = category_paths(self, item)
    for category in sorted(set(paths) & gate):
        reasons.append(f"code: {category} ({', '.join(paths[category])}) is held by orch.advisor.human_gate")
    minimum = self._advisor_cfg().get("min_confidence", "medium")
    ranks = {"low": 0, "medium": 1, "high": 2}
    if ranks[advice["confidence"]] < ranks[minimum]:
        reasons.append(f"confidence {advice['confidence']} is below orch.advisor.min_confidence {minimum}")
    held = "; ".join(reasons) or None
    if held:
        self.progress.emit("info", item=item.ref, reason_code="ADVICE_HELD", message=held)
    return option, held


def advice_summary(file: str, advice: dict, held: Optional[str]) -> dict:
    return {"file": file, "recommendation": advice["recommendation"], "confidence": advice["confidence"],
            "needs_owner": advice["needs_owner"], **({"category": advice["category"]} if advice.get("category") else {}),
            **({"held": held} if held else {})}


def advice_note(entry: dict) -> str:
    """What an advised question adds to its escalation: the advice, and why the owner still decides."""
    found = entry.get("advice")
    if not found:
        return ""
    return (f" (advisor, {found['file']}: recommends {found['recommendation']}, {found['confidence']} confidence"
            + (f"; for the owner: {found['held']}" if found.get("held") else "") + ")")


def advice_evidence(self, item: Item, *parts, diff: bool = True) -> list:
    """The local evidence of a problem as ``(kind, text)`` blocks: ``parts`` (kind, title, text, fence tag) and the
    diff of the candidate against the head."""
    found = [(kind, prompts.evidence(title, text, tag)) for kind, title, text, tag in parts]
    if diff:
        shown = checks_mod.diff(self.project, checks_mod.head(self.project)) or "(no tracked changes)"
        if len(shown) > ADVICE_DIFF_CHARS:
            shown = shown[:ADVICE_DIFF_CHARS] + "\n(cut: the diff is longer; read the files)"
        found.append(("diff", prompts.evidence("Diff of the candidate against the head", shown, "diff")))
    return found


def hold(self, item: Item, number: int, advice: dict, file: str, held: str, problem: str) -> dict:
    """The question to the owner for advice that must not be applied by the conductor: ``orch-advice-<n>`` (kind decision, the
    options of the advice), saved with the advice like any queued question; ``orch conduct answer`` and ``resume --retry``
    then apply the owner's choice."""
    store = self._questions(item)
    asked = {"id": f"orch-advice-{number}", "revision": 1, "kind": "decision", "text": problem, "blocking": True,
             "options": [{"id": option["id"], "label": option["text"][:200]} for option in advice["options"]]}
    binding = {"run": self.run_id, "item": item.ref, "step": f"advice.{number}",
               "input_digest": item.input_doc.get("digest"), "input_part_digest": required_digest(item.input_doc)}
    questions_mod.record(store, [asked], binding, clock.utc_now())
    entry = store[asked["id"]]
    entry["advice"] = self._advice_summary(file, advice, held)
    self._save_questions(item)
    return entry


def owner_choice(advice: dict, entry: dict) -> Optional[tuple]:
    """``(option, by)`` when the owner answered the question of held advice, else ``None``."""
    if entry["status"] != "applied" or not entry.get("resolution"):
        return None
    chosen = next((option for option in advice["options"] if option["id"] == entry["resolution"]["value"]), None)
    return (chosen, entry["resolution"]["by"]) if chosen else None


def advise_question(self, item: Item, key: str, entry: dict, report: dict) -> bool:
    """``questions = advisor``: the advisor reads a blocking question. Advice the conductor may apply answers it
    (resolution ``by: advisor``) and ``True`` is returned; any other stays queued with the advice. Approvals and
    credentials are the owner's by their kind, a question is answered by the policy only once, and past
    ``max_rounds`` the question is queued."""
    if entry["kind"] in ("approval", "credential") or entry.get("auto_answered"):
        return False
    ref = f"question:{entry['id']}@{entry['revision']}"
    number = self._advice_slot(item, ref)
    if number is None:
        return False
    options = "".join(f"\n- `{row['id']}`: {row['label']}" for row in entry.get("options") or [])
    problem = (f"The executor asked a blocking question ({entry['kind']}) and cannot go on without an answer:\n\n"
               f"{entry['text']}\n"
               + (f"\nOptions (recommend one of these ids):{options}\n" if options else "")
               + (f"\nThe executor's own default: {entry['default']}\n" if "default" in entry else "")
               + (f"\nRisk the executor named: {entry['risk']}\n" if entry.get("risk") else ""))
    found = self._advise(item, number, ref, problem, self._advice_evidence(
        item, ("candidate", "Report of the executor", json.dumps(report, ensure_ascii=False, indent=2), "json")),
        fixed=bool(entry.get("options")))
    if found is None:
        return False
    advice = found["advice"]
    option, held = self._reading(advice, item)
    ids = [row["id"] for row in entry.get("options") or []]
    if held is None and ids and option["id"] not in ids:
        held = f"advisor: the recommendation {option['id']} is not one of the options of the question"
        self.progress.emit("info", item=item.ref, stage=key, reason_code="ADVICE_HELD", message=held)
    entry["advice"] = self._advice_summary(found["file"], advice, held)
    if held:
        return False
    by = "panel" if found.get("panel") else "advisor"
    entry["resolution"] = {"value": option["id"] if ids else option["text"], "by": by, "at": clock.utc_now(),
                           "authority": authority(self, item, by, advice["confidence"])}
    entry["status"], entry["auto_answered"] = "applied", True
    self.progress.emit("info", item=item.ref, stage=key, reason_code="QUESTION_ADVISED",
                       message=f"question {entry['id']} answered by the {by} with {option['id']} ({found['file']})")
    return True


def applied(self, item: Item, number: int, ref: str, problem: str, found: dict, option: dict, by: str) -> None:
    """Remember an advice the conductor applied on its own (not held for the owner) to red checks or a rejected finding:
    ``finish`` records it as a decision of the plan after register. A question answered by the owner is a decision by its
    own record; one advice is remembered once, however often its round is walked."""
    rows = item.state.setdefault("advice_applied", [])
    if any(row["ref"] == ref for row in rows):
        return
    rows.append({"number": number, "ref": ref, "problem": problem,
                 "options": [{"id": row["id"], "label": row["text"][:200]} for row in found["advice"]["options"]],
                 "recommendation": option["id"], "confidence": found["advice"]["confidence"], "by": by,
                 "file": found["file"], "at": clock.utc_now()})
    self._save()


def advise_red(self, item: Item, round_no: int, red: list, report: dict) -> Optional[dict]:
    """Red checks that the ``check_fixes`` allowance cannot correct again. ``None``: no advice (the piece is blocked
    ``CHECKS_RED`` as without an advisor). ``{"held": text}``: the owner decides, the question waits with the advice.
    ``{"text": correction}``: one more correction round, by the advice."""
    if not self._advisor_on():
        return None
    ref = f"checks:{round_no}"
    number = self._advice_slot(item, ref)
    if number is None:
        return None
    names = ", ".join(row["id"] for row in red)
    problem = (f"Acceptance checks {names} stay red after the corrections the run allows. Name the ways to go on and "
               "recommend one; the conductor may make one more correction round by it.")
    found = self._advise(item, number, ref, problem, self._advice_evidence(
        item, ("verification", "Red acceptance checks", prompts.check_correction(red), "text"),
        ("candidate", "Report of the executor", json.dumps(report, ensure_ascii=False, indent=2), "json")))
    if found is None:
        return None
    advice = found["advice"]
    option, held = self._reading(advice, item)
    by = "panel" if found.get("panel") else "advisor"
    if held:
        entry = self._hold(item, number, advice, found["file"], held, problem)
        chosen = self._owner_choice(advice, entry)
        if chosen is None:
            return {"held": f"{entry['id']} {entry['text']}{self._advice_note(entry)}"}
        option, by = chosen
    else:
        applied(self, item, number, ref, problem, found, option, by)
    return {"text": prompts.advice_correction(advice, option, by=by, problem=prompts.check_correction(red))}


def retriage(self, item: Item, number: int, findings: dict, triage: dict) -> tuple:
    """``(triage, held)``: a Blocker or Major finding the triager rejected is a disagreement with the reviewer, and the
    advisor reads both sides; the findings are then triaged again with the advice (``triage.<n>-a``). ``held`` is the
    text of the question to the owner when the advice must not be applied by the conductor."""
    severe = [entry for entry in triage.get("rejected", [])
              if self._severity_of(findings, entry["finding"]) in ("blocker", "major")]
    if not severe or not self._advisor_on():
        return triage, None
    ref = f"findings:{number}"
    slot = self._advice_slot(item, ref)
    if slot is None:
        return triage, None
    ids = ", ".join(entry["finding"] for entry in severe)
    problem = (f"The reviewer raised finding(s) {ids}, the triager rejected them. Name the ways to go on (confirm, keep "
               "the rejection, or something between) and recommend one; the findings are then triaged again with your advice.")
    found = self._advise(item, slot, ref, problem, self._advice_evidence(
        item, ("findings", "Review findings", json.dumps(findings, ensure_ascii=False, indent=2), "json"),
        ("findings", "Triage of the findings", json.dumps(triage, ensure_ascii=False, indent=2), "json")))
    if found is None:
        return triage, None
    advice = found["advice"]
    option, held = self._reading(advice, item)
    by = "panel" if found.get("panel") else "advisor"
    if held:
        entry = self._hold(item, slot, advice, found["file"], held, problem)
        chosen = self._owner_choice(advice, entry)
        if chosen is None:
            return triage, f"{entry['id']} {entry['text']}{self._advice_note(entry)}"
        option, by = chosen
    else:
        applied(self, item, slot, ref, problem, found, option, by)
    return self._triage(item, number, findings, advice=prompts.advice_for_triage(advice, option, by=by)), None
