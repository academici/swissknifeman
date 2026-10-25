"""The executor session of a piece (P7.4): the fingerprint it is built under, the decision to resume it or start a fresh
one and the reason, the slots of a run and their migration from the single slot of an older state, the follow-up of a
group review and what the observer counts. Fake providers only."""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
import shutil
import tempfile
import types
import unittest
from unittest import mock

from aicore.ext import events as journal

from orch.conductor import contract, engine, records
from orch.conductor.application import review_plan
from orch.conductor.infrastructure import sessions
from orch.conductor.observer import metrics
from orch.conductor.stages import execute
from tests.test_conductor import GREEN, ConductorCase, executor_ok, report
from tests.test_conductor_questions import ASK, asking

CLAUDE = {"provider": "claude-code", "model": "m", "effort": "high"}


def stub(slots: dict):
    """A conductor with the state ``slots`` and a project directory of its own."""
    base = Path(tempfile.mkdtemp())
    owner = engine.Conductor.__new__(engine.Conductor)
    owner.project = owner.directory = base
    owner.state = {"executor_sessions": slots} if slots else {}
    owner.progress = mock.Mock()
    return owner, base


def piece(ref: str = "W1", mode: str = "handoff", **options):
    return types.SimpleNamespace(ref=ref, options={"session": {"executor": mode, **options}}, state={}, claim={"attempt_id": "att-1"},
                                 input_doc={}, routes={"executor": CLAUDE})


HANDOFF_CONFIG = '[orch.conductor]\nsession_executor = "handoff"\n'  # the default is `shared`


