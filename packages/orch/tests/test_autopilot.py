"""The autopilot without a child conductor (PLAN9 P8.5): the policy and its layers, ``classify_outcome`` on every branch of steps
6-7 and of the PLAN9 practice, ``choose_next``, the requests, ``status`` and ``explain``, the records, and the scenarios h-j, l-n,
r-t and u of knowledge/p8-design#p8-autopilot on the fake work source answers and a controlled clock. The child conductors are
fake runs written into the runs root (journal, state, lease); the real processes are in ``test_autopilot_faults.py``.
"""
from __future__ import annotations

import contextlib
import functools
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from aicore.config import ConfigError
from aicore.ext import events as journal
from aicore.util import timefmt
from aicore.util.lock import FileLock

from orch import settings
from orch.conductor import autopilot_cli, cli, contract, process, progress, questions, records
from orch.conductor.application import autopilot, autopilot_status
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import detach
from orch.conductor.infrastructure.files import RunStore, runs_root
from orch.conductor.infrastructure.lease import RunLease
from orch.conductor.policies import autopilot as rules

NOW = timefmt.epoch("2026-11-01T10:00:00Z")
POLICY = dict(rules.DEFAULTS, allowed=True, enabled=True, run_tokens_hard_max=0, poll_s=1.0)
DIGEST = "sha256:" + "a" * 64


def layers(**by_layer) -> dict:
    """``Settings.autopilot`` of the given layers: ``layers(machine={"allowed": True}, project={"max_runs": 5})``."""
    found = {key: [{"layer": "defaults", "value": value}] for key, value in rules.DEFAULTS.items()}
    for layer in ("machine", "project", "env", "invocation", "flags"):
        for key, value in (by_layer.get(layer) or {}).items():
            found[key].append({"layer": layer, "value": value})
    return found


def ready(phase: str = "P1", status: str = "ready", items=("W1",), kind: str = "run-items", phases=None) -> dict:
    return {"op": "readiness", "outcome": "ok",
            "phases": phases if phases is not None else [{"id": phase, "status": status, "digest": DIGEST}],
            "next": {"kind": kind, "items": list(items) if kind == "run-items" else [], "phase": phase, "message": None}}


class Clock:
    """Controlled time: ``sleep`` moves it and runs the hooks the test gave (a request, an answer, a finished child)."""

    def __init__(self, now: float = NOW):
        self.t = now
        self.hooks: list = []
        self.sleeps = 0

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds
        self.sleeps += 1
        if self.sleeps > 500:
            raise AssertionError("the controller loops without end")
        for hook in list(self.hooks):
            hook(self)


class Launcher:
    """Fake children: each launch writes a run of its outcome into the runs root. An outcome is a dict: ``status``
    (finished, waiting, stopped, running), ``closed``, ``blocked`` ({item: code}), ``waiting`` ({item: [question ids]}),
    ``stop`` ({code, message}), ``lines`` (more journal lines), ``group_reviews``, ``refuse`` (a Stop of the acknowledgement),
    ``corrupt`` (``json`` or ``schema``: the state.json of the run is damaged). ``deaf``: a running child ignores SIGINT;
    ``interrupt_problem``: the identity check refuses the signal."""

    def __init__(self, case, outcomes=()):
        self.case, self.outcomes, self.started, self.interrupted, self.leases = case, list(outcomes), [], [], {}
        self.readiness_at: list = []
        self.deaf, self.interrupt_problem = False, None

    def start(self, current: dict) -> dict:
        on_disk = records.read(self.case.root / autopilot.STATE_DOC, "autopilot-state")["current"]
        self.case.assertEqual(on_disk, current, "the launch intent is on disk before the child starts")
        self.case.assertEqual("launching", on_disk["state"])
        self.started.append(dict(current))
        self.readiness_at.append(getattr(getattr(self.case, "readiness", None), "call_count", None))
        outcome = self.outcomes.pop(0) if self.outcomes else {"status": "finished", "closed": current.get("items") or []}
        current["_outcome"] = outcome
        if not outcome.get("refuse"):
            self.case.write_run(current["run_id"], current, outcome)
            if outcome["status"] == "running":
                self.leases[current["run_id"]] = RunLease(self.case.root / current["run_id"]).acquire("run")
            if outcome.get("corrupt"):
                (self.case.root / current["run_id"] / "state.json").write_text(
                    "{not json" if outcome["corrupt"] == "json" else json.dumps({"status": 5}), encoding="utf-8")
        return {"pid": 4000 + len(self.started), "start_ticks": 7, "log": "child.log"}

    def acknowledged(self, current: dict, child: dict) -> dict:
        refusal = current.pop("_outcome").get("refuse")
        if refusal:
            raise Stop(*refusal)
        return {"status": "started"}

    def ack_of(self, current: dict):
        return {"pid": 4242, "start_ticks": 7} if any(row["launch_id"] == current["launch_id"] for row in self.started) else None

    def alive(self, child: dict) -> bool:
        return True

    def finish(self, run_id: str, outcome: dict) -> None:
        """A running fake child ends with ``outcome``."""
        self.leases.pop(run_id).release()
        self.case.end_run(run_id, outcome)

    def interrupt(self, directory: Path, current: dict):
        self.interrupted.append(current["run_id"])
        if self.interrupt_problem:
            return self.interrupt_problem
        if current["run_id"] in self.leases and not self.deaf:
            self.finish(current["run_id"], {"status": "stopped", "stop": {"code": "INTERRUPTED", "message": "interrupted"}})
        return None


