"""The advisor (P10.4): advice on a blocking question, on checks that stay red and on findings the triager rejected;
advice that only the owner may apply waits as a question."""
from __future__ import annotations

import json
from typing import Optional

from orch.conductor import checks as checks_mod, contract, prompts, questions as questions_mod
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


def advise(self, item: Item, number: int, ref: str, problem: str, evidence: list) -> Optional[dict]:
    """One advice round: the advisor role reads ``problem`` and the local ``evidence`` (and may ask the research
    sources) and answers a closed ``advice``, kept as ``advice-<n>.json`` in the artifacts of the piece. The agent run
    names the problem as its ``causation``. ``None`` when the advisor failed: an advice is help, never a reason for a
    piece to stop, so the problem goes on as it would without one."""
    from orch import research as research_mod
    sources = [source.id for source in research_mod.sources_from(self.settings)]
    key, role = f"advice.{number}", "advisor"
    route = item.routes[role]

    def run() -> dict:
        command = ""
        if sources:
            query_file = item.directory / "advice" / f"query-{number}.txt"
            query_file.parent.mkdir(parents=True, exist_ok=True)
            query_file.write_text(problem + "\n", encoding="utf-8")
            command = self._research_command(sources, query_file)
        prompt = prompts.advisor(item.input_doc, item=item.ref, step=key, problem_ref=ref, problem=problem,
                                 evidence=evidence, sources=sources, command=command, roles_dir=self.roles_dir,
                                 skills=self._skills(item, role), repo_rules=self._repo_rules(item, role),
                                 skill_texts=self._skill_texts(item, role))
        doc, meta = self._role(item, key, role, prompt, "advice", extra=lambda found: contract.advice_problems(ref, found),
                               causation=ref)
        saved = self._write_artifact(item, f"advice-{number}.json", doc)
        return {"advice": doc, "file": self._relative(saved), **meta}

    try:
        return self._step(item, key, run, role=role, route=self.label(route),
                          verdict=lambda result: f"{result['advice']['recommendation']} "
                                                 f"({result['advice']['confidence']})")
    except Stop as stop:
        self.progress.emit("info", item=item.ref, stage=key, reason_code="ADVISOR_FAILED",
                           message=f"{stop.code}: {stop.message}"[:300])
        return None


def reading(self, advice: dict) -> tuple:
    """``(recommended option, why the owner must decide or None)``: ``needs_owner`` or a category of
    ``orch.advisor.human_gate`` is never applied by the conductor."""
    option = next(entry for entry in advice["options"] if entry["id"] == advice["recommendation"])
    if advice["needs_owner"]:
        return option, "the advisor says only the owner can decide"
    if advice.get("category") in (self._advisor_cfg().get("human_gate") or []):
        return option, f"category {advice['category']} is held by orch.advisor.human_gate"
    return option, None


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
    options of the advice), saved with the advice like any queued question; ``conduct.py answer`` and ``resume --retry``
    then apply the owner's choice."""
    store = self._questions(item)
    asked = {"id": f"orch-advice-{number}", "revision": 1, "kind": "decision", "text": problem, "blocking": True,
             "options": [{"id": option["id"], "label": option["text"][:200]} for option in advice["options"]]}
    binding = {"run": self.run_id, "item": item.ref, "step": f"advice.{number}",
               "input_digest": item.input_doc.get("digest")}
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
        item, ("candidate", "Report of the executor", json.dumps(report, ensure_ascii=False, indent=2), "json")))
    if found is None:
        return False
    advice = found["advice"]
    option, held = self._reading(advice)
    ids = [row["id"] for row in entry.get("options") or []]
    if held is None and ids and option["id"] not in ids:
        held = f"the recommendation {option['id']} is not one of the options of the question"
    entry["advice"] = self._advice_summary(found["file"], advice, held)
    if held:
        return False
    entry["resolution"] = {"value": option["id"] if ids else option["text"], "by": "advisor", "at": clock.utc_now()}
    entry["status"], entry["auto_answered"] = "applied", True
    self.progress.emit("info", item=item.ref, stage=key, reason_code="QUESTION_ADVISED",
                       message=f"question {entry['id']} answered by the advisor with {option['id']} ({found['file']})")
    return True


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
    option, held = self._reading(advice)
    by = "advisor"
    if held:
        entry = self._hold(item, number, advice, found["file"], held, problem)
        chosen = self._owner_choice(advice, entry)
        if chosen is None:
            return {"held": f"{entry['id']} {entry['text']}{self._advice_note(entry)}"}
        option, by = chosen
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
    option, held = self._reading(advice)
    by = "advisor"
    if held:
        entry = self._hold(item, slot, advice, found["file"], held, problem)
        chosen = self._owner_choice(advice, entry)
        if chosen is None:
            return triage, f"{entry['id']} {entry['text']}{self._advice_note(entry)}"
        option, by = chosen
    return self._triage(item, number, findings, advice=prompts.advice_for_triage(advice, option, by=by)), None