class DecisionTests(unittest.TestCase):
    def owner(self, slots: dict):
        owner, base = stub(slots)
        self.addCleanup(shutil.rmtree, base, True)
        return owner

    def slot(self, owner, item, route=CLAUDE, **fields) -> dict:
        return {"session": "s1", "provider": route["provider"], "route": sessions.label(route), "last_item": item.ref,
                "fingerprint": sessions.fingerprint(owner, item, route), "last_used_at": "2026-10-23T00:00:00Z", **fields}

    def decide(self, owner, item, route=CLAUDE) -> tuple:
        return sessions.session_decision(owner, item, route, sessions.fingerprint(owner, item, route))

    def test_the_fingerprint_names_the_identity_and_a_shared_one_leaves_out_the_piece(self):
        owner = self.owner({})
        found = sessions.fingerprint(owner, piece(), CLAUDE)
        self.assertEqual(sorted(found), ["attempt_id", "authority_digest", "base", "instructions_digest", "isolation_home",
                                         "item", "project", "provider", "role", "worktree"])
        self.assertEqual((found["provider"], found["role"], found["item"], found["attempt_id"]),
                         ("claude-code", "executor", "W1", "att-1"))
        self.assertEqual((found["authority_digest"], found["isolation_home"]), ("", ""))  # not isolated; no envelope yet
        shared = sessions.fingerprint(owner, piece(mode="shared"), CLAUDE)
        self.assertEqual(sorted(set(found) - set(shared)), ["attempt_id", "base", "item"])

    def test_same_identity_resumes_and_the_first_difference_names_the_field(self):
        for field in ("attempt_id", "base", "project"):
            with self.subTest(field):
                owner, item = self.owner({}), piece()
                owner.state["executor_sessions"] = {"W1": self.slot(owner, item)}
                self.assertEqual(self.decide(owner, item), ("resume", "s1"))
                if field == "attempt_id":
                    item.claim.update(attempt_id="att-2")
                elif field == "base":
                    item.state.update(session_base="beef")
                else:
                    owner.project = owner.project / "other"
                self.assertEqual(self.decide(owner, item), ("fresh", f"fingerprint_changed:{field}"))

    def test_a_changed_authority_or_isolation_home_is_never_a_resume(self):
        owner = self.owner({})
        item = piece()
        owner.state["executor_sessions"] = {"W1": self.slot(owner, item)}
        for field in ("authority_digest", "isolation_home"):
            changed = dict(sessions.identity_inputs(owner, item, CLAUDE), **{field: "sha256:" + "b" * 64})
            with self.subTest(field), mock.patch.object(sessions, "identity_inputs", return_value=changed):
                self.assertEqual(self.decide(owner, item), ("fresh", f"fingerprint_changed:{field}"))

    def test_the_isolation_home_of_a_codex_executor_enters_the_fingerprint(self):
        """P6.1: an isolated Codex executor keeps its sessions in the CODEX_HOME of the run; a session kept in another
        home cannot be continued (SESSION_FRESH fingerprint_changed:isolation_home)."""
        codex = {"provider": "codex", "model": "m", "effort": "high",
                 "resume_argv": ["codex", "exec", "resume", "{session}", "-"]}
        owner = self.owner({})
        item = piece()
        item.options["instructions"] = {"isolate_roles": ["executor"], "isolation": "prefer"}
        self.assertEqual(sessions.identity_inputs(owner, item, codex)["isolation_home"],
                         str(owner.directory / "isolation" / "codex-home"))
        self.assertEqual(sessions.identity_inputs(owner, item, CLAUDE)["isolation_home"], "")
        owner.state["executor_sessions"] = {"W1": self.slot(owner, item, codex)}
        self.assertEqual(self.decide(owner, item, codex), ("resume", "s1"))
        owner.directory = owner.directory / "other-run"
        self.assertEqual(self.decide(owner, item, codex), ("fresh", "fingerprint_changed:isolation_home"))
        item.options["instructions"]["isolation"] = "off"
        self.assertEqual(sessions.identity_inputs(owner, item, codex)["isolation_home"], "")

    def test_a_changed_instructions_digest_is_never_a_resume(self):
        owner = self.owner({})
        item = piece()
        (owner.directory / "instructions.json").write_text('{"targets": {}}', encoding="utf-8")
        owner.state["executor_sessions"] = {"W1": self.slot(owner, item)}
        self.assertEqual(self.decide(owner, item), ("resume", "s1"))
        (owner.directory / "instructions.json").write_text('{"targets": {"executor": {"parts": []}}}', encoding="utf-8")
        self.assertEqual(self.decide(owner, item), ("fresh", "fingerprint_changed:instructions_digest"))

    def test_what_the_run_fills_into_the_instructions_itself_is_not_a_change(self):
        owner = self.owner({})
        path = owner.directory / "instructions.json"
        path.write_text('{"targets": {}}', encoding="utf-8")
        before = sessions.instructions_digest(owner)
        path.write_text('{"targets": {}, "variant_resolution": {"claude-code/m": "claude"}}', encoding="utf-8")
        self.assertEqual(sessions.instructions_digest(owner), before)
        self.assertTrue(before.startswith("sha256:"))
        path.unlink()
        self.assertEqual(sessions.instructions_digest(owner), "")

    def test_model_or_effort_change_still_resumes_and_says_so(self):
        owner = self.owner({})
        item = piece()
        owner.state["executor_sessions"] = {"W1": self.slot(owner, item)}
        other = dict(CLAUDE, effort="low")
        self.assertEqual(self.decide(owner, item, other), ("resume", "s1"))
        owner._shared_session = lambda *args: True
        self.assertEqual(sessions.resume_args(owner, item, "executor", other), ["--resume", "s1"])
        self.assertEqual([call.kwargs["reason_code"] for call in owner.progress.emit.call_args_list], ["SESSION_ROUTE_CHANGED"])

    def test_per_item_and_missing_slots_and_lost_sessions_are_fresh_with_a_reason(self):
        owner = self.owner({})
        self.assertEqual(self.decide(owner, piece(mode="per-item")), ("fresh", "per_item_mode"))
        self.assertEqual(self.decide(owner, piece()), ("fresh", "first_round"))
        item = piece()
        owner.state["executor_sessions"] = {"W1": self.slot(owner, item, error="ROLE_FAILED")}
        self.assertEqual(self.decide(owner, item), ("fresh", "provider_error"))
        owner.state["executor_sessions"] = {"W1": {k: v for k, v in self.slot(owner, item).items() if k != "session"}}
        self.assertEqual(self.decide(owner, item), ("fresh", "no_session_id"))

    def test_a_session_of_another_provider_is_not_resumed(self):
        owner = self.owner({})
        item = piece()
        owner.state["executor_sessions"] = {"W1": self.slot(owner, item)}
        other = dict(CLAUDE, provider="codex", resume_argv=["codex", "exec", "resume", "{session}"])
        self.assertEqual(self.decide(owner, item, other), ("fresh", "fingerprint_changed:provider"))

    def test_resume_is_decided_by_the_capability_record_not_by_the_name_of_the_provider(self):
        self.assertEqual({name: sessions.resume_capability(name) for name in ("claude-code", "codex", "grok", "nobody")},
                         {"claude-code": "adapted", "codex": "adapted", "grok": "adapted", "nobody": "unknown"})
        owner = self.owner({})
        item = piece()
        for provider in ("codex", "grok"):
            with self.subTest(provider):
                route = dict(CLAUDE, provider=provider, resume_argv=["x", "--resume", "{session}"])
                owner.state["executor_sessions"] = {"W1": self.slot(owner, item, route)}
                self.assertTrue(sessions.shared_session(owner, item, "executor", route))
                self.assertEqual(self.decide(owner, item, route), ("resume", "s1"))
                self.assertEqual(sessions.resume_args(owner, item, "executor", route), ["s1"])  # role_argv builds the command
        with mock.patch.object(sessions, "resume_capability", return_value="unknown"):
            route = dict(CLAUDE, provider="codex")
            self.assertFalse(sessions.shared_session(owner, item, "executor", route))
            self.assertEqual(self.decide(owner, item, route), ("fresh", "provider_unsupported"))
            self.assertEqual(sessions.resume_args(owner, item, "executor", route), [])
        with mock.patch.object(sessions, "resume_capability", return_value="unsupported"):
            self.assertEqual(self.decide(owner, item), ("fresh", "provider_unsupported"))

    def test_an_idle_session_expires_only_when_the_option_is_set(self):
        owner = self.owner({})
        item = piece(max_idle_s=1)
        owner.state["executor_sessions"] = {"W1": self.slot(owner, item, last_used_at="2020-01-01T00:00:00Z")}
        self.assertEqual(self.decide(owner, item), ("fresh", "idle_expired"))
        item.options["session"]["max_idle_s"] = 0
        self.assertEqual(self.decide(owner, item), ("resume", "s1"))
        item.options["session"]["max_idle_s"] = 10 ** 9
        self.assertEqual(self.decide(owner, item), ("resume", "s1"))

    def test_max_idle_s_is_a_run_option(self):
        self.assertEqual(contract.problems({"session": {"max_idle_s": 600}}, "run-options"), [])
        self.assertTrue(contract.problems({"session": {"max_idle_s": -1}}, "run-options"))
        self.assertTrue(contract.problems({"session": {"max_idle_s": "soon"}}, "run-options"))

    def test_the_decision_names_the_reuse_of_a_resumed_session(self):
        item = piece()
        slot = {"last_used_at": "2026-10-23T10:00:00Z", "last_item": "W1"}
        owner = self.owner({})
        self.assertEqual(sessions.reuse_of(owner, item, "executor.2", slot), "correction")
        self.assertEqual(sessions.reuse_of(owner, item, "executor.1-q1", slot), "question")
        self.assertEqual(sessions.reuse_of(owner, item, "executor.1", dict(slot, last_item="W0")), "next_piece")
        item.state["retried"] = "2026-10-23T11:00:00Z"
        self.assertEqual(sessions.reuse_of(owner, item, "executor.1", slot), "retry")
        self.assertEqual(sessions.reuse_of(owner, item, "executor.1", None), "followup")
        self.assertEqual(sessions.event_data({"action": "resume", "value": "s", "reuse": "retry"}),
                         {"resumed": True, "reason": "retry"})
        self.assertEqual(sessions.event_data({"action": "fresh", "value": "first_round"}),
                         {"resumed": False, "reason": "first_round"})
        self.assertIsNone(sessions.event_data(None))


