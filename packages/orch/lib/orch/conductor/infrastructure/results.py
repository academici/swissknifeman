"""The result of a role: its closed block taken from the answer and mended by rule, and the repair of a block outside
its contract by the report-fixer role from the role's own answer."""
from __future__ import annotations

from aicore.util.digest import sha256_hex

from orch.conductor import contract, heal, process, prompts
from orch.conductor.domain.item import Item
from orch.conductor.domain import semantics
from orch.conductor.domain.report import json_block
from orch.conductor.domain.route import label


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


def repair(self, item: Item, key: str, kind: str, extra, answer: str, issues: list, doc, healed, original=None) -> tuple:
    """The report-fixer rewrites the result block from the role's own answer; ``(doc, healed, issues, route,
    from_text)``. The repair keeps the meaning of the role's own block (I9): a block of the fixer that raises the status
    or the verdict, lowers a severity or loses a finding, question, escalation or check row against the mend of
    ``original`` is refused (``REPAIR_SEMANTIC_DRIFT``) and the next repair, then a repeat of the role, follows. An
    answer with no block that parses (``original`` None) has nothing to compare: the fixer's block is taken and said
    (``from_text``)."""
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
            run = process.run_role(self._role_argv(item, "report-fixer", route), prompt, transport=route["transport"],
                                   cwd=self.project, timeout_s=route["timeout_s"], raw_path=raw,
                                   env=self._role_env(item, "report-fixer", route), agent_directory=handle["directory"])
            self._tokens(item, run.usage, usage_complete=run.usage_complete, attempt=self._relative(raw))
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