class Case(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        base = Path(temporary.name).resolve()
        self.home, self.project = base / "home", base / "project"
        (self.home / "skm" / "config").mkdir(parents=True)
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True, capture_output=True)
        env = {"HOME": str(self.home), "SKM_HOME": str(self.home / "skm"), "SKM_AICORE_EVENTS__DELIVERY": "off",
               "SKM_CONTRACTS_STRICT": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ("SKM_ORCH_DETACHED", "SKM_ORCH_DETACH_ACK", "SKM_ORCH_DETACH_NONCE", autopilot.CRASH_ENV,
                     detach.STATE_ENV, detach.LAUNCH_ENV, detach.GATE_ENV):
            os.environ.pop(name, None)
        self.root = runs_root(self.project)
        self.clock = Clock()
        self.answers: list = []
        self.dirty = False

    folders_seen = None

    def dirty_of(self, folders=()) -> bool:
        self.folders_seen = folders
        return self.dirty

    def settings(self, **by_layer) -> SimpleNamespace:
        by_layer.setdefault("machine", {"allowed": True, "poll_s": 1})
        by_layer.setdefault("project", {"enabled": True})
        return SimpleNamespace(autopilot=layers(**by_layer), supervisor={}, events_enabled=False)

    def controller(self, readiness=None, outcomes=(), flags=None, **by_layer) -> autopilot.Controller:
        self.launcher = Launcher(self, outcomes)
        self.readiness = mock.Mock(side_effect=readiness if callable(readiness) else lambda: readiness or ready())
        return autopilot.Controller(self.project, "T", self.settings(**by_layer), flags=flags, clock=self.clock,
                                    launcher=self.launcher, readiness=self.readiness, dirty=self.dirty_of,
                                    say=lambda text: None)

    def start(self, controller) -> tuple:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = controller.start()
        return code, err.getvalue(), self.state()

    def state(self) -> dict:
        return records.read(self.root / autopilot.STATE_DOC, "autopilot-state")

    # ------------------------------------------------------------------------------------------------ fake runs

    def write_run(self, run_id: str, current: dict, outcome: dict) -> None:
        store = RunStore(self.project, run_id)
        directory = store.directory
        if current["kind"] == "run":
            store.create({"run_id": run_id, "items": current.get("items") or [], "lease": True})
            store.save({"status": "running", "items": {}})
            progress.Progress(run_id, directory, "quiet").emit("run.start")
        else:
            progress.Progress(run_id, directory, "quiet").emit("run.resume", message="resume")
        if outcome["status"] != "running":
            self.end_run(run_id, outcome)

    def end_run(self, run_id: str, outcome: dict) -> None:
        store = RunStore(self.project, run_id)
        _, state = store.load()
        line = progress.Progress(run_id, store.directory, "quiet")
        items = state.setdefault("items", {})
        brief = ({"brief": {"status": "done", "ended": "2026-11-01T10:00:00Z", "role": "deterministic",
                            "result": {"artifacts_dir": outcome["brief"], "input_path": "input.json", "input_id": "T.W1",
                                       "base": "0" * 40}}} if outcome.get("brief") else {})
        for ref in outcome.get("closed", []):
            items[ref] = {"steps": dict(brief), "outcome": "done"}
            line.emit("item.end", item=ref, outcome="done")
        for ref, code in (outcome.get("blocked") or {}).items():
            items[ref] = {"steps": outcome.get("steps", {}), "outcome": "blocked"}
            line.emit("item.end", item=ref, outcome="blocked", reason_code=code, message=f"{code}: blocked")
        for ref, ids in (outcome.get("waiting") or {}).items():
            items[ref] = {"steps": {key: dict(value, result=dict(value["result"], artifacts_dir=value["result"]["artifacts_dir"]
                                                             .replace("{ref}", ref))) for key, value in brief.items()},
                          "outcome": "blocked",
                          "waiting": {"question_ids": ids, "since": "2026-11-01T10:00:00Z"}}
            folder = store.directory / ref
            folder.mkdir(exist_ok=True)
            records.write(folder / questions.FILE, {"run": run_id, "item": ref, "questions": [
                {"id": name, "revision": 1, "kind": "decision", "text": "keep it?", "blocking": True, "status": "open",
                 "asked_at": "2026-11-01T10:00:00Z",
                 "binding": {"input_digest": "3f" * 32, "input_part_digest": "3f" * 32, "item": ref, "run": run_id,
                             "step": "executor.1"}} for name in ids]}, "questions")
        for extra in outcome.get("lines", []):
            line.emit("info", **extra)
        if outcome.get("group_reviews"):
            state["group_reviews"] = outcome["group_reviews"]
        stop = outcome.get("stop")
        state["status"] = outcome["status"]
        if stop:
            state["stop"] = stop
        store.save(state)
        line.emit("run.end", outcome=outcome["status"], reason_code=(stop or {}).get("code"),
                  message=(stop or {}).get("message", "done"))

    def answer(self, run_id: str, ref: str, question: str = "q1") -> None:
        questions.answer_file(self.root / run_id / ref, question, item=ref, option=None, text="keep it", by="owner",
                              now="2026-11-01T10:05:00Z")

    def request(self, action: str) -> None:
        records.write(self.root / autopilot.REQUEST_DOC, {"action": action, "at": "2026-11-01T10:00:00Z", "by": "test"},
                      "autopilot-request")


class PolicyTests(unittest.TestCase):
    def test_allowed_comes_only_from_the_machine_and_a_flag_or_a_project_can_only_narrow(self):
        policy, sources = rules.effective_policy(layers(machine={"allowed": False}, project={"allowed": True, "enabled": True}))
        self.assertEqual((False, "machine", True, "project"),
                         (policy["allowed"], sources["allowed"], policy["enabled"], sources["enabled"]))
        policy, sources = rules.effective_policy(layers(machine={"allowed": True, "max_runs": 8}, project={"max_runs": 50}),
                                                 {"max_runs": 3, "max_wall_s": 99999})
        self.assertEqual((3, "flag:--max-runs"), (policy["max_runs"], sources["max_runs"]))
        self.assertEqual((43200, "defaults"), (policy["max_wall_s"], sources["max_wall_s"]), "a flag cannot widen")
        policy, sources = rules.effective_policy(layers(machine={"max_runs": 8}, project={"max_runs": 5}))
        self.assertEqual((5, "project"), (policy["max_runs"], sources["max_runs"]))

    def test_require_readiness_is_on_when_any_layer_turns_it_on(self):
        for machine, project, expected in ((False, None, False), (False, True, True), (True, False, True), (None, False, True)):
            with self.subTest(machine=machine, project=project):
                given = {"machine": {} if machine is None else {"require_readiness": machine},
                         "project": {} if project is None else {"require_readiness": project}}
                self.assertEqual(expected, rules.effective_policy(layers(**given))[0]["require_readiness"])

    def test_monotony_no_project_value_widens_any_key(self):
        """Every key: whatever a project sets, the policy is never weaker than the machine's alone."""
        machine = {"allowed": False, "require_readiness": True, "max_runs": 7, "max_wall_s": 100, "max_no_progress_runs": 2,
                   "max_auto_decisions": 3, "quota_wait_max_s": 60, "max_recoveries": 1}
        alone = rules.effective_policy(layers(machine=machine))[0]
        wide = {"allowed": True, "require_readiness": False, "max_runs": 999, "max_wall_s": 99999, "max_no_progress_runs": 99,
                "max_auto_decisions": 99, "quota_wait_max_s": 99999, "max_recoveries": 9}
        for key, value in wide.items():
            for layer in ("project", "env", "invocation"):
                with self.subTest(key=key, layer=layer):
                    found = rules.effective_policy(layers(machine=machine, **{layer: {key: value}}))[0]
                    self.assertEqual(alone[key], found[key])
        narrow = rules.effective_policy(layers(machine=machine, project={"max_runs": 2, "max_recoveries": 0}))[0]
        self.assertEqual((2, 0), (narrow["max_runs"], narrow["max_recoveries"]))

    def test_settings_keep_the_history_of_each_layer_and_a_project_cannot_set_allowed(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            (base / "skm" / "config").mkdir(parents=True)
            (base / "project" / ".swissknifeman").mkdir(parents=True)
            (base / "skm" / "config" / "config.toml").write_text(
                "schema_version = 1\n[orch.autopilot]\nallowed = true\nmax_runs = 8\n", encoding="utf-8")
            (base / "project" / ".swissknifeman" / "config.toml").write_text(
                "schema_version = 1\n[orch.autopilot]\nenabled = true\nmax_runs = 50\n", encoding="utf-8")
            env = {"HOME": str(base), "SKM_HOME": str(base / "skm")}
            with mock.patch.dict(os.environ, env):
                found = settings.load(project=base / "project", env=env, home=base).autopilot
                self.assertEqual(["defaults", "machine", "project"], [row["layer"] for row in found["max_runs"]])
                policy, sources = rules.effective_policy(found)
                self.assertEqual((True, True, 8, "machine"), (policy["allowed"], policy["enabled"], policy["max_runs"],
                                                              sources["max_runs"]))
                (base / "project" / ".swissknifeman" / "config.toml").write_text(
                    "schema_version = 1\n[orch.autopilot]\nallowed = true\n", encoding="utf-8")
                with self.assertRaises(ConfigError) as caught:
                    settings.load(project=base / "project", env=env, home=base)
                self.assertEqual("CONFIG_LAYER_FORBIDDEN", caught.exception.code)


class ClassifyTests(unittest.TestCase):
    def classify(self, exit_code, history=None, policy=None, **status):
        status.setdefault("run_id", "cnd-r")
        return rules.classify_outcome(exit_code, status, history or {"counters": {}}, policy or POLICY)

    def test_step_6_exit_0(self):
        self.assertEqual("AUTOPILOT_NO_WORK", self.classify(0, items=[])["code"])
        self.assertEqual({"action": "continue", "no_progress_streak": 0, "blocker": None},
                         self.classify(0, items=["W1"], closed=["W1"]))
        self.assertEqual(1, self.classify(0, items=["W1"])["no_progress_streak"])
        self.assertEqual("AUTOPILOT_NO_PROGRESS", self.classify(0, {"counters": {"no_progress_streak": 1}}, items=["W1"])["code"])

    def test_step_6_exit_4_waits_with_a_clean_tree_and_needs_the_owner_with_changes(self):
        waiting = [{"item": "W1", "question_ids": ["q1"]}]
        self.assertEqual({"action": "waiting", "items": ["W1"]}, self.classify(4, waiting=waiting))
        found = self.classify(4, waiting=waiting, dirty=True)
        self.assertEqual("AUTOPILOT_OWNER_NEEDED", found["code"])
        self.assertIn("W1 (q1)", found["message"])
        self.assertEqual("AUTOPILOT_OWNER_NEEDED", self.classify(4, {"counters": {}, "waiting_runs": 2}, waiting=waiting)["code"])

    def test_step_6_exit_1(self):
        quota = {"code": "PROVIDER_QUOTA", "message": "the limit resets 2026-11-01T11:00:00Z"}
        self.assertEqual({"action": "wait_quota", "wait_s": 61}, self.classify(1, stop=quota, quota_reset_in_s=60))
        self.assertEqual("AUTOPILOT_QUOTA", self.classify(1, stop=quota, quota_reset_in_s=999999)["code"])
        self.assertEqual("AUTOPILOT_QUOTA", self.classify(1, stop=quota, quota_reset_in_s=None)["code"])
        self.assertEqual("AUTOPILOT_BUDGET", self.classify(1, stop={"code": "TOKEN_BUDGET"})["code"])
        self.assertEqual("AUTOPILOT_BUDGET", self.classify(1, stop={"code": "TOKEN_BUDGET_UNMETERED"})["code"])
        for code in ("RUN_BUSY", "WORKTREE_BUSY"):
            self.assertEqual("AUTOPILOT_CHECKOUT_LOST", self.classify(1, stop={"code": code})["code"])
        self.assertEqual("AUTOPILOT_STATE_INVALID", self.classify(1, stop={"code": "STATE_CORRUPT"})["code"])
        found = self.classify(1, stop={"code": "SANDBOX_UNAVAILABLE", "message": "no bwrap"})
        self.assertEqual(("AUTOPILOT_RUN_STOPPED", True), (found["code"], "SANDBOX_UNAVAILABLE" in found["message"]))
        self.assertEqual("AUTOPILOT_INTERRUPTED", self.classify(130)["code"])
        self.assertEqual("AUTOPILOT_RUN_STOPPED", self.classify(2)["code"])

    def test_blockers_continue_once_and_stop_the_second_time_in_a_row(self):
        blocked = [{"item": "W1", "code": "CHECKS_RED"}]
        first = self.classify(1, stop={"code": "CHECKS_RED"}, blocked=blocked)
        self.assertEqual({"action": "continue", "blocker": blocked[0]}, first)
        history = {"counters": {}, "last_blockers": [{"item": "W1", "code": "CHECKS_RED", "at": "x"}]}
        self.assertEqual("AUTOPILOT_REPEATED_BLOCKER", self.classify(1, history, stop={"code": "CHECKS_RED"}, blocked=blocked)["code"])
        other = {"counters": {}, "last_blockers": [{"item": "W2", "code": "CHECKS_RED", "at": "x"}]}
        self.assertEqual("continue", self.classify(1, other, stop={"code": "CHECKS_RED"}, blocked=blocked)["action"])
        self.assertEqual("AUTOPILOT_OWNER_NEEDED", self.classify(1, stop={"code": "REVIEW_LIMIT"}, blocked=blocked, dirty=True)["code"])
        self.assertEqual("AUTOPILOT_REPEATED_BLOCKER", self.classify(0, history, items=["W1"], blocked=blocked)["code"])

    def test_plan9_practice_one_time_failures_resume_within_max_recoveries(self):
        for code in sorted(rules.TRANSIENT):
            with self.subTest(code=code):
                self.assertEqual({"action": "resume", "retry": [], "reason": code}, self.classify(1, stop={"code": code}))
                self.assertEqual("AUTOPILOT_RECOVERY_EXHAUSTED",
                                 self.classify(1, {"counters": {}, "recoveries": 1}, stop={"code": code})["code"])
        found = self.classify(1, stop={"code": "QUESTION_ANSWERED_NOT_RETRIED",
                                       "message": "answers of W2 wait: orch conduct resume --run cnd-r --retry W2"})
        self.assertEqual({"action": "resume", "retry": ["W2"], "reason": "QUESTION_ANSWERED_NOT_RETRIED"}, found)

    def test_plan9_practice_protected_paths_and_group_review_findings_need_the_owner(self):
        escalations = {"W1": ["WRITE_PROTECTED_PATH: .claude/x.md -> art/protected/.claude/x.md",
                              "WRITE_PROTECTED_PATH: .claude/y.md -> art/protected/.claude/y.md"]}
        found = self.classify(1, stop={"code": "ITEM_BLOCKED"}, blocked=[{"item": "W1", "code": "WRITE_PROTECTED_PATH"}],
                              escalations=escalations)
        self.assertEqual("AUTOPILOT_OWNER_NEEDED", found["code"])
        self.assertIn(".claude/x.md <- art/protected/.claude/x.md", found["message"])
        self.assertIn("--retry W1", found["message"])
        mixed = {"W1": escalations["W1"][:1] + ["SCOPE_EXPANSION: needs bridges/x"]}
        self.assertEqual("continue", self.classify(1, stop={"code": "ITEM_BLOCKED"}, escalations=mixed,
                                                   blocked=[{"item": "W1", "code": "SCOPE_EXPANSION"}])["action"])
        followups = [{"group": "1", "followup": ".swissknifeman/x/group-review-1.followup.json", "counts": {"Blocker": 0, "Major": 2}}]
        found = self.classify(0, items=["W1"], closed=["W1"], group_followups=followups)
        self.assertEqual("AUTOPILOT_OWNER_NEEDED", found["code"])
        self.assertIn("orch conduct run --input .swissknifeman/x/group-review-1.followup.json --commit", found["message"])

    def test_step_7_decisions(self):
        policy = dict(POLICY, max_auto_decisions=2)
        self.assertEqual("AUTOPILOT_DECISIONS_EXCEEDED",
                         self.classify(0, {"counters": {"auto_decisions": 2}}, policy, items=["W1"], closed=["W1"],
                                       auto_decisions=1)["code"])
        self.assertEqual("continue", self.classify(0, {"counters": {"auto_decisions": 1}}, policy, items=["W1"], closed=["W1"],
                                                   auto_decisions=1)["action"])

    def test_exit_codes_of_the_stop_codes(self):
        self.assertEqual({0}, {rules.exit_code(code) for code in rules.FINE})
        self.assertEqual({1}, {rules.exit_code(code) for code in rules.CODES if code not in rules.FINE})
        self.assertEqual(25, len(rules.CODES))


class ChooseNextTests(unittest.TestCase):
    def test_an_answered_waiting_run_comes_first_and_needs_no_readiness(self):
        self.assertEqual({"action": "continue", "run_id": "cnd-a"}, rules.choose_next("cnd-a", 1, None, POLICY))

    def test_readiness_of_exactly_the_phase_of_the_lane(self):
        phases = [{"id": "P0", "status": "stale", "digest": DIGEST}, {"id": "P2", "status": "not_ready", "digest": DIGEST},
                  {"id": "P1", "status": "ready_with_advisories", "digest": DIGEST}]
        found = rules.choose_next(None, 0, ready("P1", phases=phases), POLICY)  # (l) and (m): other phases do not matter
        self.assertEqual({"action": "run", "items": ["W1"], "phase": "P1"}, found)
        for status in ("not_ready", "stale", "missing"):
            with self.subTest(status=status):  # (n)
                found = rules.choose_next(None, 0, ready("P1", status), POLICY)
                self.assertEqual("AUTOPILOT_NOT_READY", found["code"])
                self.assertIn(f"READINESS_{status.upper()}", found["message"])
        self.assertEqual("run", rules.choose_next(None, 0, ready("P1", "stale"), dict(POLICY, require_readiness=False))["action"])
        self.assertIn("READINESS_PHASE_UNKNOWN", rules.choose_next(None, 0, ready(None, phases=[]), POLICY)["message"])

    def test_no_lane(self):
        self.assertEqual("AUTOPILOT_NO_WORK", rules.choose_next(None, 0, ready(kind="terminal"), POLICY)["code"])
        found = rules.choose_next(None, 0, ready(kind="audit-phase"), POLICY)
        self.assertEqual(("AUTOPILOT_NOT_READY", True), (found["code"], found["message"].startswith("NEXT_AUDIT_PHASE")))
        self.assertEqual({"action": "wait_answers"}, rules.choose_next(None, 1, ready(kind="waiting"), POLICY))
        refused = {"op": "readiness", "outcome": "refused", "reason_code": "READINESS_UNSUPPORTED", "message": "no op"}
        self.assertIn("READINESS_UNSUPPORTED", rules.choose_next(None, 0, refused, POLICY)["message"])


class ControllerTests(Case):
    def test_phase_restart_does_not_start_another_lane_while_waiting(self):
        controller = self.controller(outcomes=[{"status": "waiting", "waiting": {"W1": ["q1"]}}])
        controller.phase = "P1"
        _, _, state = self.start(controller)
        run_id = state["waiting_runs"][0]["run_id"]
        restarted = self.controller(ready(items=("W2",)))
        restarted.phase = "P1"
        code, _, state = self.start(restarted)
        self.assertEqual((1, "AUTOPILOT_PHASE_WAITING", run_id),
                         (code, state["stop"]["code"], state["waiting_runs"][0]["run_id"]))
        self.assertEqual([], self.launcher.started)
        result = autopilot_status.explain(self.project, "T", self.settings(), readiness=lambda: ready(items=("W2",)))
        self.assertEqual("AUTOPILOT_PHASE_WAITING", result["next"]["code"])

    def test_phase_switch_discards_only_finished_waiting_runs(self):
        for condition in ("finished", "waiting", "leased", "running", "stopped", "unknown", "lease_unknown", "missing", "invalid"):
            with self.subTest(condition=condition):
                (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                controller = self.controller(outcomes=[{"status": "waiting", "waiting": {"W1": ["q1"]}}])
                controller.phase = "P1"
                _, _, state = self.start(controller)
                run_id = state["waiting_runs"][0]["run_id"]
                store = RunStore(self.project, run_id)
                if condition in ("finished", "leased", "running", "stopped", "unknown", "lease_unknown"):
                    _, run_state = store.load()
                    run_state["items"]["W1"] = {"steps": {}, "outcome": "done"}
                    run_state["status"] = condition if condition in ("running", "stopped", "unknown") else "finished"
                    store.save(run_state)
                lease = RunLease(store.directory).acquire("run") if condition == "leased" else None
                if condition == "missing":
                    (store.directory / "state.json").unlink()
                if condition == "invalid":
                    (store.directory / "state.json").write_text("{invalid", encoding="utf-8")
                try:
                    other = self.controller(ready("P2", items=("W2",)) if condition != "finished" else
                                            ready("P2", kind="terminal"))
                    other.phase = "P2"
                    with mock.patch.object(RunLease, "held", return_value=None) if condition == "lease_unknown" else contextlib.nullcontext():
                        code, err, state = self.start(other)
                    if condition == "finished":
                        self.assertEqual((0, "P2", [], "AUTOPILOT_PHASE_COMPLETE"),
                                         (code, state["phase"], state["waiting_runs"], state["stop"]["code"]))
                    else:
                        self.assertEqual(1, code)
                        self.assertIn("AUTOPILOT_PHASE_CONFLICT", err)
                        self.assertEqual(run_id, state["waiting_runs"][0]["run_id"])
                    self.assertEqual([], self.launcher.started)
                finally:
                    if lease:
                        lease.release()

    def test_explain_answered_phase_run_reports_other_blocked_piece(self):
        controller = self.controller(outcomes=[{"status": "waiting", "waiting": {"W1": ["q1"]},
                                                "blocked": {"W2": "ITEM_BLOCKED"}}])
        controller.phase = "P1"
        _, _, state = self.start(controller)
        self.assertEqual("AUTOPILOT_PHASE_BLOCKED", state["stop"]["code"])
        self.answer(state["waiting_runs"][0]["run_id"], "W1")
        result = autopilot_status.explain(self.project, "T", self.settings(), readiness=lambda: ready())
        self.assertEqual("AUTOPILOT_PHASE_BLOCKED", result["next"]["code"])
        self.assertIn("W2 blocked (ITEM_BLOCKED)", result["next"]["message"])
        restarted = self.controller(ready())
        restarted.phase = "P1"
        code, _, state = self.start(restarted)
        self.assertEqual((1, result["next"]["code"]), (code, state["stop"]["code"]))
        self.assertEqual([], self.launcher.started)

    def test_phase_halt_retains_settled_waiting_run_on_recovery(self):
        for number, cause in enumerate(("deadline", "stop")):
            with self.subTest(cause=cause):
                (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                controller = self.controller()
                controller.phase = "P1"
                prior = controller._session(None)
                run_id = f"cnd-20261101T095000Z-aaaaa{number}"
                current = {"run_id": run_id, "launch_id": "0123456789abcdef", "state": "running", "kind": "run",
                           "since": timefmt.utc_stamp(NOW - 60), "items": ["W1"]}
                self.write_run(run_id, current, {"status": "waiting", "waiting": {"W1": ["q1"]}})
                prior["current"] = current
                if cause == "deadline":
                    prior["deadline_at"] = timefmt.utc_stamp(NOW - 1)
                else:
                    self.request("stop")
                records.write(self.root / autopilot.STATE_DOC, prior, "autopilot-state")
                _, _, state = self.start(controller)
                self.assertEqual("AUTOPILOT_MAX_WALL" if cause == "deadline" else "AUTOPILOT_STOPPED", state["stop"]["code"])
                self.assertIsNone(state["current"])
                self.assertEqual([run_id], [row["run_id"] for row in state["waiting_runs"]])
                other = self.controller(ready("P2"))
                other.phase = "P2"
                code, err, _ = self.start(other)
                self.assertEqual(1, code)
                self.assertIn("AUTOPILOT_PHASE_CONFLICT", err)
                self.assertEqual([], self.launcher.started)

    def test_explain_phase_answered_waiting_checks_readiness(self):
        controller = self.controller(outcomes=[{"status": "waiting", "waiting": {"W1": ["q1"]}}])
        controller.phase = "P1"
        _, _, state = self.start(controller)
        self.answer(state["waiting_runs"][0]["run_id"], "W1")
        for status in ("stale", "ready"):
            with self.subTest(status=status):
                readiness = ready(status=status)
                result = autopilot_status.explain(self.project, "T", self.settings(), readiness=lambda: readiness)
                self.assertEqual(readiness, result["readiness"])
                self.assertEqual("AUTOPILOT_NOT_READY" if status == "stale" else "continue",
                                 result["next"].get("code") or result["next"]["action"])

    def test_phase_answered_run_rechecks_readiness_and_keeps_pending(self):
        waiting = {"status": "waiting", "waiting": {"W1": ["q1"]}}
        controller = self.controller(ready(), outcomes=[waiting])
        controller.phase = "P1"
        _, _, state = self.start(controller)
        run_id = state["waiting_runs"][0]["run_id"]
        self.answer(run_id, "W1")
        restarted = self.controller(ready(status="stale"))
        restarted.phase = "P1"
        code, _, state = self.start(restarted)
        self.assertEqual((1, "AUTOPILOT_NOT_READY", run_id), (code, state["stop"]["code"], state["current"]["run_id"]))
        self.assertEqual(run_id, state["waiting_runs"][0]["run_id"])
        self.assertEqual([], self.launcher.started)

    def test_phase_resume_rechecks_readiness_and_blocked(self):
        for stop in ("ROLE_FAILED", "PROVIDER_QUOTA"):
            for blocked in (False, True):
                with self.subTest(stop=stop, blocked=blocked):
                    (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                    outcome = {"status": "stopped", "stop": {"code": stop, "message": f"resets {timefmt.utc_stamp(NOW + 1)}"},
                               "blocked": {"W1": "ITEM_BLOCKED"} if blocked else {}}
                    answers = iter([ready(), ready(status="stale")])
                    controller = self.controller(lambda: next(answers), outcomes=[outcome])
                    controller.phase = "P1"
                    code, _, state = self.start(controller)
                    self.assertEqual((1, "AUTOPILOT_PHASE_BLOCKED" if blocked else "AUTOPILOT_NOT_READY"),
                                     (code, state["stop"]["code"]))
                    self.assertEqual(1, len(self.launcher.started))

    def test_phase_dirty_waiting_run_preserves_boundary(self):
        self.dirty = True
        controller = self.controller(outcomes=[{"status": "waiting", "waiting": {"W1": ["q1"]}}])
        controller.phase = "P1"
        _, _, state = self.start(controller)
        self.assertEqual("AUTOPILOT_OWNER_NEEDED", state["stop"]["code"])
        self.assertEqual(1, len(state["waiting_runs"]))
        self.dirty = False
        other = self.controller(ready("P2"))
        other.phase = "P2"
        code, err, state = self.start(other)
        self.assertEqual(1, code)
        self.assertIn("AUTOPILOT_PHASE_CONFLICT", err)
        self.assertEqual("P1", state["phase"])

    def test_phase_recovery_and_relaunch_fail_closed_on_missing_readiness(self):
        for look in ("orphaned", "relaunch"):
            with self.subTest(look=look):
                controller = self.controller(ready(phases=[]))
                controller.phase = "P1"
                controller.doc = controller._session(None)
                run_id = "cnd-20261101T095000Z-aaaaaa"
                current = {"run_id": run_id, "launch_id": "abcdabcdabcdabcd", "state": "launching", "kind": "resume",
                           "since": "2026-11-01T10:00:00Z", "boot_id": process.boot_id()}
                controller.doc["current"] = current
                controller.recover_run = mock.Mock(return_value=None)
                with mock.patch.object(controller, "view", return_value=({"blocked": []}, 1)), \
                        contextlib.redirect_stderr(io.StringIO()):
                    code = controller._recover(current, look) if look == "orphaned" else controller._intent_end(current, look)
                self.assertEqual((1, "AUTOPILOT_NOT_READY", run_id),
                                 (code, controller.doc["stop"]["code"], controller.doc["current"]["run_id"]))
                self.assertEqual([], self.launcher.started)

    def test_phase_boundary_stops_before_successor_even_if_readiness_disabled(self):
        answers = iter([ready(), ready("P2", items=("W2",))])
        controller = self.controller(lambda: next(answers), machine={"allowed": True, "require_readiness": False})
        controller.phase = "P1"
        code, _, state = self.start(controller)
        self.assertEqual((1, "AUTOPILOT_PHASE_BOUNDARY", "P1"), (code, state["stop"]["code"], state["phase"]))
        self.assertEqual([["W1"]], [row["items"] for row in self.launcher.started])

    def test_phase_waiting_and_blocked_do_not_select_successor(self):
        for outcome, expected in (({"status": "waiting", "waiting": {"W1": ["q1"]}}, "AUTOPILOT_PHASE_WAITING"),
                                  ({"status": "finished", "blocked": {"W1": "ITEM_BLOCKED"}}, "AUTOPILOT_PHASE_BLOCKED")):
            with self.subTest(expected=expected):
                (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                controller = self.controller(ready(), outcomes=[outcome])
                controller.phase = "P1"
                code, _, state = self.start(controller)
                self.assertEqual((1, expected), (code, state["stop"]["code"]))
                self.assertEqual(1, self.readiness.call_count)
                self.assertEqual(1, len(self.launcher.started))

    def test_phase_persists_on_recovery_and_conflict_is_refused(self):
        controller = self.controller(ready("P2"))
        controller.phase = "P1"
        prior = controller._session(None)
        records.write(self.root / autopilot.STATE_DOC, prior, "autopilot-state")
        conflict = self.controller(ready())
        conflict.phase = "P2"
        code, _, state = self.start(conflict)
        self.assertEqual(1, code)
        self.assertEqual(prior, state)
        recovered = self.controller(ready("P2"), machine={"allowed": True, "require_readiness": False})
        code, _, state = self.start(recovered)
        self.assertEqual((1, "P1", "AUTOPILOT_PHASE_BOUNDARY"), (code, state["phase"], state["stop"]["code"]))
        self.assertEqual([], self.launcher.started)

    def test_phase_terminal_and_missing_phase_fail_closed(self):
        for answer, expected, exit_code in ((ready(kind="terminal"), "AUTOPILOT_PHASE_COMPLETE", 0),
                                            (ready(phase=None), "AUTOPILOT_PHASE_BOUNDARY", 1),
                                            (ready(kind="waiting"), "AUTOPILOT_PHASE_WAITING", 1)):
            with self.subTest(expected=expected):
                (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                controller = self.controller(answer)
                controller.phase = "P1"
                code, _, state = self.start(controller)
                self.assertEqual((exit_code, expected), (code, state["stop"]["code"]))
                self.assertEqual([], self.launcher.started)

    def test_cli_passes_phase_to_controller_and_detach(self):
        args = ["--project", str(self.project), "autopilot", "start", "--plan", "T", "--phase", "P1"]
        with mock.patch.object(autopilot_cli, "_settings", return_value=(self.settings(), "")), \
                mock.patch.object(autopilot, "Controller") as cls:
            cls.return_value.start.return_value = 0
            self.assertEqual(0, cli.main(args))
            self.assertEqual("P1", cls.call_args.kwargs["phase"])
        with mock.patch.object(detach, "launch", return_value=0) as launch:
            self.assertEqual(0, cli.main(args + ["--detach"]))
            self.assertIn("--phase", launch.call_args.args[0])

    def test_cli_runs_controller_and_refuses_successor(self):
        args = ["--project", str(self.project), "autopilot", "start", "--plan", "T", "--phase", "P1"]
        with mock.patch.object(autopilot_cli, "_settings", return_value=(self.settings(), "")), \
                mock.patch.object(autopilot, "source_readiness", return_value=ready("P2")), \
                mock.patch.object(autopilot, "ProcessLauncher") as launcher, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(1, cli.main(args))
            launcher.return_value.start.assert_not_called()
        self.assertEqual("AUTOPILOT_PHASE_BOUNDARY", self.state()["stop"]["code"])

    def test_phase_restart_keeps_quota_wait(self):
        controller = self.controller()
        controller.phase = "P1"
        prior = controller._session(None)
        prior["stop"] = {"code": "AUTOPILOT_MAX_WALL", "message": "deadline", "at": "2026-11-01T10:00:00Z"}
        prior["quota_wait"] = {"run_id": "cnd-20261101T095000Z-aaaaaa", "until": "2026-11-01T10:05:00Z"}
        records.write(self.root / autopilot.STATE_DOC, prior, "autopilot-state")
        restarted = self.controller()
        restarted.phase = "P1"
        self.assertEqual(prior["quota_wait"], restarted._session(prior)["quota_wait"])

    def test_h_a_project_that_allows_itself_is_ignored_and_the_machine_refuses(self):
        (self.project / ".swissknifeman").mkdir()
        (self.project / ".swissknifeman" / "config.toml").write_text(
            "schema_version = 1\n[orch.autopilot]\nallowed = true\nenabled = true\n", encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = cli.main(["--project", str(self.project), "autopilot", "start", "--plan", "T"])
        self.assertEqual(1, code, err.getvalue())
        self.assertIn("AUTOPILOT_NOT_ALLOWED: ", err.getvalue())
        self.assertIn("CONFIG_LAYER_FORBIDDEN", err.getvalue())
        state = self.state()
        self.assertEqual(("stopped", "AUTOPILOT_NOT_ALLOWED", None), (state["mode"], state["stop"]["code"], state["current"]))
        sent = [event.data for event in journal.read_events(self.project)[0] if event.type == "orch.autopilot.stopped"]
        self.assertEqual([{"plan": "T", "code": "AUTOPILOT_NOT_ALLOWED", "runs": 0, "items_closed": 0}],
                         [{key: value for key, value in data.items() if key != "message"} for data in sent])

    def test_disabled(self):
        code, err, state = self.start(self.controller(project={}))
        self.assertEqual((1, "AUTOPILOT_DISABLED"), (code, state["stop"]["code"]))
        self.assertEqual([], self.launcher.started)

    def test_i_not_ready_or_stale_starts_no_run(self):
        for status in ("not_ready", "stale"):
            with self.subTest(status=status):
                (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                code, err, state = self.start(self.controller(ready("P1", status)))
                self.assertEqual((1, "AUTOPILOT_NOT_READY"), (code, state["stop"]["code"]))
                self.assertIn("AUTOPILOT_NOT_READY: READINESS_", err)
                self.assertEqual([], self.launcher.started)
        refused = {"op": "readiness", "outcome": "refused", "reason_code": "READINESS_UNSUPPORTED", "message": "no op"}
        code, _, state = self.start(self.controller(refused))
        self.assertIn("READINESS_UNSUPPORTED", state["stop"]["message"])

    def test_j_a_done_plan_is_no_work_and_another_next_step_is_not_ready(self):
        code, err, state = self.start(self.controller(ready(kind="terminal")))
        self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]))
        code, err, state = self.start(self.controller(ready(kind="audit-phase")))
        self.assertEqual((1, "AUTOPILOT_NOT_READY"), (code, state["stop"]["code"]))
        self.assertTrue(state["stop"]["message"].startswith("NEXT_AUDIT_PHASE"))

    def test_l_m_finished_and_unrelated_phases_are_ignored_and_the_lane_runs(self):
        phases = [{"id": "P0", "status": "stale", "digest": DIGEST}, {"id": "P9", "status": "not_ready", "digest": DIGEST},
                  {"id": "P1", "status": "ready", "digest": DIGEST}]
        answers = iter([ready("P1", phases=phases, items=("W1", "W2")), ready(kind="terminal")])
        code, err, state = self.start(self.controller(lambda: next(answers), flags={"run_tokens_hard_max": 5000}))
        self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]), err)
        self.assertEqual([("run", ["W1", "W2"])], [(row["kind"], row["items"]) for row in self.launcher.started])
        self.assertEqual(({"run": 1}, 2), ({"run": state["counters"]["runs"]}, state["counters"]["items_closed"]))
        self.assertEqual(["finished"], [row["status"] for row in state["history"]])
        options = json.loads((self.root / autopilot.OPTIONS_DOC).read_text(encoding="utf-8"))
        self.assertEqual({"scope": {"outside": "block"}, "limits": {"run_tokens_hard_max": 5000}}, options)
        self.assertEqual([], contract.problems(options, "run-options"))

    def test_n_the_phase_of_the_lane_not_ready(self):
        phases = [{"id": "P0", "status": "ready", "digest": DIGEST}, {"id": "P1", "status": "not_ready", "digest": DIGEST}]
        code, _, state = self.start(self.controller(ready("P1", phases=phases)))
        self.assertEqual((1, "AUTOPILOT_NOT_READY", []), (code, state["stop"]["code"], self.launcher.started))

    def test_r_the_deadline_passes_in_a_healthy_run(self):
        controller = self.controller(outcomes=[{"status": "running"}], flags={"max_wall_s": 60})
        code, err, state = self.start(controller)
        self.assertEqual((0, "AUTOPILOT_MAX_WALL"), (code, state["stop"]["code"]), err)
        run_id = self.launcher.started[0]["run_id"]
        self.assertEqual([run_id], self.launcher.interrupted)
        self.assertEqual(("interrupted", 130, None), (state["history"][0]["status"], state["history"][0]["exit"], state["current"]))
        self.assertIn(f"orch conduct resume --run {run_id}", state["stop"]["message"])
        self.assertEqual(timefmt.utc_stamp(NOW + 60), state["deadline_at"])

    def test_s_the_deadline_passes_in_a_pause(self):
        self.request("pause")
        code, _, state = self.start(self.controller(flags={"max_wall_s": 30}))
        self.assertEqual((0, "AUTOPILOT_MAX_WALL", []), (code, state["stop"]["code"], self.launcher.started))
        self.assertEqual("stopped", state["mode"])

    def test_t_the_deadline_passes_while_waiting_for_a_quota(self):
        quota = {"status": "stopped", "stop": {"code": "PROVIDER_QUOTA",
                                               "message": f"the limit resets {timefmt.utc_stamp(NOW + 600)}, resume after it"}}
        code, err, state = self.start(self.controller(outcomes=[quota], flags={"max_wall_s": 120}))
        self.assertEqual((0, "AUTOPILOT_MAX_WALL"), (code, state["stop"]["code"]), err)
        self.assertEqual(1, len(self.launcher.started), "no resume before the reset")
        self.assertIsNotNone(state["quota_wait"])

    def test_t_a_restart_after_the_deadline_stops_at_once_and_does_not_move_it(self):
        self.root.mkdir(parents=True)
        prior = {"$schema": records.TAGS["autopilot-state"][1], "plan": "T", "project": str(self.project), "pid": 1,
                 "started_at": timefmt.utc_stamp(NOW - 7200), "updated_at": timefmt.utc_stamp(NOW - 10),
                 "deadline_at": timefmt.utc_stamp(NOW - 3600), "mode": "running",
                 "limits": {"max_runs": 20, "max_wall_s": 3600, "run_tokens_hard_max": 0, "max_no_progress_runs": 2,
                            "max_auto_decisions": 10, "quota_wait_max_s": 21600},
                 "counters": dict.fromkeys(autopilot.COUNTERS, 0), "current": None, "waiting_runs": [], "history": [],
                 "last_blockers": [], "stop": None}
        records.write(self.root / autopilot.STATE_DOC, prior, "autopilot-state")
        code, _, state = self.start(self.controller())
        self.assertEqual((0, "AUTOPILOT_MAX_WALL", [], prior["deadline_at"]),
                         (code, state["stop"]["code"], self.launcher.started, state["deadline_at"]))
        self.readiness.assert_not_called()

    def test_quota_wait_then_resume(self):
        quota = {"status": "stopped", "stop": {"code": "PROVIDER_QUOTA",
                                               "message": f"the limit resets {timefmt.utc_stamp(NOW + 5)}"}}
        answers = iter([ready(), ready(kind="terminal")])
        code, err, state = self.start(self.controller(lambda: next(answers), outcomes=[quota, {"status": "finished", "closed": ["W1"]}]))
        self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]), err)
        self.assertEqual(["run", "resume"], [row["kind"] for row in self.launcher.started])
        self.assertEqual(1, state["counters"]["quota_waits"])
        self.assertEqual(1, len(state["history"]), "one history entry per run")

    def test_u_an_answered_waiting_run_is_continued_once_before_any_readiness(self):
        for following in (ready(kind="waiting"), ready("P1", "stale", kind="audit-phase")):
            with self.subTest(next=following["next"]["kind"]):
                (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                answers = iter([ready(), following, ready(kind="terminal")])
                controller = self.controller(lambda answers=answers: next(answers), outcomes=[
                    {"status": "waiting", "waiting": {"W1": ["q1"]}, "stop": {"code": "WAITING_DECISION", "message": "q1"}},
                    {"status": "finished", "closed": ["W1"]}])
                calls: list = []

                def answered(clock, calls=calls):
                    state = records.read(self.root / autopilot.STATE_DOC, "autopilot-state")
                    if state["waiting_runs"] and not calls:
                        calls.append(self.readiness.call_count)
                        self.answer(state["waiting_runs"][0]["run_id"], "W1")
                self.clock.hooks = [answered]
                code, err, state = self.start(controller)
                self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]), err)
                kinds = [row["kind"] for row in self.launcher.started]
                self.assertEqual(["run", "continue"], kinds, "continued exactly once")
                self.assertEqual(self.launcher.started[0]["run_id"], self.launcher.started[1]["run_id"])
                self.assertEqual(calls, self.launcher.readiness_at[1:], "no readiness between the answer and the continue")
                self.assertNotIn("NEXT_", state["stop"]["message"])
                self.assertEqual([], state["waiting_runs"])

    def test_a_waiting_run_finished_by_hand_waits_no_longer(self):
        waiting = {"status": "waiting", "waiting": {"W1": ["q1"]}, "stop": {"code": "WAITING_DECISION", "message": "q1"}}
        answers = iter([ready()])
        controller = self.controller(lambda: next(answers, ready(kind="terminal")), outcomes=[waiting], flags={"max_wall_s": 600})

        def by_hand(clock):
            state = records.read(self.root / autopilot.STATE_DOC, "autopilot-state")
            if state["waiting_runs"]:
                store = RunStore(self.project, state["waiting_runs"][0]["run_id"])
                _, run_state = store.load()
                run_state["items"]["W1"] = {"steps": {}, "outcome": "done"}
                run_state["status"] = "finished"
                store.save(run_state)
        self.clock.hooks = [by_hand]
        code, _, state = self.start(controller)
        self.assertEqual((0, "AUTOPILOT_NO_WORK", []), (code, state["stop"]["code"], state["waiting_runs"]))

    def test_exit_4_with_changes_in_the_tree_needs_the_owner(self):
        self.dirty = True
        waiting = {"status": "waiting", "waiting": {"W1": ["q1"]}, "stop": {"code": "WAITING_DECISION", "message": "q1"}}
        code, _, state = self.start(self.controller(outcomes=[waiting]))
        self.assertEqual((1, "AUTOPILOT_OWNER_NEEDED"), (code, state["stop"]["code"]))
        self.assertIn("W1 (q1)", state["stop"]["message"])

    def test_max_runs_and_the_progress_of_the_counters(self):
        code, _, state = self.start(self.controller(flags={"max_runs": 2}, outcomes=[
            {"status": "finished", "closed": ["W1"]}, {"status": "finished", "closed": ["W2"]}]))
        self.assertEqual((0, "AUTOPILOT_MAX_RUNS", 2, 2), (code, state["stop"]["code"], state["counters"]["runs"],
                                                          state["counters"]["items_closed"]))

    def test_decisions_are_counted_from_question_advised_lines(self):
        advised = [{"reason_code": "QUESTION_ADVISED", "message": "advised"}] * 2
        code, _, state = self.start(self.controller(project={"enabled": True, "max_auto_decisions": 2}, outcomes=[
            {"status": "finished", "closed": ["W1"], "lines": advised}]))
        self.assertEqual((1, "AUTOPILOT_DECISIONS_EXCEEDED", 2), (code, state["stop"]["code"], state["counters"]["auto_decisions"]))

    def test_a_refused_child_is_classified_by_its_code(self):
        code, _, state = self.start(self.controller(outcomes=[{"refuse": ("WORKTREE_BUSY", "checkout driven by cnd-x")}]))
        self.assertEqual((1, "AUTOPILOT_CHECKOUT_LOST"), (code, state["stop"]["code"]))
        self.assertEqual(("never_started", "WORKTREE_BUSY"), (state["history"][0]["status"], state["history"][0]["reason_code"]))

    def test_a_one_time_failure_is_resumed_once_then_exhausted(self):
        crashed = {"status": "stopped", "stop": {"code": "ROLE_FAILED", "message": "exit 1"}}
        code, _, state = self.start(self.controller(outcomes=[crashed, crashed]))
        self.assertEqual((1, "AUTOPILOT_RECOVERY_EXHAUSTED"), (code, state["stop"]["code"]))
        self.assertEqual(["run", "resume"], [row["kind"] for row in self.launcher.started])
        self.assertEqual({self.launcher.started[0]["run_id"]: 1}, state["recoveries"])

    def test_a_repeated_blocker_stops(self):
        blocked = {"status": "stopped", "blocked": {"W1": "CHECKS_RED"}, "stop": {"code": "CHECKS_RED", "message": "red"}}
        code, _, state = self.start(self.controller(outcomes=[blocked, blocked]))
        self.assertEqual((1, "AUTOPILOT_REPEATED_BLOCKER"), (code, state["stop"]["code"]))
        self.assertEqual(1, len(state["last_blockers"]))

    def test_requests_drain_and_stop(self):
        controller = self.controller(outcomes=[{"status": "running"}])
        self.clock.hooks = [lambda clock: self.request("drain") if clock.sleeps == 1 else None,
                            lambda clock: self.launcher.finish(self.launcher.started[0]["run_id"],
                                                               {"status": "finished", "closed": ["W1"]})
                            if clock.sleeps == 2 else None]
        code, _, state = self.start(controller)
        self.assertEqual((0, "AUTOPILOT_DRAINED", 1), (code, state["stop"]["code"], len(self.launcher.started)))
        (self.root / autopilot.STATE_DOC).unlink()
        self.clock.hooks = [lambda clock: self.request("stop")]
        code, _, state = self.start(self.controller(outcomes=[{"status": "running"}]))
        self.assertEqual((0, "AUTOPILOT_STOPPED"), (code, state["stop"]["code"]))
        self.assertEqual([self.launcher.started[0]["run_id"]], self.launcher.interrupted)
        self.assertEqual("interrupted", state["history"][0]["status"])
        self.assertFalse((self.root / autopilot.REQUEST_DOC).exists())

    def test_pause_then_resume(self):
        self.request("pause")
        self.clock.hooks = [lambda clock: self.request("resume") if clock.sleeps == 3 else None]
        answers = iter([ready(), ready(kind="terminal")])
        code, _, state = self.start(self.controller(lambda: next(answers)))
        self.assertEqual((0, "AUTOPILOT_NO_WORK", 1), (code, state["stop"]["code"], len(self.launcher.started)))
        self.assertGreaterEqual(self.clock.sleeps, 3)

    def test_busy_writes_nothing(self):
        self.root.mkdir(parents=True)
        lock = FileLock(self.root / autopilot.LOCK_FILE)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)
        code, err, state = self.start(self.controller())
        self.assertEqual((1, None), (code, state))
        self.assertIn("AUTOPILOT_BUSY: ", err)

    def test_a_launch_intent_without_a_run_never_started_and_one_with_a_run_is_adopted(self):
        intent = {"run_id": "cnd-20261101T095900Z-aaaaaa", "launch_id": "0123456789abcdef", "state": "launching",
                  "kind": "run", "items": ["W1"], "since": timefmt.utc_stamp(NOW)}
        prior = {"$schema": records.TAGS["autopilot-state"][1], "plan": "T", "project": str(self.project), "pid": 1,
                 "started_at": timefmt.utc_stamp(NOW), "updated_at": timefmt.utc_stamp(NOW),
                 "deadline_at": timefmt.utc_stamp(NOW + 3600), "mode": "running",
                 "limits": {"max_runs": 20, "max_wall_s": 3600, "run_tokens_hard_max": 0, "max_no_progress_runs": 2,
                            "max_auto_decisions": 10, "quota_wait_max_s": 21600},
                 "counters": dict.fromkeys(autopilot.COUNTERS, 0), "current": intent, "waiting_runs": [], "history": [
                     {"run_id": intent["run_id"], "started_at": intent["since"], "ended_at": None, "exit": None,
                      "status": "running", "reason_code": None, "items_closed": []}], "last_blockers": [], "stop": None}
        records.write(self.root / autopilot.STATE_DOC, prior, "autopilot-state")
        code, _, state = self.start(self.controller(ready(kind="terminal")))
        self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]))
        self.assertEqual(["never_started"], [row["status"] for row in state["history"]])
        self.assertGreater(self.clock.t - NOW, autopilot.LAUNCH_GRACE_S)
        # the same intent with the run of the child in place: adopted, one history entry
        prior["current"] = dict(intent, since=timefmt.utc_stamp(self.clock.t))
        prior["history"][0]["status"] = "running"
        records.write(self.root / autopilot.STATE_DOC, prior, "autopilot-state")
        launcher = Launcher(self)
        launcher.started.append(prior["current"])
        self.write_run(intent["run_id"], prior["current"], {"status": "finished", "closed": ["W1"]})
        controller = autopilot.Controller(self.project, "T", self.settings(), clock=self.clock, launcher=launcher,
                                          readiness=lambda: ready(kind="terminal"), dirty=lambda folders=(): False, say=lambda text: None)
        code, _, state = self.start(controller)
        self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]))
        self.assertEqual([(intent["run_id"], "finished")], [(row["run_id"], row["status"]) for row in state["history"]])
        self.assertEqual(1, state["counters"]["items_closed"])