class MigrationTests(unittest.TestCase):
    LEGACY = {"executor_session": "s7", "executor_session_route": "claude-code/m/high", "executor_session_item": "W3",
              "executor_session_task_digest": "d" * 64, "executor_session_answers": ["k1"], "executor_session_route_said": "x"}

    def test_every_legacy_key_moves_into_a_slot_and_goes(self):
        state = dict(self.LEGACY, status="running")
        self.assertTrue(sessions.migrate_state(state, "2026-10-23T00:00:00Z"))
        self.assertEqual(sorted(set(state) & set(sessions.SESSION_FIELDS)), [])
        slot = state["executor_sessions"]["W3"]
        self.assertEqual((slot["session"], slot["route"], slot["provider"], slot["last_item"], slot["task_digest"],
                          slot["answers"], slot["fingerprint"]), ("s7", "claude-code/m/high", "claude-code", "W3", "d" * 64,
                                                                  ["k1"], {}))
        self.assertIn("*", state["executor_sessions"])  # a shared run finds it too
        self.assertEqual(state["executor_session_route_said"], "x")  # not a session field: it silences a route notice
        self.assertFalse(sessions.migrate_state(state, "later"))  # once

    def test_a_state_without_a_session_just_loses_the_keys(self):
        state = {"executor_session_answers": ["k"]}
        self.assertTrue(sessions.migrate_state(state, "t"))
        self.assertEqual(state, {})
        self.assertFalse(sessions.migrate_state({"status": "running"}, "t"))

    def test_a_migrated_slot_resumes_as_before_and_takes_an_identity_when_kept(self):
        owner, base = stub({})
        self.addCleanup(shutil.rmtree, base, True)
        owner.state.update(self.LEGACY)
        sessions.migrate_state(owner.state, "2026-10-23T00:00:00Z")
        item = piece("W3")
        fp = sessions.fingerprint(owner, item, CLAUDE)
        self.assertEqual(sessions.session_decision(owner, item, CLAUDE, fp), ("resume", "s7"))
        owner.store = types.SimpleNamespace(mutating=mock.MagicMock())
        owner._save = lambda: None
        owner._shared_session = lambda *args: True
        sessions.keep_session(owner, item, "executor", CLAUDE, types.SimpleNamespace(error=None, session="s8"),
                              decision={"action": "resume", "value": "s7", "fingerprint": fp})
        slot = owner.state["executor_sessions"]["W3"]
        self.assertEqual((slot["session"], slot["fingerprint"], slot["rounds"]), ("s8", fp, 1))
        self.assertNotIn("migrated", slot)


