"""The result of a role: its closed block taken from the answer and mended by rule, the repair of a block outside
its contract by the report-fixer role from the role's own answer, and the isolation the stream of the role showed."""
from __future__ import annotations

import json
import re

from typing import Optional

from aicore.util.digest import sha256_hex

from orch.conductor import contract, heal, process, prompts
from orch.conductor.domain.item import Item
from orch.conductor.domain import semantics
from orch.conductor.domain.report import json_block
from orch.conductor.domain.route import label
from orch.conductor.policies import isolation as isolation_rules
from orch.conductor.policies.routing import exact_reviewer


def observe_denials(handle: dict, counts: dict) -> None:
    """Accumulate categories across attempts; agent_end emits one beacon for the completed step."""
    if counts:
        total = handle.setdefault("env_denials", {})
        for kind, number in counts.items():
            total[kind] = total.get(kind, 0) + number


def denial_beacons(handle: dict) -> list:
    """Emit once per role/step, including multiple report-fixer agents nested in the same step.

    Each agent keeps only its own persisted counts. Nested agents defer their beacon to the enclosing step,
    which combines the counts without duplicating them in the observer's agent results.
    """
    rows = handle.setdefault("step_env_denials", {})
    if handle.get("env_denials"):
        key = (handle["role"], handle["step"])
        counts = rows.setdefault(key, {})
        for kind, number in handle["env_denials"].items():
            counts[kind] = counts.get(kind, 0) + number
    parent = handle.get("previous")
    if parent is not None:
        pending = parent.setdefault("step_env_denials", {})
        for key, counts in rows.items():
            total = pending.setdefault(key, {})
            for kind, number in counts.items():
                total[kind] = total.get(kind, 0) + number
        return []
    return [(role, step, counts) for (role, step), counts in sorted(rows.items())]


def observe_isolation(self, item: Item, key: str, role: str, route: dict, init: Optional[dict], handle: dict) -> None:
    """What the first init event of the stream of an isolated role showed (``result.json`` ``isolation.observed``). A
    field its profile keeps empty (``observe.empty``) that is not is ``ISOLATION_DRIFT`` (info, the call goes on), and
    the provider is lowered for the run (``state.isolation_noted`` ``<provider>:ISOLATION_DRIFT``): under ``require`` its
    next role is refused (``ISOLATION_UNAVAILABLE``)."""
    instructions = (item.options or {}).get("instructions") or {}
    if init is None or role not in (instructions.get("isolate_roles") or ()) \
            or instructions.get("isolation", "prefer") == "off":
        return
    provider = route.get("provider") or ""
    handle["isolation"] = {"observed": init}
    found = isolation_rules.drift(isolation_rules.load_profiles(isolation_rules.PROFILES_PATH).get(provider), init)
    if not found:
        return
    mark = f"{provider}:ISOLATION_DRIFT"
    with self.store.mutating():
        noted = self.state.setdefault("isolation_noted", [])
        if mark not in noted:
            noted.append(mark)
            self._save()
    for field, names in found:
        self.progress.emit("info", item=item.ref, stage=key, role=role, route=label(route), reason_code="ISOLATION_DRIFT",
                           message=f"{role}/{provider} loaded {field} [{', '.join(names)}] although isolated")


def closed(text: str, kind: str, extra) -> tuple:
    """``(document, healed, issues, original)`` of the result block in ``text``: ``original`` is the block as the role
    wrote it, before the mend (None when the answer has no block that parses)."""
    original, error = json_block(text, kind)
    if error:
        return None, [], [error], None
    doc, healed = heal.heal(kind, original or {})
    if kind == "stage-report" and healed:
        doc = dict(doc, open_issues=list(doc.get("open_issues") or []) + [
            {"text": ("the conductor mended the form of this report: " + "; ".join(healed))[:900], "kind": "note",
             "impact": "none", "next": "none"}])
    issues = contract.problems(doc, kind)
    if not issues and extra:
        issues = extra(doc)
    return doc, healed, issues, original


def green_prose(text: str) -> Optional[dict]:
    """Normalize a declared GREEN with empty findings/questions, retaining all explanatory text."""
    sections = re.split(r"(?m)^## ([^\n]+)\s*\n", text.strip())
    if sections[0].strip() or len(sections) != 9:
        return None
    names = [name.strip().lower().replace("review-findings", "review findings") for name in sections[1::2]]
    expected = {"review findings", "questions", "material residual risk", "verdict"}
    if set(names) != expected or len(set(names)) != 4:
        return None
    bodies = {name: body.strip() for name, body in zip(names, sections[2::2])}
    if not re.fullmatch(r"(?:no findings|none)\.", bodies["review findings"], re.I):
        return None
    if not re.fullmatch(r"none\.", bodies["questions"], re.I):
        return None
    verdict = re.fullmatch(r"(?:\*\*)?`?GREEN`?(?:\*\*)?(?:\s*\n(.*))?", bodies["verdict"], re.I | re.S)
    if verdict is None or not bodies["material residual risk"]:
        return None
    # Prose accompanying the verdict is evidence too; retain it verbatim, ahead of the risk.
    context = (verdict.group(1) or "").strip()
    risk = "\n\n".join(part for part in (context, bodies["material residual risk"]) if part)
    return {"verdict": "GREEN", "findings": [], "questions": [], "residual_risk": risk}