class CorrectionTests(Case):
    """Regressions of the review of P8.5: the identity of a child (F1), a confirmed stop (F2), requests before a quota resume
    (F3), damaged run records (F4), a relative --config (F5) and the folder of the plan (F6)."""

    def sleeper(self):
        child = subprocess.Popen(["sleep", "300"])
        self.addCleanup(lambda: (child.kill(), child.wait()))
        return child

    def test_f1_a_signal_needs_the_whole_saved_identity_of_the_child(self):
        child = self.sleeper()
        directory = self.root / "cnd-20261101T100000Z-aaaaaa"
        directory.mkdir(parents=True)
        exact = {"run_id": directory.name, "pid": child.pid, "start_ticks": process.start_ticks(child.pid),
                 "boot_id": process.boot_id()}
        launcher = autopilot.ProcessLauncher(self.project, "T")
        refused = {"another boot": dict(exact, boot_id="another-boot"), "other ticks": dict(exact, start_ticks=1),
                   "no boot": {key: value for key, value in exact.items() if key != "boot_id"},
                   "no ticks": dict(exact, start_ticks=None)}
        with mock.patch.object(os, "kill") as kill:
            for name, current in refused.items():
                with self.subTest(name):
                    self.assertIsNotNone(launcher.interrupt(directory, current))
            lease = RunLease(directory).acquire("run")  # held by this test process: not the child
            self.assertIn("not by the child", launcher.interrupt(directory, exact))
            owner = RunLease.owner(directory)
            records.write(directory / "lease.json", {**owner, "pid": child.pid, "start_ticks": 1}, "lease")
            self.assertIn("not by the child", launcher.interrupt(directory, exact), "the lease names other ticks")
            self.assertEqual(0, kill.call_count)
            records.write(directory / "lease.json", {**owner, "pid": child.pid, "start_ticks": exact["start_ticks"]}, "lease")
            self.assertIsNone(launcher.interrupt(directory, exact), "the lease names exactly the child")
            lease.release()
            self.assertIsNone(launcher.interrupt(directory, exact), "a free lease and the exact identity")
        self.assertEqual([mock.call(child.pid, autopilot.signal.SIGINT)] * 2, kill.call_args_list)

    def test_f1_the_intent_carries_the_boot_and_a_restart_keeps_it(self):
        self.start(self.controller(outcomes=[{"status": "running"}], flags={"max_wall_s": 5}))
        self.assertEqual(process.boot_id(), self.launcher.started[0]["boot_id"])
        state = self.state()
        current = dict(self.launcher.started[0], state="running", pid=4242, start_ticks=7, boot_id="old-boot")
        state.update(stop=None, mode="running", current=current, boot_id="old-boot",
                     deadline_at=timefmt.utc_stamp(NOW + 3600))
        records.write(self.root / autopilot.STATE_DOC, state, "autopilot-state")
        session = autopilot.Controller(self.project, "T", self.settings(), clock=self.clock)._session(self.state())
        self.assertEqual(("old-boot", process.boot_id()), (session["current"]["boot_id"], session["boot_id"]))

    def test_f2_a_child_that_does_not_end_stays_current_and_the_stop_is_not_a_success(self):
        for case in ("deaf", "refused"):
            with self.subTest(case):
                (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                recover = mock.Mock(return_value="pid 4001 still holds the lease 60 s after SIGKILL")
                controller = self.controller(outcomes=[{"status": "running"}], flags={"max_wall_s": 30})
                controller.recover_run = recover
                self.launcher.deaf = case == "deaf"
                self.launcher.interrupt_problem = "pid 4001 is not the child any more" if case == "refused" else None
                code, err, state = self.start(controller)
                self.assertEqual((1, "AUTOPILOT_CHECKOUT_LOST"), (code, state["stop"]["code"]), err)
                self.assertEqual(self.launcher.started[0]["run_id"], state["current"]["run_id"], "current is kept")
                self.assertIn("AUTOPILOT_MAX_WALL", state["stop"]["message"])
                recover.assert_called_once()
                self.assertEqual("hung", recover.call_args[0][1])
                for lease in self.launcher.leases.values():
                    lease.release()

    def test_f2_the_supervisor_library_stops_a_deaf_child_then_the_stop_succeeds(self):
        controller = self.controller(outcomes=[{"status": "running"}], flags={"max_wall_s": 30})
        self.launcher.deaf = True

        def stopped(current, look):
            self.launcher.finish(current["run_id"], {"status": "stopped", "stop": {"code": "INTERRUPTED", "message": "killed"}})
        controller.recover_run = stopped
        code, err, state = self.start(controller)
        self.assertEqual((0, "AUTOPILOT_MAX_WALL", None), (code, state["stop"]["code"], state["current"]), err)
        self.assertIn("did not answer SIGINT", state["stop"]["message"])
        self.assertEqual("interrupted", state["history"][0]["status"])
        self.assertGreaterEqual(self.clock.t - (NOW + 30), controller.grace_s, "SIGINT got its grace first")

    def half_known_child(self, deadline: float, run_id: str) -> dict:
        """A schema-valid session whose running child has no saved boot_id, and a held lease that names a live process with
        the same pid and start_ticks on this machine: the case after a reboot that reused pid and ticks."""
        child = self.sleeper()
        ticks = process.start_ticks(child.pid)
        store = RunStore(self.project, run_id)
        store.create({"run_id": run_id, "items": ["W1"], "lease": True})
        store.save({"status": "running", "items": {"W1": {"steps": {}}}})
        progress.Progress(run_id, store.directory, "quiet").emit("run.start")
        lease = RunLease(store.directory).acquire("run")
        self.addCleanup(lease.release)
        owner = RunLease.owner(store.directory)
        records.write(store.directory / "lease.json", {**owner, "pid": child.pid, "start_ticks": ticks,
                                                         "boot_id": process.boot_id()}, "lease")
        current = {"run_id": run_id, "launch_id": "0123456789abcdef", "state": "running", "kind": "run", "items": ["W1"],
                   "pid": child.pid, "start_ticks": ticks, "since": timefmt.utc_stamp(NOW - 60)}
        prior = {"$schema": records.TAGS["autopilot-state"][1], "plan": "T", "project": str(self.project), "pid": 1,
                 "started_at": timefmt.utc_stamp(NOW - 120), "updated_at": timefmt.utc_stamp(NOW - 10),
                 "deadline_at": timefmt.utc_stamp(deadline), "mode": "running",
                 "limits": {"max_runs": 20, "max_wall_s": 3600, "run_tokens_hard_max": 0, "max_no_progress_runs": 2,
                            "max_auto_decisions": 10, "quota_wait_max_s": 21600},
                 "counters": dict.fromkeys(autopilot.COUNTERS, 0), "current": current, "waiting_runs": [], "history": [],
                 "last_blockers": [], "stop": None}
        self.assertEqual([], records.problems(prior, "autopilot-state"))
        records.write(self.root / autopilot.STATE_DOC, prior, "autopilot-state")
        return current

    def test_f1_no_path_signals_a_child_whose_saved_identity_is_incomplete(self):
        for number, case in enumerate(("deadline", "stop request", "hung")):
            with self.subTest(case):
                (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                current = self.half_known_child(NOW - 1 if case == "deadline" else NOW + 3600,
                                                f"cnd-20261101T095000Z-bbbbb{number}")
                if case == "stop request":
                    self.request("stop")
                controller = autopilot.Controller(self.project, "T", self.settings(), clock=self.clock,
                                                  readiness=lambda: ready(kind="terminal"), dirty=lambda folders=(): False,
                                                  say=lambda text: None)
                hung = {"health": "hung", "reason_code": "HEARTBEAT_STALE", "detail": "forced"}
                with mock.patch.object(os, "kill") as kill, \
                        mock.patch.object(autopilot.supervisor, "reap") as reap, \
                        mock.patch.object(autopilot.runs, "health_of", return_value=hung) if case == "hung" \
                        else contextlib.nullcontext():
                    code, err, state = self.start(controller)
                self.assertEqual((1, "AUTOPILOT_CHECKOUT_LOST"), (code, state["stop"]["code"]), err)
                self.assertEqual(0, kill.call_count, "no signal to a half-confirmed identity")
                reap.assert_not_called()
                self.assertEqual(current, state["current"], "current is kept as it was")
                self.assertIn("identity of the child", state["stop"]["message"])

    def quota(self, reset_in: int = 5) -> dict:
        return {"status": "stopped", "stop": {"code": "PROVIDER_QUOTA",
                                              "message": f"the limit resets {timefmt.utc_stamp(NOW + reset_in)}, resume after it"}}

    def test_f3_drain_before_and_after_the_reset_stops_without_a_resume(self):
        for when in ("before", "after"):
            with self.subTest(when):
                (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                self.clock.t = NOW
                asked: list = []

                def drain(clock, when=when, asked=asked):
                    due = clock.t >= NOW + 6 if when == "after" else True
                    if due and not asked:
                        asked.append(clock.t)
                        self.request("drain")
                self.clock.hooks = [drain]
                code, err, state = self.start(self.controller(outcomes=[self.quota()]))
                self.assertEqual((0, "AUTOPILOT_DRAINED", ["run"]), (code, state["stop"]["code"],
                                                                     [row["kind"] for row in self.launcher.started]), err)
                self.assertIn("orch conduct resume --run", state["stop"]["message"])

    def test_f3_pause_holds_the_quota_resume_until_resume(self):
        steps: list = []

        def control(clock):
            if not steps:
                steps.append("pause")
                self.request("pause")
            elif len(steps) == 1 and clock.t >= NOW + 20:
                self.assertEqual(["run"], [row["kind"] for row in self.launcher.started], "no resume while paused")
                steps.append("resume")
                self.request("resume")
        self.clock.hooks = [control]
        answers = iter([ready()])
        controller = self.controller(lambda: next(answers, ready(kind="terminal")),
                                     outcomes=[self.quota(), {"status": "finished", "closed": ["W1"]}])
        code, err, state = self.start(controller)
        self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]), err)
        self.assertEqual(["run", "resume"], [row["kind"] for row in self.launcher.started], "exactly one resume")
        self.assertEqual(1, state["counters"]["quota_waits"])

    def test_f4_a_damaged_record_of_the_current_run_is_a_stop_of_the_session(self):
        for status, corrupt in (("finished", "json"), ("finished", "schema"), ("running", "json")):
            with self.subTest(status=status, corrupt=corrupt):
                (self.root / autopilot.STATE_DOC).unlink(missing_ok=True)
                with mock.patch.object(autopilot.events, "emit") as emit:
                    code, err, state = self.start(self.controller(outcomes=[{"status": status, "corrupt": corrupt}]))
                self.assertEqual((1, "AUTOPILOT_STATE_INVALID"), (code, state["stop"]["code"]), err)
                self.assertIn("AUTOPILOT_STATE_INVALID: ", err)
                self.assertEqual(["orch.autopilot.stopped"], [call.args[0] for call in emit.call_args_list])
                self.assertEqual(self.launcher.started[0]["run_id"], state["current"]["run_id"], "current is kept")
                self.assertTrue((self.root / self.launcher.started[0]["run_id"] / "state.json").read_text(encoding="utf-8"))
                for lease in self.launcher.leases.values():
                    lease.release()
                self.launcher.leases.clear()

    def test_f5_a_relative_config_is_the_file_of_the_working_folder_for_every_child(self):
        work = self.project.parent / "work"
        work.mkdir()
        (work / "cfg.toml").write_text("schema_version = 1\n[orch.autopilot]\nenabled = true\n", encoding="utf-8")
        (self.project / "cfg.toml").write_text("schema_version = 1\n[orch]\nengine = \"tmux\"\n", encoding="utf-8")
        (self.home / "skm" / "config" / "config.toml").write_text("schema_version = 1\n[orch.autopilot]\nallowed = true\n",
                                                                  encoding="utf-8")
        with contextlib.chdir(work):
            controller = autopilot.Controller(self.project, "T", self.settings(), config_file=Path("cfg.toml"))
            seen = mock.Mock(return_value=ready(kind="terminal"))
            out = io.StringIO()
            with mock.patch.object(autopilot_status, "source_readiness", seen), contextlib.redirect_stdout(out):
                self.assertEqual(0, cli.main(["--config", "cfg.toml", "--project", str(self.project), "autopilot", "explain",
                                              "--plan", "T", "--json"]))
        self.assertEqual(work / "cfg.toml", controller.config_file)
        argv = controller.launcher.argv({"kind": "resume", "run_id": "cnd-x"})
        self.assertEqual(str(work / "cfg.toml"), argv[argv.index("--config") + 1])
        self.assertEqual(work / "cfg.toml", seen.call_args[0][2])
        self.assertEqual(("stop", "AUTOPILOT_NO_WORK"), (json.loads(out.getvalue())["next"]["action"],
                                                         json.loads(out.getvalue())["next"]["code"]))

    def test_f6_only_a_plan_folder_the_source_named_inside_the_checkout_is_left_out(self):
        for path, folders, outside in (("src/T/module.py", ("plans/T",), True), ("plans/T2/x.json", ("plans/T",), True),
                                       ("plans/T/phases/P1.json", ("plans/T",), False), ("plans/T", ("plans/T",), False),
                                       ("plans/T/module.py", (), True), (".swissknifeman/x", (), False)):
            with self.subTest(path=path, folders=folders):
                self.assertEqual(outside, autopilot_status.outside_plan(path, folders))
        def state(named):
            return {"items": {"W1": {"steps": {"brief": {"result": {"artifacts_dir": named}}}}}} if named else {"items": {"W1": {}}}
        for named, expected in (("plans/T/artifacts/W1", ("plans/T",)), (None, ()), ("../elsewhere/T/artifacts/W1", ()),
                                ("/abs/T/artifacts/W1", ()), ("plans/T/other/W1", ()),
                                (".swissknifeman/state/orch-artifacts/cnd-x/artifacts/W1", ())):
            with self.subTest(named=named):
                self.assertEqual(expected, autopilot_status.plan_folders(self.project, state(named)))

    def commit(self, *paths) -> None:
        git = ["git", "-C", str(self.project)]
        for path in paths:
            (self.project / path).parent.mkdir(parents=True, exist_ok=True)
            (self.project / path).write_text("one\n", encoding="utf-8")
        subprocess.run(git + ["add", "-A"], check=True, capture_output=True)
        subprocess.run(git + ["-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-qm", "base"], check=True,
                       capture_output=True)

    def real_dirty(self, readiness=None, outcomes=()) -> autopilot.Controller:
        controller = self.controller(readiness, outcomes=outcomes)
        controller.dirty = functools.partial(autopilot_status.tracked_changes, self.project)  # the real git status
        return controller

    def test_f6_a_tracked_change_under_plans_of_an_unknown_plan_folder_needs_the_owner(self):
        self.commit("plans/T/module.py", "src/T/module.py")
        (self.project / "plans/T/module.py").write_text("changed\n", encoding="utf-8")
        self.assertTrue(autopilot_status.tracked_changes(self.project))
        self.assertFalse(autopilot_status.tracked_changes(self.project, ("plans/T",)))
        waiting = {"status": "waiting", "waiting": {"W1": ["q1"]}, "stop": {"code": "WAITING_DECISION", "message": "q1"}}
        code, err, state = self.start(self.real_dirty(outcomes=[waiting]))  # a plan in a workspace: no artifacts_dir
        self.assertEqual((1, "AUTOPILOT_OWNER_NEEDED", []), (code, state["stop"]["code"], state["waiting_runs"]), err)
        self.assertEqual(1, len(self.launcher.started), "no independent lane")
        self.assertEqual("changed\n", (self.project / "plans/T/module.py").read_text(encoding="utf-8"))

    def test_f6_the_plan_folder_the_brief_named_is_left_out_and_a_product_file_is_not(self):
        self.commit("plans/T/plan.json", "src/T/module.py")
        (self.project / "plans/T/plan.json").write_text("changed\n", encoding="utf-8")
        waiting = {"status": "waiting", "waiting": {"W1": ["q1"]}, "brief": "plans/T/artifacts/{ref}",
                   "stop": {"code": "WAITING_DECISION", "message": "q1"}}
        answers = iter([ready()])
        controller = self.real_dirty(lambda: next(answers, ready(kind="terminal")), outcomes=[waiting])
        controller.policy["max_wall_s"] = 60
        with mock.patch.object(controller, "_finish", wraps=controller._finish) as finish:
            self.clock.hooks = [lambda clock: (self.root / autopilot.REQUEST_DOC).exists() or self.request("drain")]
            code, err, state = self.start(controller)
        self.assertEqual((0, "AUTOPILOT_DRAINED"), (code, state["stop"]["code"]), err)
        self.assertEqual(1, len(state["waiting_runs"]), "the plan change of a known plan folder is no owner matter")
        finish.assert_called_once()
        (self.root / autopilot.STATE_DOC).unlink()
        (self.project / "src/T/module.py").write_text("changed\n", encoding="utf-8")
        code, err, state = self.start(self.real_dirty(outcomes=[dict(waiting)]))
        self.assertEqual((1, "AUTOPILOT_OWNER_NEEDED", []), (code, state["stop"]["code"], state["waiting_runs"]), err)

    def test_f6_the_controller_hands_the_folders_of_the_run_to_its_dirty_check(self):
        self.dirty = True
        waiting = {"status": "waiting", "waiting": {"W1": ["q1"]}, "brief": "plans/T/artifacts/{ref}",
                   "stop": {"code": "WAITING_DECISION", "message": "q1"}}
        code, _, state = self.start(self.controller(outcomes=[waiting]))
        self.assertEqual(("AUTOPILOT_OWNER_NEEDED", ("plans/T",)), (state["stop"]["code"], self.folders_seen))