class FollowupTests(unittest.TestCase):
    def setUp(self):
        self.owner, self.base = stub({})
        self.addCleanup(shutil.rmtree, self.base, True)

    def slot(self, item, route=CLAUDE) -> dict:
        return {"session": "s2", "provider": route["provider"], "route": sessions.label(route), "last_item": item.ref,
                "fingerprint": sessions.fingerprint(self.owner, item, route)}

    def followup(self, ref: dict):
        item = piece("followup@1")
        item.input_doc = {"provenance": {"kind": "review_followup", "session_ref": ref}}
        return item

    def reference(self, last="W2", **change) -> dict:
        slot = self.slot(piece(last))
        return {"run": "cnd-old", "item": last, "session": "s2", "provider": "claude-code", "items": ["W1", last],
                "fingerprint_digest": sessions.identity_digest(slot["fingerprint"]), **change}

    def test_session_ref_is_the_session_of_the_last_piece_of_the_group_without_its_attempt(self):
        owner = types.SimpleNamespace(run_id="cnd-old", state={"executor_sessions": {
            "W1": dict(self.slot(piece("W1")), session="s1"), "W2": self.slot(piece("W2"))}})
        found = review_plan.session_ref(owner, ["W1", "W2"])
        self.assertEqual({key: found[key] for key in ("run", "item", "session", "provider", "items")},
                         {"run": "cnd-old", "item": "W2", "session": "s2", "provider": "claude-code", "items": ["W1", "W2"]})
        self.assertEqual(found["fingerprint_digest"], sessions.identity_digest(self.slot(piece("W9"))["fingerprint"]))
        owner.state["executor_sessions"]["W2"].pop("session")  # a lost session leaves the origin of the group alone
        self.assertEqual(review_plan.session_ref(owner, ["W1", "W2"]),
                         {"run": "cnd-old", "item": "W2", "items": ["W1", "W2"]})
        self.assertEqual(review_plan.session_ref(types.SimpleNamespace(run_id="r", state={}), ["W1"]),
                         {"run": "r", "item": "W1", "items": ["W1"]})

    def test_a_matching_session_ref_resumes_it_for_the_followup(self):
        item = self.followup(self.reference())
        fp = sessions.fingerprint(self.owner, item, CLAUDE)
        self.assertEqual(sessions.session_decision(self.owner, item, CLAUDE, fp), ("resume", "s2"))
        self.assertEqual(sessions.decide(self.owner, item, "executor.1", "executor", CLAUDE)["reuse"], "followup")

    def test_another_provider_or_identity_is_a_followup_mismatch(self):
        for change in ({"provider": "codex"}, {"fingerprint_digest": "sha256:" + "0" * 64}):
            with self.subTest(change):
                item = self.followup(self.reference(**change))
                fp = sessions.fingerprint(self.owner, item, CLAUDE)
                self.assertEqual(sessions.session_decision(self.owner, item, CLAUDE, fp), ("fresh", "followup_mismatch"))

    def test_a_followup_without_a_session_ref_is_a_first_round(self):
        item = piece("followup@1")
        item.input_doc = {"provenance": {"kind": "review_followup"}}
        self.assertEqual(sessions.session_decision(self.owner, item, CLAUDE, sessions.fingerprint(self.owner, item, CLAUDE)),
                         ("fresh", "first_round"))

    def old_run(self, state=None) -> None:
        runs = self.base / "runs"
        old = runs / "cnd-old"
        for ref, summary in (("W1", "made the parser"), ("W2", "made the writer")):
            (old / ref).mkdir(parents=True, exist_ok=True)
            (old / ref / "register-report.json").write_text(json.dumps({"summary": summary, "changed_paths": [f"{ref}.py"]}))
        (old / "state.json").write_text(state if state is not None else json.dumps({"items": {
            "W1": {"steps": {"commit": {"status": "done", "result": {"outcome": "committed", "sha": "a" * 40}}}},
            "W2": {"steps": {"commit": {"status": "done", "result": {"outcome": "committed", "sha": "b" * 40}}}}}}),
            encoding="utf-8")
        self.owner.directory = runs / "cnd-new"
        self.owner.run_doc = {"items": ["followup@1"]}

    def assert_handoff_of_both(self, text: str) -> None:
        for expected in ("### Handoff of `W1` (commit aaaaaaaaaaaa)", "### Handoff of `W2` (commit bbbbbbbbbbbb)",
                         "made the parser", "made the writer", "fresh session"):
            self.assertIn(expected, text)

    def test_a_mismatch_hands_off_every_piece_of_the_group_from_the_state_of_the_old_run(self):
        self.old_run()
        item = self.followup(self.reference(fingerprint_digest="sha256:" + "0" * 64))
        self.assert_handoff_of_both(execute.batch_note(self.owner, item))
        matching = self.followup(self.reference())
        self.assertEqual(execute.batch_note(self.owner, matching), "")  # it resumes: nothing to hand off

    def test_every_fresh_start_of_a_followup_hands_off_the_group(self):
        self.old_run()
        origin = {"run": "cnd-old", "item": "W2", "items": ["W1", "W2"]}  # the last piece kept no session
        cases = (("per-item", None, self.reference()), ("handoff", "unknown", self.reference()),
                 ("handoff", None, origin), ("handoff", None, self.reference(fingerprint_digest="sha256:" + "0" * 64)))
        for mode, capability, ref in cases:
            with self.subTest(mode=mode, capability=capability, ref=sorted(ref)):
                item = self.followup(ref)
                item.options["session"]["executor"] = mode
                with mock.patch.object(sessions, "resume_capability", return_value=capability or "adapted"):
                    self.assert_handoff_of_both(execute.batch_note(self.owner, item))

    def test_a_damaged_state_of_the_old_run_is_diagnosed_not_swallowed(self):
        item = self.followup(self.reference(fingerprint_digest="sha256:" + "0" * 64))
        for text, code in (("[]", "STATE_INVALID"), ("{invalid-json", "STATE_CORRUPT")):
            with self.subTest(text):
                self.old_run(text)
                with self.assertRaises(engine.Stop) as raised:
                    execute.batch_note(self.owner, item)
                self.assertEqual(raised.exception.code, code)
        shutil.rmtree(self.base / "runs")
        self.old_run()
        (self.base / "runs" / "cnd-old" / "state.json").unlink()
        self.assertEqual(execute.batch_note(self.owner, item), "")  # no state, nothing to hand off


