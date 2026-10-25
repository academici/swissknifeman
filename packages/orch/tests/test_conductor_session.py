"""One executor session for the pieces of a run (``session.executor``): the executor of the next piece, and of every
correction round, resumes the session of the previous executor (``--resume``), and the first prompt names the pieces
of the run; ``per-item`` (``--no-batch``) starts a fresh session each time."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest import mock

from orch.conductor import engine, options, process, prompts
import sys

from tests.test_conductor import FIXTURES, GREEN, ROLES, ConductorCase, executor_ok, report
from tests.test_conductor_prompts import fixture


HANDOFF_CONFIG = '[orch.conductor]\nsession_executor = "handoff"\n'  # the default is `shared`


class SessionOptionsTests(unittest.TestCase):
    def test_shared_is_the_default(self):
        self.assertEqual(options.DEFAULTS["session"], {"executor": "shared", "max_idle_s": 0})

    def test_a_layer_can_choose_per_item_and_a_bad_value_is_refused(self):
        merged = options.merge(options.DEFAULTS, {"session": {"executor": "per-item"}})
        self.assertEqual(merged["session"]["executor"], "per-item")
        from orch.conductor import contract
        self.assertEqual(contract.problems({"session": {"executor": "per-item"}}, "run-options"), [])
        self.assertTrue(contract.problems({"session": {"executor": "forever"}}, "run-options"))
        self.assertTrue(contract.problems({"session": {"reviewer": "shared"}}, "run-options"))


class BatchBlockTests(unittest.TestCase):
    def test_no_note_is_no_block_and_a_note_is_a_supporting_run_rules_block(self):
        plain = prompts.executor(fixture("adhoc"), item="W1", step="executor.1")
        noted = prompts.executor(fixture("adhoc"), item="W1", step="executor.1", batch="## Run batch\n\nW1, W2")
        self.assertEqual(len(noted), len(plain) + 1)
        block = [b for b in noted if b.text.startswith("## Run batch")][0]
        self.assertEqual((block.kind, block.origin), ("run_rules", "conductor"))


class SharedSessionTests(ConductorCase):
    def argv(self, number: int) -> list:
        return json.loads((self.fake / f"executor-{number}.argv").read_text(encoding="utf-8"))

    def two_items(self):
        self.set_items({"W1": {}, "W2": {}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN, GREEN]})

    def shared(self) -> tuple:
        path = self.project.parent / "shared.json"
        path.write_text(json.dumps({"session": {"executor": "shared"}}), encoding="utf-8")
        return ("--options", path)

    def test_the_second_piece_resumes_the_session_of_the_first(self):
        self.two_items()
        code, _, err = self.run_items("W1", "W2", extra=self.shared())
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 2)
        self.assertNotIn("--resume", self.argv(1))
        self.assertEqual(self.argv(2)[self.argv(2).index("--resume") + 1], "executor-session-1")
        self.assertEqual(self.state(err)["executor_sessions"]["*"]["session"], "executor-session-2")
        self.assertNotIn("executor_session", self.state(err))  # the deprecated key is no longer written

    def with_no_persistence(self):
        roles = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        roles["executor"].append("--no-session-persistence")  # what the launch catalog gives the executor
        self.write_config(argv=roles)
        self.two_items()

    def test_a_shared_executor_keeps_its_session_on_disk(self):
        self.with_no_persistence()
        code, _, err = self.run_items("W1", "W2", extra=self.shared())
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("--no-session-persistence", self.argv(1))

    def test_per_item_leaves_the_flag_as_the_catalog_has_it(self):
        self.with_no_persistence()
        code, _, err = self.run_items("W1", "W2", extra=("--no-batch",))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertIn("--no-session-persistence", self.argv(1))

    def test_the_prompts_name_the_run_and_say_whether_the_session_is_resumed(self):
        self.two_items()
        self.run_items("W1", "W2", extra=self.shared())
        first, second = self.prompt("executor", 1), self.prompt("executor", 2)
        self.assertIn("## Run batch", first)
        self.assertIn("`W1`", first)
        self.assertIn("`W2`", first)
        self.assertIn("You start with W1", first)
        self.assertIn("You are resuming that session", second)

    def test_per_item_starts_a_fresh_session_and_adds_no_note(self):
        self.two_items()
        code, _, err = self.run_items("W1", "W2", extra=("--no-batch",))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("--resume", self.argv(2))
        self.assertNotIn("## Run batch", self.prompt("executor", 1))
        self.assertNotIn("executor_sessions", self.state(err))  # a per-item session is kept nowhere

    def test_one_piece_alone_has_no_note_and_no_resume(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("## Run batch", self.prompt("executor", 1))
        self.assertNotIn("--resume", self.argv(1))




class HandoffSessionTests(ConductorCase):
    """``handoff``: a new piece starts a fresh session with the handoff of the earlier pieces; its correction
    rounds resume its own session."""

    def setUp(self):
        super().setUp()
        self.write_config(extra=HANDOFF_CONFIG)  # the default is `shared`; these tests are about `handoff`

    def argv(self, number: int) -> list:
        return json.loads((self.fake / f"executor-{number}.argv").read_text(encoding="utf-8"))

    def test_the_second_piece_starts_fresh_with_the_handoff_of_the_first(self):
        self.set_items({"W1": {}, "W2": {}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN, GREEN]})
        code, _, err = self.run_items("W1", "W2")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("--resume", self.argv(2))
        first, second = self.prompt("executor", 1), self.prompt("executor", 2)
        self.assertIn("You start W1 in a fresh session", first)
        self.assertNotIn("Handoff of", first)
        self.assertIn("You start W2 in a fresh session", second)
        self.assertIn("### Handoff of `W1` (commit ", second)
        self.assertEqual(self.state(err)["executor_sessions"]["W2"]["last_item"], "W2")
        self.assertEqual(sorted(self.state(err)["executor_sessions"]), ["W1", "W2"])  # a slot of its own for each piece

    def test_a_correction_round_resumes_the_session_of_its_own_piece_only(self):
        from types import SimpleNamespace
        from orch.conductor.infrastructure import roles, sessions
        owner = engine.Conductor.__new__(engine.Conductor)
        owner.project = owner.directory = self.project
        route = {"provider": "claude-code", "model": "m", "effort": "high"}
        item = SimpleNamespace(ref="W2", options={"session": {"executor": "handoff"}}, state={}, claim={}, input_doc={})
        owner.progress = SimpleNamespace(emit=lambda *a, **k: None)
        owner.state = {"executor_sessions": {"W2": {"session": "s1", "provider": "claude-code", "last_item": "W2",
                                                    "fingerprint": sessions.fingerprint(owner, item, route)}}}
        self.assertEqual(roles.resume_args(owner, item, "executor", route), ["--resume", "s1"])
        item.ref = "W3"
        self.assertEqual(roles.resume_args(owner, item, "executor", route), [])  # another piece: no slot of its own
        item.options["session"]["executor"] = "shared"
        owner.state["executor_sessions"]["*"] = dict(owner.state["executor_sessions"]["W2"],
                                                     fingerprint=sessions.fingerprint(owner, item, route))
        self.assertEqual(roles.resume_args(owner, item, "executor", route), ["--resume", "s1"])


class ResumedBlocksTests(unittest.TestCase):
    """``prompts.executor_resumed`` is the delta prompt of a round in a resumed session; ``task_digest`` says whether the
    session holds the task."""

    def test_the_delta_prompt_has_the_round_and_the_contract_and_not_the_task(self):
        blocks = prompts.executor_resumed(item="W1", step="executor.2", correction="the checks are red", fix="",
                                          answers=[{"id": "alpha", "text": "which?", "answer": "this", "by": "owner"}],
                                          interrupted="it was interrupted", changed_paths=["a.py", "b.py"])
        self.assertEqual([block.kind for block in blocks],
                         ["resumed", "answers", "correction", "interrupted", "changed", "progress", "result_contract"])
        text = prompts.render(blocks)
        self.assertIn("You continue piece W1 in the same session", text)
        self.assertIn("the checks are red", text)
        self.assertIn("alpha", text)
        self.assertIn("`a.py`, `b.py`", text)
        self.assertIn("```stage-report", text)
        self.assertNotIn("Repository rules", text)

    def test_nothing_to_say_leaves_only_the_continuation_progress_and_contract(self):
        blocks = prompts.executor_resumed(item="W1", step="executor.2")
        self.assertEqual([block.kind for block in blocks], ["resumed", "progress", "result_contract"])

    def full(self, **extra) -> list:
        return prompts.executor(fixture("adhoc"), item="W1", step="executor.1", **extra)

    def test_the_task_digest_ignores_the_round_and_changes_with_the_task(self):
        first = prompts.task_digest(self.full())
        again = prompts.task_digest(prompts.executor(fixture("adhoc"), item="W1", step="executor.2", correction="red",
                                                     answers=[{"id": "Q", "text": "t", "answer": "a", "by": "x"}],
                                                     batch="## Run batch\n\nresuming"))
        self.assertEqual(first, again)
        self.assertNotEqual(first, prompts.task_digest(self.full(rules=["another rule"])))
        self.assertNotEqual(first, prompts.task_digest(self.full(repo_rules="a repository rule")))
        self.assertNotEqual(first, prompts.task_digest(self.full(skill_texts={"s": "a skill text"})))
        self.assertNotEqual(first, prompts.task_digest(self.full(stub=("stub:x", "## Extra\n\ntext"))))
        self.assertNotEqual(first, prompts.task_digest(self.full(scout_text="a map")))

    def test_the_manifest_of_a_delta_prompt_says_so_and_stays_valid(self):
        from orch.conductor import contract
        route = {"provider": "claude-code", "model": "m", "effort": "high"}
        digest = prompts.task_digest(self.full())
        doc = prompts.manifest(prompts.executor_resumed(item="W1", step="executor.2", correction="red"), step="executor.2",
                               role="executor", route=route, resumed_session=True, digest=digest)
        self.assertEqual((doc["resumed_session"], doc["task_digest"]), (True, digest))
        self.assertEqual(contract.problems(doc, "prompt-manifest"), [])
        plain = prompts.manifest(self.full(), step="executor.1", role="executor", route=route)
        self.assertNotIn("resumed_session", plain)
        self.assertEqual(contract.problems(plain, "prompt-manifest"), [])


class ResumedRoundTests(ConductorCase):
    """A correction round continues the session with the delta prompt; every doubt gives the whole prompt."""

    def setUp(self):
        super().setUp()
        self.write_config(extra=HANDOFF_CONFIG)  # the default is `shared`; these tests are about `handoff`

    RED = {"result": report("W1")}  # no file written: the check is red and the round is corrected

    def argv(self, number: int) -> list:
        return json.loads((self.fake / f"executor-{number}.argv").read_text(encoding="utf-8"))

    def item_dir(self, err: str, ref: str = "W1") -> Path:
        return self.run_dir(err) / ref

    def manifest(self, err: str, key: str, ref: str = "W1") -> dict:
        return json.loads((self.item_dir(err, ref) / "prompts" / f"{key}.manifest.json").read_text(encoding="utf-8"))

    def test_a_correction_round_sends_only_the_correction_and_the_contract(self):
        self.script({"executor": [self.RED, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.argv(2)[self.argv(2).index("--resume") + 1], "executor-session-1")
        first, second = self.prompt("executor", 1), self.prompt("executor", 2)
        resumed = (self.item_dir(err) / "prompts" / "executor.2.resumed.md").read_text(encoding="utf-8")
        self.assertEqual(second, resumed)
        self.assertIn("These acceptance checks are red", second)
        self.assertIn("```stage-report", second)
        self.assertIn("You continue piece W1 in the same session", second)
        self.assertNotIn(first.splitlines()[0], second)  # not the text of the role
        self.assertNotIn("Create the output of W1.", second)  # not the execution-input
        self.assertLess(len(second), len(first) // 2)
        full = (self.item_dir(err) / "prompts" / "executor.2.md").read_text(encoding="utf-8")  # the full prompt is kept too
        self.assertIn(first.splitlines()[0], full)
        self.assertIn("Create the output of W1.", full)
        manifest = self.manifest(err, "executor.2")
        self.assertTrue(manifest["resumed_session"])
        self.assertEqual([row["kind"] for row in manifest["blocks"]],
                         ["resumed", "correction", "progress", "result_contract"])
        self.assertEqual(manifest["task_digest"], self.manifest(err, "executor.1")["task_digest"])
        self.assertNotIn("resumed_session", self.manifest(err, "executor.1"))
        self.assertFalse((self.item_dir(err) / "prompts" / "executor.1.resumed.md").exists())
        self.assertEqual(self.state(err)["executor_sessions"]["W1"]["task_digest"], manifest["task_digest"])

    def test_a_lost_session_gives_the_next_attempt_the_whole_prompt_in_a_fresh_session(self):
        self.script({"executor": [self.RED, {"exit": 3}, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(self.calls("executor"), 3)
        self.assertIn("--resume", self.argv(2))
        failed = [line for line in self.lines(err) if line.get("reason_code") == "SESSION_RESUME_FAILED"]
        self.assertEqual(len(failed), 1, err)
        self.assertEqual((failed[0]["item"], failed[0]["stage"]), ("W1", "executor.2"))
        self.assertIn("claude-code", failed[0]["message"])
        self.assertNotIn("--resume", self.argv(3))
        third = self.prompt("executor", 3)
        self.assertEqual(third, (self.item_dir(err) / "prompts" / "executor.2.md").read_text(encoding="utf-8"))
        self.assertIn("Create the output of W1.", third)  # the task again: this session has none
        self.assertIn("These acceptance checks are red", third)
        self.assertFalse((self.item_dir(err) / "prompts" / "executor.2.resumed.md").exists())
        self.assertNotIn("resumed_session", self.manifest(err, "executor.2"))

    def test_a_rebuilt_input_gives_the_continued_session_the_whole_prompt(self):
        state = self.source()
        state["items"]["W1"].update(status="in_progress", goal="Create the amended output of W1.")
        amend = {"result": report("W1"), "write": {str(self.state_file): json.dumps(state)}}
        self.script({"executor": [amend, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertIn("--resume", self.argv(2))  # the session goes on ...
        second = self.prompt("executor", 2)
        self.assertIn("Create the amended output of W1.", second)  # ... with the new task, whole
        self.assertNotIn("You continue piece", second)
        self.assertNotEqual(self.manifest(err, "executor.2")["task_digest"], self.manifest(err, "executor.1")["task_digest"])
        self.assertNotIn("resumed_session", self.manifest(err, "executor.2"))
        self.assertFalse((self.item_dir(err) / "prompts" / "executor.2.resumed.md").exists())

    def test_the_first_round_of_the_next_piece_continues_a_shared_session_with_the_whole_prompt(self):
        self.set_items({"W1": {}, "W2": {}})
        self.script({"executor": [executor_ok("W1"), {"result": report("W2")}, executor_ok("W2")], "reviewer": [GREEN, GREEN]})
        path = self.project.parent / "shared.json"
        path.write_text(json.dumps({"session": {"executor": "shared"}}), encoding="utf-8")
        code, _, err = self.run_items("W1", "W2", extra=("--options", path))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertIn("--resume", self.argv(2))  # W2 starts in the session of W1 ...
        second = self.prompt("executor", 2)
        self.assertIn("Create the output of W2.", second)  # ... with the execution-input of W2
        self.assertIn("You are resuming that session", second)
        self.assertNotIn("resumed_session", self.manifest(err, "executor.1", "W2"))
        self.assertIn("--resume", self.argv(3))  # its correction round is the delta
        third = self.prompt("executor", 3)
        self.assertIn("You continue piece W2 in the same session", third)
        self.assertNotIn("Create the output of W2.", third)
        self.assertTrue(self.manifest(err, "executor.2", "W2")["resumed_session"])

    def test_a_per_item_session_is_never_resumed_and_gets_the_whole_prompt(self):
        self.script({"executor": [self.RED, executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--no-batch",))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("--resume", self.argv(2))
        self.assertIn("Create the output of W1.", self.prompt("executor", 2))

    def test_an_answer_the_session_has_seen_is_not_sent_again(self):
        from orch.conductor.stages import execute
        seen = {"id": "alpha", "text": "which?", "answer": "this", "by": "owner"}
        new = {"id": "beta", "text": "how?", "answer": "so", "by": "owner"}
        owner = engine.Conductor.__new__(engine.Conductor)
        owner.state = {"executor_sessions": {"W1": {"session": "s1", "answers": [execute.answer_key(seen)]}}}
        item = mock.Mock(ref="W1", state={"steps": {}},
                         options={"checks": {"executor_runs_checks": False}, "session": {"executor": "handoff"}})
        blocks = owner._resumed_prompt(item, "executor.2", "", "", "", [seen, new])
        text = prompts.render(blocks)
        self.assertIn("beta", text)
        self.assertNotIn("alpha", text)
        self.assertIsNone(owner._resumed_prompt(item, "executor.2", "", "", "", [seen]))  # nothing new, nothing asked


class CodexResumeTests(ConductorCase):
    """A Codex executor continues its thread in a correction round: ``codex exec resume <thread> ...``, the sandbox mode
    as a ``-c`` override (the subcommand has no ``--sandbox``)."""

    RED = {"codex": True, "result": report("W1")}

    def setUp(self):
        super().setUp()
        bin_dir = self.project.parent / "bin"
        bin_dir.mkdir()
        shim = bin_dir / "codex"
        # the probes of the isolation profile (``--version``, ``exec --help``) are answered, not played as a role
        shim.write_text('#!/bin/sh\ncase "$*" in --version) echo "codex-cli 0.0.0"; exit 0;; '
                        '*--help) echo "--ignore-user-config"; exit 0;; esac\n'
                        f'exec "{sys.executable}" "{FIXTURES / "fake_role.py"}" executor "$@"\n', encoding="utf-8")
        shim.chmod(0o755)
        patcher = mock.patch.dict("os.environ", {"PATH": f"{bin_dir}:{__import__('os').environ['PATH']}"})
        patcher.start()
        self.addCleanup(patcher.stop)
        process.available.__globals__["_command_available"].cache_clear()
        self.addCleanup(process.available.__globals__["_command_available"].cache_clear)
        self.write_config(argv={role: [sys.executable, str(FIXTURES / "fake_role.py"), role]
                                for role in ROLES if role != "executor"},
                          extra=HANDOFF_CONFIG)  # the executor starts from the launch catalog
        path = self.project.parent / "codex-executor.json"
        path.write_text(json.dumps({"stages": [{"role": "executor", "provider": "codex", "model": "gpt-6.1-sol",
                                                "effort": "high"}]}), encoding="utf-8")
        self.options = ("--options", path)

    def argv(self, number: int) -> list:
        return json.loads((self.fake / f"executor-{number}.argv").read_text(encoding="utf-8"))

    def test_the_correction_round_resumes_the_thread_with_the_sandbox_as_a_config_override(self):
        self.script({"executor": [self.RED, dict(executor_ok("W1"), codex=True)], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=self.options)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        isolated = ["--ignore-user-config", "-c", "project_doc_max_bytes=0"]  # the codex isolation profile (P6.1)
        self.assertEqual(self.argv(1), ["-a", "never", "exec", "--json", "--sandbox", "danger-full-access",
                                        "--model", "gpt-6.1-sol", "-c", 'model_reasoning_effort="high"', "-", *isolated])
        self.assertEqual(self.argv(2), ["-a", "never", "exec", "resume", "executor-session-1", "--json",
                                        "-c", 'sandbox_mode="danger-full-access"', "--model", "gpt-6.1-sol",
                                        "-c", 'model_reasoning_effort="high"', "-", *isolated])
        self.assertNotIn("--sandbox", self.argv(2))
        second = self.prompt("executor", 2)
        self.assertIn("You continue piece W1 in the same session", second)  # the delta prompt on the thread
        self.assertNotIn("Create the output of W1.", second)
        self.assertEqual(self.state(err)["executor_sessions"]["W1"]["session"], "executor-session-2")

    def test_a_per_item_session_starts_a_new_thread_each_round(self):
        self.script({"executor": [self.RED, dict(executor_ok("W1"), codex=True)], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--no-batch", *self.options))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("resume", self.argv(2))
        self.assertIn("--sandbox", self.argv(2))
        self.assertIn("Create the output of W1.", self.prompt("executor", 2))


class GrokResumeTests(unittest.TestCase):
    """A Grok executor continues its conversation in a correction round (``grok --resume <id>``): the same command line
    as a fresh one plus the session, conversation only (never ``--restore-code``, which would roll the tree back)."""

    def test_the_grok_executor_resumes_the_conversation_and_keeps_its_command_line(self):
        from orch import launch
        catalog = launch.load_catalog()
        fresh = launch.build_argv(catalog, "executor", "grok", model="grok-4.7", cwd="/w")
        resumed = launch.build_resume_argv(catalog, "executor", "grok", model="grok-4.7", cwd="/w")
        self.assertEqual(resumed[resumed.index("--resume") + 1], "{session}")
        self.assertEqual([arg for arg in resumed if arg not in ("--resume", "{session}")], fresh)
        for flag in ("--restore-code", "--fork-session", "--continue"):
            self.assertNotIn(flag, resumed)


class OptionsCopyTests(ConductorCase):
    def test_the_options_file_is_kept_with_the_run(self):
        options_file = self.project.parent / "opts.json"
        options_file.write_text(json.dumps({"rules": ["keep it short"]}), encoding="utf-8")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--options", options_file))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        kept = self.run_dir(err) / "options.json"
        self.assertEqual(json.loads(kept.read_text(encoding="utf-8")), {"rules": ["keep it short"]})


class ReviewFixesTests(unittest.TestCase):
    def test_every_role_that_reads_the_repository_is_isolated_by_default(self):
        for role in ("researcher", "advisor", "executor", "reviewer"):
            self.assertIn(role, options.DEFAULTS["instructions"]["isolate_roles"])

    def test_the_catalog_lets_the_researcher_and_the_advisor_query_with_an_invocation_config(self):
        from orch import launch
        catalog = launch.load_catalog()["launch"]  # resolved: the file states the command once, as a shared part
        found = [role for role, providers in catalog.items() for entry in providers.values()
                 if "Bash(python3 *orch.py --config * research query *)" in entry["argv"]]
        self.assertEqual(sorted(found), ["advisor", "researcher"])

    def test_a_skills_choice_is_dropped_with_the_retry(self):
        import inspect
        self.assertIn('"skills_checked"', inspect.getsource(engine.Conductor._retry))


class SessionConfigTests(unittest.TestCase):
    def test_the_machine_config_layer_sets_the_default_and_a_run_option_overrides_it(self):
        layer = options.config_layer({"session_executor": "per-item"})
        self.assertEqual(layer["session"], {"executor": "per-item"})
        self.assertNotIn("session", options.config_layer({}))
        merged, sources = options.effective({"session_executor": "per-item"}, {}, [])
        self.assertEqual(merged["session"]["executor"], "per-item")
        merged, _ = options.effective({"session_executor": "per-item"}, {},
                                      [{"source": "plan", "options": {"session": {"executor": "shared"}}}])
        self.assertEqual(merged["session"]["executor"], "shared")




class ClaimAllTests(ConductorCase):
    def statuses_at_the_first_piece(self, *extra) -> dict:
        self.set_items({"W1": {}, "W2": {}, "W3": {}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2"), executor_ok("W3")], "reviewer": [GREEN] * 3})
        seen, original = {}, engine.Conductor._piece

        def spy(conductor, answer):
            if not seen:
                seen.update({ref: doc["status"] for ref, doc in self.source()["items"].items()})
            return original(conductor, answer)

        with mock.patch.object(engine.Conductor, "_piece", spy):
            code, _, err = self.run_items("W1", "W2", "W3", extra=extra)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return seen

    def test_all_pieces_of_a_batch_are_in_progress_before_the_first_one_starts(self):
        self.assertEqual(self.statuses_at_the_first_piece(), {"W1": "in_progress", "W2": "in_progress", "W3": "in_progress"})

    def test_no_batch_takes_them_one_at_a_time(self):
        self.assertEqual(self.statuses_at_the_first_piece("--no-batch"),
                         {"W1": "in_progress", "W2": "todo", "W3": "todo"})

    def test_a_piece_that_depends_on_an_earlier_one_of_the_batch_is_in_progress_with_it(self):
        self.set_items({"W1": {}, "W2": {"depends_on": ["W1"]}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN] * 2})
        seen, original = {}, engine.Conductor._piece

        def spy(conductor, answer):
            if not seen:
                seen.update({ref: doc["status"] for ref, doc in self.source()["items"].items()})
            return original(conductor, answer)

        with mock.patch.object(engine.Conductor, "_piece", spy):
            code, _, err = self.run_items("W1", "W2")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual(seen, {"W1": "in_progress", "W2": "in_progress"})

    def test_a_dependency_outside_the_batch_waits_for_its_turn_without_stopping_the_run(self):
        self.set_items({"W1": {}, "W2": {"depends_on": ["W9"]}, "W9": {"status": "done"}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN] * 2})
        code, _, err = self.run_items("W1", "W2")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)

    def test_the_prompt_lists_every_piece_with_its_title_and_state(self):
        self.statuses_at_the_first_piece()
        first, second = self.prompt("executor", 1), self.prompt("executor", 2)
        self.assertIn("- `W1` — Work W1 (this piece)", first)
        self.assertIn("- `W2` — Work W2 (next)", first)
        self.assertIn("- `W1` — Work W1 (done and committed)", second)
        self.assertIn("- `W3` — Work W3 (next)", second)


class ClaimActorTests(ConductorCase):
    def test_the_claim_names_the_executor_class_the_run_was_started_with(self):
        options_file = self.project.parent / "o.json"
        options_file.write_text(json.dumps({"stages": [{"role": "executor", "model_class": "frontier"}]}), encoding="utf-8")
        eng = engine.Conductor.__new__(engine.Conductor)
        eng.run_doc, eng.directory = {"options_file": str(options_file)}, self.project
        self.assertEqual(eng._invocation_executor_class(), "frontier")
        eng.run_doc = {"options_file": str(self.project.parent / "gone.json")}
        self.assertIsNone(eng._invocation_executor_class())

    def claimer(self, stage):
        options_file = self.project.parent / "o.json"
        options_file.write_text(json.dumps({"stages": [dict(role="executor", **stage)]}), encoding="utf-8")
        eng = engine.Conductor.__new__(engine.Conductor)
        eng.run_doc, eng.directory, eng.conductor = {"options_file": str(options_file)}, self.project, {}
        eng._catalog_get = mock.Mock()
        return eng

    def test_the_claim_carries_the_provider_model_and_effort_of_the_options_executor(self):
        eng = self.claimer({"provider": "codex", "model": "gpt-6.1-sol", "model_class": "implementation",
                            "effort": "xhigh"})
        self.assertEqual(eng._claim_actor(), "codex/gpt-6.1-sol/xhigh")
        eng._catalog_get.assert_not_called()  # an explicit model is not resolved from its class

    def test_the_claim_resolves_the_model_of_the_class_and_names_no_effort_the_options_do_not_set(self):
        eng = self.claimer({"provider": "codex", "model_class": "economy"})
        eng._catalog_get.return_value.resolve_model.return_value = "gpt-6.1-sol"
        self.assertEqual(eng._claim_actor(), "codex/gpt-6.1-sol")
        eng._catalog_get.return_value.resolve_model.assert_called_once_with("codex", "economy")

    def test_without_options_the_claim_is_the_default_executor_without_effort(self):
        eng = self.claimer({})
        eng.run_doc = {"options_file": None}
        eng._catalog_get.return_value.resolve_model.return_value = "m"
        actor = eng._claim_actor()
        self.assertEqual(actor.count("/"), 1, actor)


    def test_the_claim_says_which_fields_of_the_actor_the_run_named(self):
        for stage, expected in (({"provider": "codex", "model": "gpt-6.1-sol", "effort": "xhigh"},
                                 ("options", ["provider", "model", "effort"], None)),
                                ({"effort": "low"}, ("options", ["effort"], None)),
                                ({"provider": "codex"}, ("options", ["provider"], None)),  # the merge keeps the plan's model
                                ({"model_class": "frontier"}, ("options", None, "frontier")),
                                ({"model": "opus", "model_class": "frontier"}, ("options", ["model"], None))):
            with self.subTest(stage):
                self.assertEqual(self.claimer(stage)._claim_actor_source(), expected)
        eng = self.claimer({})
        eng.run_doc = {"options_file": None}
        self.assertEqual(eng._claim_actor_source(), ("default", None, None))

    def test_a_run_executor_that_replaces_the_plan_one_is_said_and_kept(self):
        self.set_items({"W1": {"plan_executor": {"provider": "codex", "model": "gpt-6.1-sol"}}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        path = self.project.parent / "exec-options.json"
        path.write_text(json.dumps({"stages": [{"role": "executor", "provider": "claude-code", "model": "opus"}]}))
        code, _, err = self.run_items("W1", extra=("--options", path))
        self.assertEqual(code, 0, err)
        said = [line for line in self.lines(err) if line.get("reason_code") == "ACTOR_OVERRIDE"]
        self.assertEqual(len(said), 1, err)
        claims = self.state(err)["claims"]
        self.assertEqual([claim["actor_override"]["plan"]["provider"] for claim in claims.values()], ["codex"])
        request = self.source()["claim_requests"][0]
        self.assertEqual((request["actor_source"], request["actor_fields"]), ("options", ["provider", "model"]))

    def test_a_run_without_an_executor_of_its_own_claims_as_default(self):
        self.set_items({"W1": {"plan_executor": {"provider": "codex", "model": "gpt-6.1-sol"}}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.source()["claim_requests"][0]["actor_source"], "default")
        self.assertFalse([line for line in self.lines(err) if line.get("reason_code") == "ACTOR_OVERRIDE"])


class TranscriptGuardTests(ConductorCase):
    def test_a_shared_claude_executor_may_write_the_transcripts_of_the_project_and_nothing_else_of_claude(self):
        eng = engine.Conductor.__new__(engine.Conductor)
        eng.project = Path("/tmp/my.proj-x")
        item = type("I", (), {"options": {"session": {"executor": "shared"}, "scope": {}}})()
        argv = ["python3", "/x/ro-run.py", "--rw", "/p", "--", "claude", "-p"]
        with mock.patch.object(Path, "mkdir"), mock.patch.object(Path, "home", return_value=Path("/home/u")):
            out = eng._extra_write_dirs(item, "executor", argv)
            self.assertIn("/home/u/.claude/projects/-tmp-my-proj-x", out)
            self.assertNotIn("/home/u/.claude", out)
            item.options["session"]["executor"] = "per-item"
            self.assertEqual(eng._extra_write_dirs(item, "executor", argv), argv)


class ReadyBatchTests(ConductorCase):
    """`--ready`: the lane the source names is a batch like `--items` (all pieces in progress, one session)."""

    def at_the_first_piece(self, *extra) -> dict:
        self.set_items({"W1": {}, "W2": {}, "W3": {}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2"), executor_ok("W3")], "reviewer": [GREEN] * 3})
        seen, original = {}, engine.Conductor._piece

        def spy(conductor, answer):
            if not seen:
                seen.update({ref: doc["status"] for ref, doc in self.source()["items"].items()})
            return original(conductor, answer)

        with mock.patch.object(engine.Conductor, "_piece", spy):
            code, _, err = self.conduct("run", "--plan", "T", "--ready", "--json-lines", *extra)
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        return seen

    def test_the_lane_of_the_source_is_in_progress_at_once(self):
        self.assertEqual(self.at_the_first_piece(), {"W1": "in_progress", "W2": "in_progress", "W3": "in_progress"})
        self.assertEqual(self.calls("executor"), 3)
        self.assertIn("`W3`", self.prompt("executor", 1))

    def test_no_batch_takes_one_piece_at_a_time(self):
        self.assertEqual(self.at_the_first_piece("--no-batch"), {"W1": "in_progress", "W2": "todo", "W3": "todo"})

    def test_max_items_cuts_the_lane(self):
        seen = self.at_the_first_piece("--max-items", "2")
        self.assertEqual(seen, {"W1": "in_progress", "W2": "in_progress", "W3": "todo"})


class StopKeepsTheBatchTests(ConductorCase):
    """A stop is resumable: the pieces of a batch stay in progress together (none is given back on its own), and a piece
    whose executor round began counts as worked on, however the round ended."""

    def stopped_first_piece(self, *extra) -> dict:
        self.set_items({"W1": {}, "W2": {}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN] * 2})
        original = engine.Conductor._conduct

        def stop_first(conductor, item):
            if item.ref == "W1":
                raise engine.Stop("PREPARE_REFUSED", "refused for the test")
            return original(conductor, item)

        with mock.patch.object(engine.Conductor, "_conduct", stop_first):
            self.run_items("W1", "W2", extra=extra)
        return {ref: doc["status"] for ref, doc in self.source()["items"].items()}

    def test_a_batch_keeps_every_piece_in_progress_when_one_stops_before_work(self):
        self.assertEqual(self.stopped_first_piece(), {"W1": "in_progress", "W2": "in_progress"})

    def test_without_a_batch_the_stopped_piece_is_given_back_as_before(self):
        self.assertEqual(self.stopped_first_piece("--no-batch"), {"W1": "todo", "W2": "todo"})

    def test_a_started_executor_round_counts_as_work(self):
        self.assertTrue(engine.Conductor._work_began({"executor_started": True, "steps": {}}))
        self.assertFalse(engine.Conductor._work_began({"steps": {"scout": {}}}))


class FenceTests(ConductorCase):
    def test_the_project_fence_is_the_default_and_the_executor_is_told_it_may_report_instead_of_block(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        prompt = self.prompt("executor", 1)
        self.assertIn("## Write fence of this run", prompt)
        self.assertIn("it is not a fence", prompt)

    def test_the_plan_fence_leaves_the_prompt_as_it_was(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--fence", "plan"))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertNotIn("Write fence of this run", self.prompt("executor", 1))

    def test_an_extra_path_is_named_in_the_prompt_and_given_to_the_filesystem_guard(self):
        extra = self.project.parent / "shared-docs"
        extra.mkdir()
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--fence", "plan", "--allow-path", str(extra)))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertIn(f"`{extra}`", self.prompt("executor", 1))

    def test_ro_run_gets_one_rw_per_extra_path_before_the_separator(self):
        eng = engine.Conductor.__new__(engine.Conductor)
        item = type("I", (), {"options": {"scope": {"extra_paths": ["/data/a", "~/b"]}, "session": {"executor": "per-item"}}})()
        argv = ["python3", "/x/ro-run.py", "--rw", "/p", "--", "claude", "-p"]
        out = eng._extra_write_dirs(item, "executor", argv)
        self.assertEqual(out[:5], ["python3", "/x/ro-run.py", "--rw", "/p", "--rw"])
        self.assertEqual(out[out.index("--"):], ["--", "claude", "-p"])
        self.assertEqual(out.count("--rw"), 3)
        self.assertEqual(eng._extra_write_dirs(item, "reviewer", argv), argv)
        self.assertEqual(eng._extra_write_dirs(item, "executor", ["claude", "-p"]), ["claude", "-p"])
        self.assertEqual(eng._extra_write_dirs(item, "executor", ["claude", "-p"]), ["claude", "-p"])
        self.assertEqual(eng._extra_write_dirs(item, "bounded-implementer", argv).count("--rw"), 3)  # a writer too


class ExtraPathGrantTests(unittest.TestCase):
    """``scope.extra_paths`` reaches every route that writes (K5-N2): the Landlock guard (``--rw``) while it stays,
    ``--add-dir`` and a sandbox write grant for Claude Code under the provider sandbox, ``--add-dir`` for Codex."""
    UP = {"available": True, "reason": None, "checked": []}
    DOWN = {"available": False, "reason": "no bwrap", "checked": []}
    PATH = "/data/shared"
    ROUTES = {
        "claude-code": {"provider": "claude-code", "argv": [
            "python3", "/x/ro-run.py", "--rw", "/p", "--", "claude", "-p", "--tools", "Bash,Read,Edit,Write",
            "--permission-mode", "acceptEdits"]},
        "codex": {"provider": "codex", "argv": ["codex", "-a", "never", "exec", "--json", "--sandbox", "workspace-write", "-"]},
        "grok": {"provider": "grok", "argv": ["python3", "/x/ro-run.py", "--rw", "/p", "--", "grok", "--cwd", "/p"]},
    }

    def argv(self, role: str, provider: str, paths: list, probe: dict) -> list:
        eng = engine.Conductor.__new__(engine.Conductor)
        eng.progress = None
        item = type("I", (), {"ref": "W1", "options": {
            "instructions": {"isolate_roles": [], "sandbox": "prefer", "sandbox_domains": []},
            "session": {"executor": "per-item"}, "scope": {"extra_paths": paths}}})()
        with mock.patch("orch.sandbox.probe", return_value=probe), mock.patch.object(engine.Conductor, "_knows", return_value=True):
            return eng._role_argv(item, role, self.ROUTES[provider])

    @staticmethod
    def grant(argv: list) -> dict:
        """The ways ``PATH`` is granted in ``argv``."""
        found = {"rw": [argv[i + 1] for i, arg in enumerate(argv) if arg == "--rw"],
                 "add_dir": [argv[i + 1] for i, arg in enumerate(argv) if arg == "--add-dir"], "allow_write": []}
        if "--settings" in argv:
            found["allow_write"] = json.loads(argv[argv.index("--settings") + 1])["sandbox"].get("filesystem", {}).get("allowWrite", [])
        return found

    def test_every_writing_route_gets_the_grant_with_the_sandbox_up_or_down(self):
        for role in ("executor", "bounded-implementer"):
            for provider in ("claude-code", "codex", "grok"):
                for probe in (self.UP, self.DOWN):
                    with self.subTest(role=role, provider=provider, sandbox=probe["available"]):
                        found = self.grant(self.argv(role, provider, [self.PATH], probe))
                        if provider == "claude-code":
                            self.assertEqual(found["add_dir"], [self.PATH])
                            if probe["available"]:  # the Landlock guard is gone: the sandbox block and --add-dir carry it
                                self.assertEqual((found["rw"], found["allow_write"]), ([], [self.PATH]))
                            else:
                                self.assertEqual((found["rw"], found["allow_write"]), (["/p", self.PATH], []))
                        elif provider == "codex":
                            self.assertEqual(found["add_dir"], [self.PATH])
                        else:
                            self.assertEqual((found["rw"], found["add_dir"]), (["/p", self.PATH], []))

    def test_a_sandboxed_claude_writer_keeps_the_rest_of_the_sandbox_block(self):
        argv = self.argv("executor", "claude-code", [self.PATH], self.UP)
        block = json.loads(argv[argv.index("--settings") + 1])["sandbox"]
        self.assertEqual({key: block[key] for key in ("enabled", "allowUnsandboxedCommands", "failIfUnavailable")},
                         {"enabled": True, "allowUnsandboxedCommands": False, "failIfUnavailable": True})
        self.assertEqual(block["network"], {"strictAllowlist": True, "allowedDomains": []})
        self.assertEqual(block["filesystem"], {"allowWrite": [self.PATH]})
        self.assertNotIn("ro-run.py", " ".join(argv))
        self.assertLess(argv.index("--add-dir"), argv.index("--settings"))  # --add-dir takes several values: a flag ends them

    def test_codex_gets_add_dir_right_after_exec(self):
        argv = self.argv("executor", "codex", ["/data/a", "/data/b"], self.UP)
        at = argv.index("exec")
        self.assertEqual(argv[at + 1:at + 5], ["--add-dir", "/data/a", "--add-dir", "/data/b"])
        self.assertEqual(argv[-1], "-")

    def test_without_extra_paths_the_argv_does_not_change(self):
        for provider in ("claude-code", "codex", "grok"):
            for probe in (self.UP, self.DOWN):
                with self.subTest(provider=provider, sandbox=probe["available"]):
                    argv = self.argv("executor", provider, [], probe)
                    self.assertNotIn("--add-dir", argv)
                    self.assertEqual(self.grant(argv)["allow_write"], [])
                    guarded = provider == "grok" or (provider == "claude-code" and not probe["available"])
                    self.assertEqual(argv.count("--rw"), 1 if guarded else 0)  # only the project of the guard
        self.assertEqual(self.argv("executor", "codex", [], self.UP), self.ROUTES["codex"]["argv"])

    def test_a_role_that_does_not_write_gets_no_grant(self):
        for provider in ("claude-code", "codex", "grok"):
            with self.subTest(provider=provider):
                found = self.grant(self.argv("reviewer", provider, [self.PATH], self.UP))
                self.assertEqual((found["add_dir"], found["allow_write"]), ([], []))
                self.assertNotIn(self.PATH, found["rw"])

    def test_a_home_path_is_expanded(self):
        found = self.grant(self.argv("executor", "claude-code", ["~/shared"], self.UP))
        self.assertEqual(found["add_dir"], [str(Path("~/shared").expanduser())])
        self.assertEqual(found["allow_write"], found["add_dir"])


if __name__ == "__main__":
    unittest.main()


class ScenarioFlagTests(ConductorCase):
    """``run --scenario S`` for a plan run reaches every claim (the work source resolves it for the piece)."""

    def claims(self) -> list:
        return [call for call in self.source()["calls"] if call.get("op") == "claim"]

    def test_the_flag_is_passed_to_the_claim_of_a_plan_run(self):
        self.set_items({"W1": {}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--scenario", self.scenario))
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual({call.get("scenario") for call in self.claims()}, {self.scenario})

    def test_without_the_flag_the_claim_names_no_scenario(self):
        self.set_items({"W1": {}})
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual({call.get("scenario") for call in self.claims()}, {None})


class DependencyHoldTests(ConductorCase):
    """``on_blocked: report`` goes on after a blocked piece, but not into a piece that depends on it."""

    def test_a_piece_that_depends_on_a_blocked_one_is_held_not_run(self):
        blocked = {"result": __import__("tests.test_conductor", fromlist=["report"]).report(
            "W1", "blocked", open_issues=[{"text": "needs a decision", "kind": "escalation"}])}
        self.set_items({"W1": {}, "W2": {"depends_on": ["W1"]}, "W3": {}})
        self.script({"executor": [blocked, executor_ok("W3")], "reviewer": [GREEN] * 2})
        options_file = self.project.parent / "report.json"
        options_file.write_text(json.dumps({"on_blocked": "report"}), encoding="utf-8")
        code, _, err = self.run_items("W1", "W2", "W3", extra=("--options", options_file))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "DEPENDENCY_BLOCKED")), err)
        self.assertEqual(self.calls("executor"), 2)  # W1 (blocked) and W3; never W2
        self.assertIn("DEPENDENCY_BLOCKED", err)
        status = {ref: doc["status"] for ref, doc in self.source()["items"].items()}
        self.assertEqual(status["W2"], "in_progress")  # held, not given back, not closed
        self.assertEqual(self.state(err)["items"]["W3"]["outcome"], "done")
