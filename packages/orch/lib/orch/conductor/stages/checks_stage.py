"""The acceptance checks of a round: run (beside the review with ``checks.overlap_review``) and corrected while they
stay red and the corrections make progress."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import threading
from typing import Optional

from orch.conductor import checks as checks_mod, process, prompts
from orch.conductor.domain.item import Item, done_steps
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import disk
from orch.conductor.progress import human_duration


def red_signature(rows: list) -> tuple:
    """The red checks of a round and how many failure lines their tails show (a correction that mends some of
    the tests of a red check is progress too)."""
    red = [row for row in rows if not row["green"] and not row.get("skipped")]
    failures = sum(len(re.findall(r"^(?:FAIL|ERROR|FAILED|not ok)\b", row.get("tail") or "", re.M)) for row in red)
    return tuple(sorted(row["id"] for row in red)), failures


def green(self, item: Item, rows: list, report: dict, round_no: int, scout_text: str,
          review_no: Optional[int] = None) -> tuple:
    """Correct red checks, within the ``check_fixes`` target or past it while the red checks change; otherwise
    the piece of work is blocked. With ``review_no`` (``checks.overlap_review``) the checks of a correction run
    while review ``review_no`` reads it."""
    state, earlier = item.state, None
    while not all(row["green"] for row in rows):
        red = [row for row in rows if not row["green"] and not row.get("skipped")]
        signature = self._red_signature(rows)
        progress = earlier is not None and (signature[0] != earlier[0] or signature[1] < earlier[1])
        earlier = signature
        replayed = round_no in state["check_fixes_at"]
        done_before = len([number for number in state["check_fixes_at"] if number != round_no])
        why = None if replayed else self._allowance(item, "check_fixes", done_before, progress)
        advised = None
        if why:
            advised = None if why.startswith("batch:") else self._advise_red(item, round_no, red, report)
            if advised and advised.get("held"):  # the owner decides; the question waits with the advice
                return rows, self._blocked(report, "QUESTION", advised["held"]), round_no
            if not advised:
                names = ", ".join(row["id"] for row in red)
                return rows, self._blocked(report, "CHECKS_RED", f"acceptance checks {names} stay red after "
                                                                 f"{done_before} correction(s): {why}"), round_no
        if not replayed:
            state["check_fixes_at"].append(round_no)
        if advised:  # kept: a replay of this round (resume --retry) must get the same advice, not only the red text
            state.setdefault("advice_fix", {})[str(round_no)] = advised["text"]
        state["check_fixes_used"] = len(state["check_fixes_at"])
        kept_advice = (state.get("advice_fix") or {}).get(str(round_no)) if replayed else None
        round_no += 1
        text, combined = prompts.check_correction(red), state.get("combined")
        if advised:  # the allowance is spent; the advice makes one more round
            text = advised["text"]
        elif kept_advice:
            text = kept_advice
        if combined:  # the finished review's confirmed findings are corrected in this one round, and only in it
            text += "\n\n" + combined["text"]
            if combined["review"] not in state.setdefault("combined_done", []):
                state["combined_done"].append(combined["review"])
            if combined["review"] not in state["corrections_at"]:
                state["corrections_at"].append(combined["review"])
            state["corrections_used"] = len(state["corrections_at"])
            state.pop("combined")
            self._save()
        report = self._execute(item, round_no, scout_text, text)
        if report["status"] == "blocked":
            return rows, report, round_no
        rows = (self._checks_then_review(item, report, round_no, review_no) if review_no is not None
                else self._run_checks(item, round_no, report))
    return rows, report, round_no


def red_before(item: Item, number: int) -> list:
    """The checks that were red in the latest earlier round, when ``checks.red_first`` asks to run them first."""
    if not item.options["checks"]["red_first"]:
        return []
    steps = done_steps(item.state.get("steps", {}))
    for earlier in range(number - 1, 0, -1):
        rows = (steps.get(f"checks.{earlier}") or {}).get("result")
        if rows:
            return [row["id"] for row in rows if not row.get("green") and not row.get("skipped")]
    return []


def compute_checks(self, item: Item, number: int, report: dict, on_result=None) -> list:
    """The rows of the checks of one round; touches no run state, so it may run beside a model role."""
    self._disk_guard(item, f"checks.{number}")  # a heavy check that fills the disk dies with a truncated trace
    try:
        return checks_mod.run_checks(
            item.input_doc, project=self.project, evidence_dir=self._evidence_dir(item),
            log_dir=item.directory / "checks" / str(number),
            timeout_s=item.options["limits"]["check_timeout_s"],
            evidence_prefix=f"{self.run_id}:{item.ref}:checks.{number}", report=report,
            executor=self._actor(item.routes["executor"]), parallel=item.options["checks"]["parallel"],
            on_result=on_result, first=self._red_before(item, number), kinds=tuple(item.options["checks"]["kinds"]),
            cadence=tuple(item.options["checks"]["cadence"]), warn_s=item.options["limits"].get("check_warn_s", 0),
            on_slow=lambda check_id, elapsed, pid: self._check_tick(item, number, check_id, elapsed, pid),
            idle_s=item.options["limits"].get("check_idle_timeout_s", 0),
            on_changed=lambda paths: self.progress.emit(
                "info", item=item.ref, stage=f"checks.{number}", reason_code="CHECK_CHANGED_TREE",
                message=f"the checks changed {len(paths)} file(s) of the project: {', '.join(paths[:5])}"
                        f"{' …' if len(paths) > 5 else ''}; the evidence proves the candidate before them"))
    except (RuntimeError, ValueError, OSError) as error:
        raise Stop("CHECKS_FAILED", str(error)) from None


def check_tick(self, item: Item, number: int, check_id: str, elapsed: float, pid: int) -> None:
    self.progress.emit("info", item=item.ref, stage=f"checks.{number}", reason_code="CHECK_SLOW",
                       message=f"{check_id} running {human_duration(elapsed)}; {process.activity(pid, Path(os.devnull))}")
    low = disk.shortage(self.project, item.options["limits"].get("disk_min_gb", 0))
    if low:  # the check is not cut (a stop from this thread could not release it); the owner decides
        self.progress.emit("info", item=item.ref, stage=f"checks.{number}", reason_code="DISK_LOW", message=low)
    self._run_clock(item, stop=False)


def run_checks(self, item: Item, number: int, report: dict, computed=None) -> list:
    """The step ``checks.N``; ``computed`` is a future of the rows started earlier (the overlap with the review)."""
    key = f"checks.{number}"

    def run() -> list:
        return computed.result() if computed is not None else self._compute_checks(item, number, report)

    def said(rows: list) -> str:
        red = [row["id"] for row in rows if not row["green"]]
        return "green" if not red else "red " + ",".join(red)

    return self._step(item, key, run, verdict=said)


def checks_then_review(self, item: Item, report: dict, checks_no: int, review_no: int) -> list:
    """With ``checks.overlap_review`` the checks of a round run while the review of that candidate reads it. When the
    checks are red the review read a candidate that is about to change: its step is dropped and made again later."""
    steps = item.state.setdefault("steps", {})
    if steps.get(f"checks.{checks_no}", {}).get("status") == "done" \
            or steps.get(f"review.{review_no}", {}).get("status") == "done":
        return self._run_checks(item, checks_no, report)
    cancel = threading.Event()  # a red check ends the review at once: it reads a candidate that is about to change
    self._start_step(item, f"checks.{checks_no}")
    with ThreadPoolExecutor(max_workers=1) as pool:
        computed = pool.submit(self._compute_checks, item, checks_no, report,
                               lambda row: None if row.get("green") else cancel.set())
        try:
            self._review(item, review_no, [], pending=True, cancel=cancel)
        except Stop as stop:
            if stop.code != "REVIEW_CANCELLED":
                if computed.exception() is None:  # the checks ran to the end: keep them for the resume
                    self._run_checks(item, checks_no, report, computed=computed)
                raise
        finally:
            computed.exception()  # wait for the checks before the pool closes, whatever the review did
    rows = self._run_checks(item, checks_no, report, computed=computed)
    if not all(row["green"] for row in rows):
        if steps.get(f"review.{review_no}", {}).get("status") == "done":
            self._carry_review(item, review_no)
        else:
            steps.pop(f"review.{review_no}", None)
            self.progress.emit("info", item=item.ref, message="the checks are red: the parallel review is dropped "
                                                               "and repeated after the correction")
    return rows


def carry_review(self, item: Item, review_no: int) -> None:
    """The review finished before the red checks: keep it. Its confirmed findings at the floor go into the same
    correction as the red checks (one executor round, not two), and the next audit is the pre-final one."""
    review = done_steps(item.state.get("steps", {})).get(f"review.{review_no}")
    if review is None:
        return
    findings = review["result"]["findings"]
    major = []
    if findings["findings"]:
        triage = self._triage(item, review_no, findings)
        major, minor = self._split_confirmed(item, findings, triage)
        self._defer_minor(item, findings, minor)
        if major:
            item.state["combined"] = {"review": review_no,
                                      "text": prompts.review_correction(findings, dict(triage, confirmed=major))}
    self.progress.emit("info", item=item.ref, message=f"the checks are red but review {review_no} is done: its "
                                                      f"{len(major)} finding(s) to correct go into the same correction")