class RouteResumeTests(unittest.TestCase):
    """A route resumes only through a command line that exists for it."""

    def test_a_codex_route_of_the_users_own_command_line_starts_fresh_and_a_catalog_one_resumes(self):
        owner, base = stub({})
        self.addCleanup(shutil.rmtree, base, True)
        item = piece()
        own = {"provider": "codex", "model": "m", "effort": "high", "argv": ["codex", "-a", "never", "exec", "--json", "-"]}
        catalog = dict(own, resume_argv=["codex", "-a", "never", "exec", "resume", "{session}", "--json", "-"])
        owner.state["executor_sessions"] = {"W1": {"session": "thread-1", "provider": "codex", "last_item": "W1",
                                                   "fingerprint": sessions.fingerprint(owner, item, own)}}
        self.assertFalse(sessions.shared_session(owner, item, "executor", own))
        decision = sessions.decide(owner, item, "executor.2", "executor", own)
        self.assertEqual((decision["action"], decision["value"]), ("fresh", "provider_unsupported"))
        self.assertEqual(sessions.resume_args(owner, item, "executor", own), [])  # not a --resume that codex does not know
        self.assertTrue(sessions.shared_session(owner, item, "executor", catalog))
        self.assertEqual(sessions.resume_args(owner, item, "executor", catalog), ["thread-1"])

    def test_a_provider_without_resume_argv_in_the_catalog_resumes_with_the_flag(self):
        self.assertTrue(sessions.resume_buildable(CLAUDE))
        self.assertFalse(sessions.resume_buildable({"provider": "grok"}))
        self.assertTrue(sessions.resume_buildable({"provider": "grok", "resume_argv": ["grok", "--resume", "{session}"]}))