class Crash(BaseException):
    """The controller dies (a SIGKILL in the middle of a step)."""


class Crashing(Launcher):
    def start(self, current: dict) -> dict:
        raise Crash()


class LateAck(Launcher):
    """``wait_ack`` ran out of time; the child acknowledged right after (``acked``) and exited before the controller looked."""

    acked = True

    def acknowledged(self, current: dict, child: dict) -> dict:
        current.pop("_outcome", None)
        raise Stop("DETACH_FAILED", "no acknowledgement within 20 s")

    def alive(self, child: dict) -> bool:
        return False

    def ack_of(self, current: dict):
        return super().ack_of(current) if self.acked else None


class FenceTests(Case):
    """P8.8, the controller side of the startup fence (``autopilot_fence``) on a controlled clock: the intent is cancelled
    only under ``autopilot-launch.lock`` and never while a child holds it; a cancelled launch id is refused by a late child;
    an existing run keeps its id and state and gets a new launch id; a held run or a partial new run is never replaced."""

    RUN = "cnd-20261101T095900Z-aaaaaa"
    OLD = "0123456789abcdef"

    def prior(self, kind: str = "run", since: float = NOW - 3600, retry=None) -> dict:
        intent = {"run_id": self.RUN, "launch_id": self.OLD, "state": "launching", "kind": kind,
                  "since": timefmt.utc_stamp(since), **({"items": ["W1"]} if kind == "run" else {}),
                  **({"retry": retry} if retry else {})}
        records.write(self.root / autopilot.STATE_DOC, {
            "$schema": records.TAGS["autopilot-state"][1], "plan": "T", "project": str(self.project), "pid": 1,
            "started_at": timefmt.utc_stamp(NOW), "updated_at": timefmt.utc_stamp(NOW),
            "deadline_at": timefmt.utc_stamp(NOW + 3600), "mode": "running",
            "limits": {"max_runs": 20, "max_wall_s": 3600, "run_tokens_hard_max": 0, "max_no_progress_runs": 2,
                       "max_auto_decisions": 10, "quota_wait_max_s": 21600},
            "counters": dict.fromkeys(autopilot.COUNTERS, 0), "current": intent, "waiting_runs": [],
            "history": [{"run_id": self.RUN, "started_at": intent["since"], "ended_at": None, "exit": None,
                         "status": "running", "reason_code": None, "items_closed": [], "kind": kind}],
            "last_blockers": [], "stop": None}, "autopilot-state")
        return intent

    def late_child(self, launch_id: str = OLD) -> None:
        """The fence of a child of ``launch_id`` that reaches it only now."""
        env = {detach.STATE_ENV: str(self.root / autopilot.STATE_DOC), detach.LAUNCH_ENV: launch_id}
        with mock.patch.dict(os.environ, env), self.assertRaises(Stop) as refused:
            with detach.startup_fence(self.project, self.RUN):
                self.fail("a cancelled launch passed the fence")
        self.assertEqual(detach.CANCELLED, refused.exception.code)

    def waiting_run(self) -> None:
        self.write_run(self.RUN, {"kind": "run", "items": ["W1"]}, {"status": "waiting", "waiting": {"W1": ["q1"]}})
        self.answer(self.RUN, "W1", "q1")

    def test_v_a_new_run_never_started_is_cancelled_once_and_its_late_child_refused(self):
        self.prior()
        code, _, state = self.start(self.controller(ready(kind="terminal")))
        self.assertEqual((0, "AUTOPILOT_NO_WORK", None), (code, state["stop"]["code"], state["current"]))
        self.assertEqual([(self.RUN, "never_started")], [(row["run_id"], row["status"]) for row in state["history"]])
        self.assertEqual([], self.launcher.started)
        self.late_child()
        self.assertFalse((self.root / self.RUN).exists())
        lock = FileLock(self.root / detach.LAUNCH_LOCK)
        self.assertTrue(lock.acquire(), "the launch lock is free")
        lock.release()

    def test_v_an_intent_is_not_cancelled_while_its_child_holds_the_launch_lock_and_its_ack_adopts_it(self):
        self.prior()
        held = detach.launch_lock(self.root, 0)
        self.addCleanup(held.release)
        looks = []

        def child_inside_its_fence(clock):
            current = self.state()["current"]
            looks.append((current["launch_id"], current["state"]))
            if clock.sleeps == 3:  # the child created its run and acknowledged under the lock, then lets it go
                self.write_run(self.RUN, {"kind": "run", "items": ["W1"]}, {"status": "finished", "closed": ["W1"]})
                self.launcher.started.append({"launch_id": self.OLD})
                held.release()
        self.clock.hooks = [child_inside_its_fence]
        with mock.patch.object(detach, "LAUNCH_LOCK_WAIT_S", 0):
            code, _, state = self.start(self.controller(ready(kind="terminal")))
        self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]))
        self.assertEqual([(self.OLD, "launching")] * 3, looks[:3], "no cancel while the launch lock is held")
        self.assertEqual([(self.RUN, "finished", ["W1"])], [(row["run_id"], row["status"], row["items_closed"])
                                                           for row in state["history"]])
        self.assertEqual(1, len(self.launcher.started), "no second child")

    def test_v2_an_existing_run_keeps_its_id_and_state_and_gets_a_new_launch_id(self):
        self.waiting_run()
        self.prior(kind="continue", retry=["W1"])
        code, _, state = self.start(self.controller(ready(kind="terminal"), outcomes=[{"status": "finished", "closed": ["W1"]}]))
        self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]))
        [again] = self.launcher.started
        self.assertEqual(("resume", self.RUN, ["W1"]), (again["kind"], again["run_id"], again["retry"]),
                         "a continue that may have begun goes on as resume --retry of its saved pieces (F3)")
        self.assertNotEqual(self.OLD, again["launch_id"])
        self.assertEqual("conduct resume --run {} --retry W1 --json-lines".format(self.RUN),
                         " ".join(autopilot.ProcessLauncher(self.project, "T").argv(again)[-7:]))
        self.assertEqual([(self.RUN, "finished", ["W1"])], [(row["run_id"], row["status"], row["items_closed"])
                                                           for row in state["history"]], "one entry, never never_started")
        self.assertEqual(1, state["counters"]["runs"])
        self.late_child()

    def test_v2_an_existing_run_held_without_the_ack_of_this_launch_stops_with_no_second_child(self):
        self.waiting_run()
        self.prior(kind="resume")
        lease = RunLease(self.root / self.RUN).acquire("resume")
        self.addCleanup(lease.release)
        code, _, state = self.start(self.controller(ready(kind="terminal")))
        self.assertEqual((1, "AUTOPILOT_CHECKOUT_LOST"), (code, state["stop"]["code"]))
        self.assertEqual((self.OLD, "launching"), (state["current"]["launch_id"], state["current"]["state"]))
        self.assertEqual([], self.launcher.started)
        self.assertEqual(["running"], [row["status"] for row in state["history"]])

    def test_v2_an_existing_run_folder_is_no_start_of_this_launch_and_is_cancelled_only_after_the_grace(self):
        self.waiting_run()
        intent = self.prior(kind="continue", since=NOW - autopilot.LAUNCH_GRACE_S + 1, retry=["W1"])
        controller = self.controller(ready(kind="terminal"))
        controller.doc = self.state()
        self.assertEqual("launching", controller._look(dict(intent)))
        self.assertEqual((self.OLD, "launching"), (self.state()["current"]["launch_id"], self.state()["current"]["state"]))
        self.clock.t += 2
        self.assertEqual("relaunch", controller._look(dict(intent)))
        again = self.state()["current"]  # cancelled and replaced by the next attempt in one save (F2)
        self.assertEqual((self.RUN, "resume", ["W1"], "launching"), (again["run_id"], again["kind"], again["retry"], again["state"]))
        self.assertNotEqual(self.OLD, again["launch_id"])
        self.assertEqual([("running", "resume")], [(row["status"], row["kind"]) for row in self.state()["history"]],
                         "no never_started")
        self.assertEqual("waiting", records.read(self.root / self.RUN / "state.json", "state")["status"])

    def test_f2_a_crash_after_the_cancel_keeps_the_next_attempt_and_a_restart_goes_on_with_it(self):
        for kind, retry in (("continue", ["W1"]), ("resume", None)):
            with self.subTest(kind):
                if not (self.root / self.RUN).exists():
                    self.waiting_run()
                self.prior(kind=kind, retry=retry)
                crashing = self.controller(ready(kind="waiting"))
                crashing.launcher = Crashing(self)
                with self.assertRaises(Crash), contextlib.redirect_stderr(io.StringIO()):
                    crashing.start()
                saved = self.state()["current"]
                self.assertEqual((self.RUN, "launching", "resume" if retry else kind),
                                 (saved["run_id"], saved["state"], saved["kind"]))
                self.clock.t += 2 * autopilot.LAUNCH_GRACE_S
                code, err, state = self.start(self.controller(ready(kind="waiting"),
                                                              outcomes=[{"status": "finished", "closed": ["W1"]}]))
                self.assertEqual(0, self.launcher.readiness_at[0], "the attempt comes before readiness (no NEXT_WAITING)")
                [again] = self.launcher.started
                self.assertEqual((self.RUN, saved["kind"]), (again["run_id"], again["kind"]))
                self.assertNotIn(again["launch_id"], (self.OLD, saved["launch_id"]))
                self.assertEqual([self.RUN], [row["run_id"] for row in state["history"]])
                self.assertNotIn("never_started", [row["status"] for row in state["history"]])

    def test_f2_max_runs_keeps_the_next_attempt_current_for_the_next_start(self):
        self.waiting_run()
        self.prior(kind="resume")
        doc = self.state()
        doc["counters"]["runs"] = 1
        records.write(self.root / autopilot.STATE_DOC, doc, "autopilot-state")
        code, _, state = self.start(self.controller(ready(kind="terminal"), flags={"max_runs": 1}))
        self.assertEqual((0, "AUTOPILOT_MAX_RUNS", []), (code, state["stop"]["code"], self.launcher.started))
        self.assertEqual((self.RUN, "resume", "launching"), (state["current"]["run_id"], state["current"]["kind"],
                                                             state["current"]["state"]))
        self.clock.t += 2 * autopilot.LAUNCH_GRACE_S
        code, _, state = self.start(self.controller(ready(kind="terminal"), outcomes=[{"status": "finished", "closed": ["W1"]}]))
        self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]))
        self.assertEqual([(self.RUN, "resume")], [(row["run_id"], row["kind"]) for row in self.launcher.started])
        self.assertEqual([(self.RUN, "finished")], [(row["run_id"], row["status"]) for row in state["history"]])

    def test_f1_an_ack_written_after_the_wait_ran_out_adopts_the_run_once(self):
        controller = self.controller(lambda: ready(kind="terminal") if self.launcher.started else ready())
        controller.launcher = self.launcher = LateAck(self, [{"status": "finished", "closed": ["W1"]}])
        code, err, state = self.start(controller)
        self.assertEqual((0, "AUTOPILOT_NO_WORK"), (code, state["stop"]["code"]), err)
        [run] = self.launcher.started
        self.assertEqual([(run["run_id"], "finished", ["W1"])], [(row["run_id"], row["status"], row["items_closed"])
                                                                for row in state["history"]])
        self.assertEqual(1, state["counters"]["items_closed"])

    def test_f1_without_an_ack_or_a_run_the_dead_child_never_started(self):
        controller = self.controller(ready())
        controller.launcher = self.launcher = LateAck(self, [{"refuse": ("UNUSED", "the child wrote nothing")}])
        self.launcher.acked = False
        code, _, state = self.start(controller)
        self.assertEqual((1, "AUTOPILOT_RUN_STOPPED"), (code, state["stop"]["code"]))
        self.assertEqual([("never_started", "DETACH_FAILED")], [(row["status"], row["reason_code"]) for row in state["history"]])

    def test_a_partial_new_run_is_kept_and_stops_the_session(self):
        self.prior()
        (self.root / self.RUN).mkdir(parents=True)
        code, _, state = self.start(self.controller(ready(kind="terminal")))
        self.assertEqual((1, "AUTOPILOT_STATE_INVALID"), (code, state["stop"]["code"]))
        self.assertEqual(self.RUN, state["current"]["run_id"])
        self.assertTrue((self.root / self.RUN).is_dir())
        self.assertEqual([], self.launcher.started)


