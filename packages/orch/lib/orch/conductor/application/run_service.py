"""The verbs of a conductor run: ``run``, ``resume`` (with ``--retry`` of a blocked piece), ``release`` and ``settle``."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from orch import settings as settings_mod
from orch.conductor.domain.report import continued
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock
from orch.conductor.infrastructure.files import RunStore
from orch.worksource import WorkSourceError
from orch.worksource_file import read_input


def run(self, *, plan: Optional[str], plans_root: Optional[str], items: list, batch: bool, max_items: int,
        options_file: Optional[Path] = None, adopt: bool = False, input_file: Optional[Path] = None,
        commit: bool = False, scenario: Optional[str] = None,
        fence: Optional[str] = None, extra_paths: Optional[list] = None,
        grouped: Optional[bool] = None) -> int:
    """Conduct the pieces of a plan, or with ``input_file`` the one piece of an execution-input document (the built-in
    file source: no plan; ``scenario`` is then the scenario of the run, ``commit`` lets it commit its paths)."""
    run_id = clock.new_run_id()
    source = None
    if input_file is not None:
        try:
            found = read_input(input_file)
        except WorkSourceError as error:
            raise Stop(error.code, error.message) from None
        plan, plans_root, items, batch = str(Path(input_file).resolve()), None, [found["input_id"]], False
        source = {"kind": "file", "path": plan, "commit": bool(commit)}
    run_doc = {"run_id": run_id, "plan": plan, "plans_root": plans_root, "items": list(items), "batch": batch,
               "source": source, "scenario": scenario if source else None,
               "max_items": max_items, "options_file": str(options_file) if options_file else None,
               "adopt": bool(adopt), "grouped": grouped, "fence": fence,
               "extra_paths": [str(path) for path in extra_paths or []] or None,
               "config_file": str(self.config_file) if self.config_file else None, "created": clock.utc_now(),
               "project": str(self.project), "project_resolution": self.project_resolution,
               "working_directory": os.getcwd(), "config_digest": settings_mod.config_digest(self.settings),
               "config_layers": settings_mod.config_layers(self.settings)}
    self._open(run_id, run_doc, {"status": "running", "items": {}, "claims": {}, "tokens": {"input": 0, "output": 0}})
    self.store.create(run_doc)
    if options_file:
        self.store.keep_options(options_file)
    self._save()
    self.progress.emit("run.start", message=f"plan {plan}; " + (f"items {', '.join(items)}" if items else
                                                                 f"batch, at most {max_items or 'all'}"))
    return self._loop()


def resume(self, run_id: str, retry=()) -> int:
    store = RunStore(self.project, run_id)
    run_doc, state = store.load()
    if run_doc.get("config_file") and not self.config_file:
        self.config_file = Path(run_doc["config_file"])
    self._open(run_id, run_doc, state, store)
    for ref in retry:
        self._retry(ref)
    state["status"] = "running"
    state["resumes"] = state.get("resumes", 0) + 1
    self._save()
    self.progress.emit("run.resume", message=f"resume {state['resumes']}")
    return self._loop()


def retry(self, ref: str) -> None:
    """Take a blocked piece back into the run: the input is built again from the (amended) plan, and the steps from the executor round that reported ``blocked`` on
    (and the closing steps after it) are repeated; the earlier rounds are kept and the work in the tree is not thrown away."""
    item = self.state["items"].get(ref)
    if not item or item.get("outcome") != "blocked":
        raise Stop("RETRY_NOT_BLOCKED", f"{ref} is not a blocked piece of this run")
    steps = item.get("steps", {})
    # the state file is sorted by key, so the order of the steps is the order of their ``ended`` stamps
    blocked = min((key for key in steps if key.startswith("executor.") and key not in continued(steps) and
                   (((steps[key].get("result") or {}).get("report") or {}).get("status") == "blocked")),
                  key=lambda key: steps[key].get("ended", ""), default=None)
    held = any(name.startswith("orch-advice-") for name in (self.state.get("questions") or {}).get(ref, {}))
    if blocked is None and not held:
        raise Stop("RETRY_NOT_BLOCKED", f"{ref} has no executor round that reported blocked")
    # the input is built again too: the plan was amended (that is why the piece was blocked and reopened), and the
    # executor must see the amended write set, not the one of the first brief. A piece held on advice (red checks or a
    # rejected finding, the question ``orch-advice-<n>`` waits for the owner) reported no blocked round: its closed rounds,
    # checks, reviews and advice stay and only the opening and closing steps are repeated.
    since = steps[blocked].get("ended", "") if blocked else None
    for key in [key for key in steps if key == blocked or key in ("brief", "prepare", "scout", "close", "register", "commit")
                or (since is not None and steps[key].get("ended", "") > since)]:
        steps.pop(key)
    for key in ("outcome", "stop", "partial", "skills_auto", "skills_checked"):  # the skills are chosen again from the amended write set
        item.pop(key, None)
    self._save()
    self.progress.emit("info", item=ref, message=f"retry: the steps from {blocked} on are repeated" if blocked
                       else "retry: the answer to the advice is applied; the closed rounds are kept")


def work_began(state: dict) -> bool:
    """An executor round ran: the piece has this run's work in the tree and is no longer free to give back. Changes
    adopted from an earlier attempt do not count: they stay in the tree, and a later ``run --adopt`` takes them again."""
    return bool(state.get("executor_started")) or any(key.startswith("executor.") for key in state.get("steps", {}))


def batch_held(self) -> bool:
    """The pieces of this run are one batch (several pieces, ``--batch`` unless ``--no-batch``): they are in progress
    together, so a stop gives none of them back on its own (a stop is resumable; ``release`` is the hand that frees)."""
    return self.run_doc.get("grouped") is not False and len(self.run_doc.get("items") or []) > 1


def release(self, run_id: str, ref: str, reason: str) -> int:
    """Give a piece of this run back to the work source by hand, when a run died or stopped before any work began
    (an executor round makes it refuse: settle or retry the piece instead)."""
    store = RunStore(self.project, run_id)
    run_doc, state = store.load()
    item = state.get("items", {}).get(ref)
    if item is None:
        raise Stop("ITEM_UNKNOWN", f"{ref} is not a piece of run {run_id}")
    if self._work_began(item) or item.get("outcome") in ("done", "done_with_deviations"):
        raise Stop("RELEASE_WORK_BEGAN", f"{ref} has work in the tree or is closed; settle it, or resume with --retry")
    self._open(run_id, run_doc, state, store)
    if not self._release_claim(ref, item, reason):
        raise Stop("RELEASE_REFUSED", f"the work source did not release {ref}; see the progress line")
    return 0


def settle(self, run_id: str, ref: str, outcome: str, reason: str) -> int:
    """Set the outcome of a piece of this run by hand, after the owner or an observer finished it outside the
    conductor (committed it with the work source's own command, or gave it up). Nothing else changes: the work
    source keeps its own record; a resume then treats the piece as closed."""
    store = RunStore(self.project, run_id)
    run_doc, state = store.load()
    if ref not in state.get("items", {}):
        raise Stop("ITEM_UNKNOWN", f"{ref} is not a piece of run {run_id}")
    self._open(run_id, run_doc, state, store)
    item = state["items"][ref]
    before = item.get("outcome")
    item["outcome"] = outcome
    item.pop("stop", None)
    item.pop("partial", None)
    item.setdefault("settled", []).append({"from": before, "to": outcome, "reason": reason, "at": clock.utc_now()})
    self._save()
    self.progress.emit("info", item=ref, reason_code="SETTLED", outcome=outcome, message=f"outcome {before or '-'} → {outcome} by hand: {reason}")
    return 0