class MigratedAliasTests(unittest.TestCase):
    """The copies of a migrated session under the other keys never resume it unchecked (I7)."""

    LEGACY = {"executor_session": "s1", "executor_session_route": "claude-code/m/high", "executor_session_item": "W1",
              "executor_session_task_digest": "task", "executor_session_answers": ["a"]}

    def kept(self, mode: str):
        """A migrated session resumed and kept once in ``mode``, with the identity ``old`` it continues under."""
        owner, base = stub({})
        self.addCleanup(shutil.rmtree, base, True)
        owner.state.update(self.LEGACY)
        sessions.migrate_state(owner.state, "2026-10-23T00:00:00Z")
        owner.store = types.SimpleNamespace(mutating=contextlib.nullcontext)
        owner._save = lambda: None
        item = piece(mode=mode)
        with self.identity(instructions="a", authority="old"):
            decision = sessions.decide(owner, item, "executor.1", "executor", CLAUDE)
            self.assertEqual((decision["action"], decision["value"]), ("resume", "s1"))
            sessions.keep_session(owner, item, "executor", CLAUDE, types.SimpleNamespace(error=None, session="s1"),
                                  decision=decision)
        return owner, item

    @staticmethod
    def identity(instructions: str, authority: str):
        stack = contextlib.ExitStack()
        stack.enter_context(mock.patch.object(sessions, "instructions_digest", return_value="sha256:" + instructions * 64))
        stack.enter_context(mock.patch.object(sessions, "identity_inputs",
                                              return_value={"authority_digest": authority, "isolation_home": ""}))
        return stack

    def test_a_changed_identity_is_never_resumed_by_the_other_mode_either(self):
        for first, second in (("handoff", "shared"), ("shared", "handoff")):
            for instructions, authority in (("a", "old"), ("b", "old"), ("a", "new")):  # unchanged, then each changed
                with self.subTest(first=first, second=second, instructions=instructions, authority=authority):
                    owner, item = self.kept(first)
                    self.assertEqual([key for key, slot in owner.state["executor_sessions"].items() if slot.get("migrated")], [])
                    self.assertEqual(sorted(owner.state["executor_sessions"]), ["*"] if first == "shared" else ["W1"])
                    owner.state = json.loads(json.dumps(owner.state))  # save, load
                    item.options["session"]["executor"] = second
                    with self.identity(instructions, authority):
                        decision = sessions.decide(owner, item, "executor.2", "executor", CLAUDE)
                    self.assertEqual((decision["action"], decision["value"]), ("fresh", "first_round"))

    def test_the_same_mode_still_refuses_a_changed_identity_after_the_migration(self):
        for instructions, authority, field in (("b", "old", "instructions_digest"), ("a", "new", "authority_digest")):
            with self.subTest(field):
                owner, item = self.kept("handoff")
                with self.identity(instructions, authority):
                    decision = sessions.decide(owner, item, "executor.2", "executor", CLAUDE)
                self.assertEqual((decision["action"], decision["value"]), ("fresh", f"fingerprint_changed:{field}"))

    def test_a_failed_attempt_on_a_migrated_session_drops_its_copies_too(self):
        owner, base = stub({})
        self.addCleanup(shutil.rmtree, base, True)
        owner.state.update(self.LEGACY)
        sessions.migrate_state(owner.state, "2026-10-23T00:00:00Z")
        self.assertEqual(sorted(owner.state["executor_sessions"]), ["*", "W1"])
        owner.store = types.SimpleNamespace(mutating=contextlib.nullcontext)
        owner._save = lambda: None
        sessions.keep_session(owner, piece(), "executor", CLAUDE, types.SimpleNamespace(error="ROLE_FAILED", session=None))
        self.assertEqual(sorted(owner.state["executor_sessions"]), ["W1"])
        self.assertNotIn("session", owner.state["executor_sessions"]["W1"])