class VerbTests(Case):
    def test_status_dead_running_and_none(self):
        self.assertEqual("none", autopilot_status.status(self.project)["status"])
        self.start(self.controller(outcomes=[{"status": "running"}], flags={"max_wall_s": 5}))
        state = self.state()
        state.update(mode="running", stop=None)
        records.write(self.root / autopilot.STATE_DOC, state, "autopilot-state")
        found = autopilot_status.status(self.project)
        self.assertEqual(("dead", False), (found["status"], found["alive"]))
        self.assertEqual([], contract.problems(found, "autopilot-status"))
        lock = FileLock(self.root / autopilot.LOCK_FILE)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)
        self.assertEqual(("running", True), (autopilot_status.status(self.project)["status"], autopilot_status.alive(self.root)))

    def test_a_request_needs_a_live_controller(self):
        with self.assertRaises(Stop) as caught:
            autopilot_status.request(self.project, "pause", "owner")
        self.assertEqual("AUTOPILOT_NOT_RUNNING", caught.exception.code)
        self.root.mkdir(parents=True)
        lock = FileLock(self.root / autopilot.LOCK_FILE)
        self.assertTrue(lock.acquire())
        self.addCleanup(lock.release)
        autopilot_status.request(self.project, "drain", "owner")
        found = records.read(self.root / autopilot.REQUEST_DOC, "autopilot-request")
        self.assertEqual(("drain", "owner"), (found["action"], found["by"]))
        self.assertEqual("drain", autopilot_status.status(self.project)["request"]["action"])

    def test_explain_names_the_sources_and_the_next_action_and_starts_nothing(self):
        found = autopilot_status.explain(self.project, "T", self.settings(machine={"allowed": True, "max_runs": 9}),
                                         flags={"max_runs": 4}, readiness=lambda: ready("P1"))
        self.assertEqual([], contract.problems(found, "autopilot-explain"))
        self.assertEqual((4, "flag:--max-runs", "machine", "project"),
                         (found["policy"]["max_runs"], found["sources"]["max_runs"], found["sources"]["allowed"],
                          found["sources"]["enabled"]))
        self.assertEqual(("run", ["W1"]), (found["next"]["action"], found["next"]["items"]))
        self.assertFalse((self.root / autopilot.STATE_DOC).exists())
        denied = autopilot_status.explain(self.project, "T", self.settings(machine={}), readiness=lambda: ready("P1"))
        self.assertEqual(("stop", "AUTOPILOT_NOT_ALLOWED", None), (denied["next"]["action"], denied["next"]["code"],
                                                                   denied["readiness"]))

    def test_explain_and_status_on_the_command_line(self):
        machine = self.home / "skm" / "config" / "config.toml"
        machine.write_text("schema_version = 1\n[orch.autopilot]\nallowed = true\n", encoding="utf-8")
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(autopilot_status, "source_readiness",
                                                                return_value=ready(kind="terminal")):
            self.assertEqual(0, cli.main(["--project", str(self.project), "autopilot", "explain", "--plan", "T", "--json"]))
        doc = json.loads(out.getvalue())
        self.assertEqual(("stop", "AUTOPILOT_DISABLED", "machine"), (doc["next"]["action"], doc["next"]["code"],
                                                                     doc["sources"]["allowed"]))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(0, cli.main(["--project", str(self.project), "autopilot", "status", "--json"]))
        self.assertEqual("none", json.loads(out.getvalue())["status"])
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(1, cli.main(["--project", str(self.project), "autopilot", "stop"]))
        self.assertIn("AUTOPILOT_NOT_RUNNING: ", err.getvalue())
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli.main(["--project", str(self.project), "autopilot", "start", "--plan", "T", "--max-runs", "0"])

    def test_the_state_survives_a_save_and_a_load_and_a_bad_file_is_not_overwritten(self):
        self.start(self.controller(outcomes=[{"status": "finished", "closed": ["W1"]}], flags={"max_runs": 1}))
        state = self.state()
        self.assertEqual([], records.problems(state, "autopilot-state"))
        self.assertEqual(records.TAGS["autopilot-state"][1], state["$schema"])
        (self.root / autopilot.STATE_DOC).write_text("{not json", encoding="utf-8")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = self.controller().start()
        self.assertEqual(1, code)
        self.assertIn("AUTOPILOT_STATE_INVALID: STATE_CORRUPT", err.getvalue())
        self.assertEqual("{not json", (self.root / autopilot.STATE_DOC).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