def completed_error_review(events: list, extra) -> Optional[dict]:
    """Recover a completed reviewer response followed by a transient provider error, without hiding the error."""
    raw = []
    try:
        for event in events:
            if event.get("type") == "agy.raw":
                raw.append(json.loads(event["line"]))
        terminal = [event.get("result", {}) for event in raw if event.get("event") == "result"]
        if len(terminal) != 1 or terminal[0].get("status") != "ERROR":
            return None
        error, response = terminal[0].get("error", ""), terminal[0].get("response", "")
        if not isinstance(error, str) or "UNAVAILABLE (code 503)" not in error or not isinstance(response, str):
            return None
        session = terminal[0].get("conversation_id")
        if not isinstance(session, str) or not session:
            return None
        updates = [event.get("step_update", {}) for event in raw if event.get("event") == "step_update"]
        completed = [step for step in updates if step.get("conversation_id") == session
                     and step.get("step_type") == "agent_response" and step.get("state") == "DONE"]
        if not completed:
            return None
        index = completed[-1].get("step_index")
        pieces = [step.get("text_delta", "") for step in updates if step.get("conversation_id") == session
                  and step.get("step_type") == "agent_response" and step.get("step_index") == index]
        final = "".join(pieces)
        if not final or not response.endswith(final):
            return None
        document, _healed, issues, original = closed(final, "review-findings", extra)
        if issues or original is None or document != original:
            return None
        return {"findings": document, "session": session, "provider_error": error}
    except (KeyError, TypeError, ValueError):
        return None


def repair(self, item: Item, key: str, kind: str, extra, answer: str, issues: list, doc, healed, original=None) -> tuple:
    """The report-fixer rewrites the result block from the role's own answer; ``(doc, healed, issues, route,
    from_text)``. The repair keeps the meaning of the role's own block (I9): a block of the fixer that raises the status
    or the verdict, lowers a severity or loses a finding, question, escalation or check row against the mend of
    ``original`` is refused (``REPAIR_SEMANTIC_DRIFT``) and the next repair, then a repeat of the role, follows. An
    answer with no block that parses (``original`` None) has nothing to compare: the fixer's block is taken and said
    (``from_text``)."""
    if original is None and exact_reviewer(item.options, item.sources, item.input_doc):
        return doc, healed, issues, None, False
    if item.options["limits"]["repairs"] <= 0 or "report-fixer" not in item.routes:
        return doc, healed, issues, None, False
    route = item.routes["report-fixer"]
    if self.role_ports.provider_disabled(route["provider"]) or not process.available(route["argv"]):
        return doc, healed, issues, None, False
    baseline = heal.heal(kind, original)[0] if original is not None else None
    for number in range(1, item.options["limits"]["repairs"] + 1):
        self.role_ports.admit_budget(item, "attempt")  # a repair is a provider call too: none starts past a hard limit (I10)
        problem = "; ".join(issues[:5])
        prompt = prompts.render(prompts.report_fixer(kind=kind, problem=problem, answer=answer, item=item.ref, step=key))
        raw = item.directory / "streams" / f"{key}-fix{number}.jsonl"
        prompt_file = item.directory / "prompts" / f"{key}-fix{number}.md"
        prompt_file.write_text(prompt, encoding="utf-8")
        handle = self._agent_start(item, key, "report-fixer", route, prompt_file, number,
                                  prompt_sha256=sha256_hex(prompt.encode("utf-8")))  # the parent is the role mended
        try:
            run = self._launch(item, handle, "report-fixer", route, prompt, attempt=number, raw=raw,
                               timeout_s=route["timeout_s"])
            self._tokens(item, run.usage, usage_complete=run.usage_complete, attempt=self._relative(raw),
                         accounting=run.usage_accounting)
            observe_isolation(self, item, key, "report-fixer", route, run.init, handle)
            handle.update(last_exit=run.exit, stream=self._relative(raw), lingered=run.lingered)
        except BaseException as error:
            self._agent_end(handle, {"code": type(error).__name__, "message": str(error)[:300] or type(error).__name__})
            raise
        self._agent_end(handle, {"code": run.error, "message": run.detail or run.error} if run.error else None)
        if run.error:
            self.progress.emit("info", item=item.ref, stage=key, role="report-fixer", route=label(route),
                               reason_code="REPAIR_FAILED", message=f"{run.error}: {run.detail}")
            return doc, healed, issues, None, False
        fixed, fixed_healed, fixed_issues, _written = self._closed(run.text, kind, extra)
        if not fixed_issues and baseline is not None:
            found = semantics.drift(kind, baseline, fixed)
            if found:
                self.progress.emit("info", item=item.ref, stage=key, role="report-fixer", route=label(route),
                                   reason_code="REPAIR_SEMANTIC_DRIFT",
                                   message=f"kept the role's answer: {'; '.join(found[:2])}")
                issues = [f"REPAIR_SEMANTIC_DRIFT: {'; '.join(found[:3])}"]
                continue
        self.progress.emit("info", item=item.ref, stage=key, role="report-fixer", route=label(route),
                           reason_code="RESULT_REPAIRED" if not fixed_issues else "REPAIR_FAILED",
                           message=f"was: {problem}" + (f"; still: {'; '.join(fixed_issues[:2])}" if fixed_issues else ""))
        if not fixed_issues:
            from_text = baseline is None
            note = [f"repaired by {label(route)}: {problem}"[:300]]
            if from_text:
                note.append("the answer had no block to compare; the fixer's block is taken as it came")
            return fixed, healed + fixed_healed + note, [], label(route), from_text
        issues = fixed_issues
    return doc, healed, issues, None, False