class ObserverTests(unittest.TestCase):
    def test_the_report_counts_resumed_sessions_by_reuse_and_fresh_ones_by_reason(self):
        def line(code, message):
            return {"event": "info", "reason_code": code, "message": message}
        lines = [line("SESSION_FRESH", "a fresh session starts; reason=first_round"),
                 line("SESSION_RESUMED", "session s1 resumed; reuse=correction"),
                 line("SESSION_RESUMED", "session s1 resumed; reuse=correction"),
                 line("SESSION_FRESH", "a fresh session starts; reason=fingerprint_changed:authority_digest"),
                 line("SESSION_ROUTE_CHANGED", "x"), {"event": "stage.end"}]
        self.assertEqual(metrics.session_totals(lines),
                         {"resumed": {"correction": 2},
                          "fresh": {"first_round": 1, "fingerprint_changed:authority_digest": 1}})
        self.assertEqual(metrics.session_totals([]), {"resumed": {}, "fresh": {}})


class SessionRunTests(ConductorCase):
    """The decisions in a whole run, through the fake executor."""

    def setUp(self):
        super().setUp()
        self.write_config(extra=HANDOFF_CONFIG)  # the default is `shared`; these tests are about `handoff`

    RED = {"result": report("W1")}  # no file written: the check is red and the round is corrected

    def argv(self, number: int) -> list:
        return json.loads((self.fake / f"executor-{number}.argv").read_text(encoding="utf-8"))

    def sessions(self, err: str) -> list:
        return [(line["reason_code"], line["message"], line.get("stage")) for line in self.lines(err)
                if line.get("reason_code") in ("SESSION_RESUMED", "SESSION_FRESH")]

    def test_a_retry_of_an_earlier_piece_resumes_its_own_session_after_a_later_piece_ran(self):
        self.set_items({"W1": {}, "W2": {}})
        self.script({"executor": [asking(dict(ASK)), executor_ok("W2"), executor_ok("W1")], "reviewer": [GREEN, GREEN]})
        options = self.project.parent / "report.json"
        options.write_text(json.dumps({"on_blocked": "report"}), encoding="utf-8")
        code, _, err = self.run_items("W1", "W2", extra=("--options", options))
        self.assertEqual(self.calls("executor"), 2, err)
        run = self.run_dir(err).name
        slots = self.state(err)["executor_sessions"]
        self.assertEqual({ref: slots[ref]["session"] for ref in ("W1", "W2")},
                         {"W1": "executor-session-1", "W2": "executor-session-2"})
        self.conduct("answer", "--run", run, "--item", "W1", "--question", "Q1", "--option", "rename")
        doc = self.source()
        doc["items"]["W1"]["status"] = "todo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        code, _, again = self.conduct("resume", "--run", run, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(again)), (0, ("finished", None)), again)
        third = self.argv(3)
        self.assertEqual(third[third.index("--resume") + 1], "executor-session-1")  # not the session of W2
        self.assertEqual([row[0] for row in self.sessions(again)], ["SESSION_RESUMED"])
        self.assertIn("reuse=retry", self.sessions(again)[0][1])

    def test_the_journal_says_why_each_round_is_fresh_or_resumed_and_the_event_carries_it(self):
        self.script({"executor": [self.RED, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        rows = self.sessions(err)
        self.assertEqual([(row[0], row[2]) for row in rows], [("SESSION_FRESH", "executor.1"), ("SESSION_RESUMED", "executor.2")])
        self.assertIn("reason=first_round", rows[0][1])
        self.assertIn("reuse=correction", rows[1][1])
        stored, _ = journal.read_events(self.project)
        started = [event.data["session"] for event in stored
                   if event.type == "orch.agent.started" and event.data["role"] == "executor"]
        self.assertEqual(started, [{"resumed": False, "reason": "first_round"}, {"resumed": True, "reason": "correction"}])
        slot = self.state(err)["executor_sessions"]["W1"]
        self.assertEqual((slot["session"], slot["rounds"], slot["provider"]), ("executor-session-2", 2, "claude-code"))
        self.assertEqual(slot["fingerprint_digest"], sessions.fingerprint_digest(slot["fingerprint"]))

    def test_a_changed_authority_between_rounds_starts_a_fresh_session(self):
        marker = self.project.parent / "authority-changed"
        self.script({"executor": [dict(self.RED, write={str(marker): "x"}), executor_ok("W1")], "reviewer": [GREEN]})

        def inputs(owner, item, route):
            return {"authority_digest": "sha256:" + ("b" if marker.exists() else "a") * 64, "isolation_home": ""}

        with mock.patch.object(sessions, "identity_inputs", inputs):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("--resume", self.argv(2))
        self.assertIn("Create the output of W1.", self.prompt("executor", 2))  # the whole task, not the delta
        self.assertEqual(self.sessions(err)[1][0], "SESSION_FRESH")
        self.assertIn("reason=fingerprint_changed:authority_digest", self.sessions(err)[1][1])
        stored, _ = journal.read_events(self.project)
        started = [event.data["session"] for event in stored
                   if event.type == "orch.agent.started" and event.data["role"] == "executor"]
        self.assertEqual(started[1], {"resumed": False, "reason": "fingerprint_changed:authority_digest"})

    def test_changed_instructions_between_rounds_start_a_fresh_session(self):
        marker = self.project.parent / "instructions-changed"
        self.script({"executor": [dict(self.RED, write={str(marker): "x"}), executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(sessions, "instructions_digest",
                               lambda owner: "sha256:" + ("b" if marker.exists() else "a") * 64):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("--resume", self.argv(2))
        self.assertIn("reason=fingerprint_changed:instructions_digest", self.sessions(err)[1][1])

    def test_per_item_says_so_every_round(self):
        self.script({"executor": [self.RED, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--no-batch",))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual([row[0] for row in self.sessions(err)], ["SESSION_FRESH", "SESSION_FRESH"])
        self.assertTrue(all("reason=per_item_mode" in row[1] for row in self.sessions(err)))

    def test_an_expired_session_starts_fresh(self):
        self.script({"executor": [self.RED, executor_ok("W1")], "reviewer": [GREEN]})
        options = self.project.parent / "idle.json"
        options.write_text(json.dumps({"session": {"max_idle_s": 1}}), encoding="utf-8")
        with mock.patch.object(sessions, "_age_s", return_value=10.0):
            code, _, err = self.run_items("W1", extra=("--options", options))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("--resume", self.argv(2))
        self.assertIn("reason=idle_expired", self.sessions(err)[1][1])

    def test_a_lost_session_is_fresh_with_provider_error_and_the_slot_keeps_no_id(self):
        self.script({"executor": [self.RED, {"exit": 3}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertIn("reason=provider_error", self.sessions(err)[2][1])

    def test_a_state_of_the_single_slot_is_migrated_once_and_resumed_as_before(self):
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (4, ("waiting", "WAITING_DECISION")), err)
        directory = self.run_dir(err)
        path = directory / "state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        slot = state.pop("executor_sessions")["W1"]  # what the conductor before P7.4 wrote
        state.update(executor_session=slot["session"], executor_session_item="W1", executor_session_route=slot["route"],
                     executor_session_task_digest=slot["task_digest"], executor_session_answers=[])
        state["items"]["W1"].pop("session_base", None)
        path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(records.read(path, "state")["executor_session"], slot["session"])  # the old document is valid
        self.conduct("answer", "--run", directory.name, "--item", "W1", "--question", "Q1", "--option", "rename")
        doc = self.source()
        doc["items"]["W1"]["status"] = "todo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        code, _, again = self.conduct("resume", "--run", directory.name, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(again)), (0, ("finished", None)), again)
        migrated = [line for line in self.lines(again) if line.get("reason_code") == "SESSION_STATE_MIGRATED"]
        self.assertEqual(len(migrated), 1)
        second = self.argv(2)
        self.assertEqual(second[second.index("--resume") + 1], slot["session"])
        saved = records.read(path, "state")
        self.assertEqual(sorted(set(saved) & set(sessions.SESSION_FIELDS)), [])
        self.assertEqual(saved["executor_sessions"]["W1"]["session"], "executor-session-2")
        self.assertTrue(saved["executor_sessions"]["W1"]["fingerprint"])  # it has an identity now


if __name__ == "__main__":
    unittest.main()
