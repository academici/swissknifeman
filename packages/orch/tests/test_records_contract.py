"""records/v1 (P4.3): the schemas of the run records, their examples, the tags, read/write through
``orch.conductor.records``, ``questions.json`` that is not valid (``QUESTIONS_INVALID``) and ``answer_schema``."""
from __future__ import annotations

from contextlib import nullcontext
import json
from pathlib import Path
import re
import statistics
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from aicore.util import schema

from orch.conductor import engine, questions, records
from orch.conductor.application import loop
from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import RunStore, write_json
from orch.conductor.stages import checks_stage, context
from tests.test_conductor import GREEN, ConductorCase, executor_ok
from tests.test_conductor_questions import ASK, asking

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "tests" / "golden" / "characterization"
EXAMPLES = records.CONTRACT_DIR / "examples"
TIME, DIGEST = "2026-01-01T00:00:00Z", "a" * 64


def concrete(value):
    """A golden snapshot with its placeholders (``<time>``, ``<digest>``, ``<run>``, the folders) made concrete, as the
    normalizer of test_characterization wrote them."""
    if isinstance(value, dict):
        return {key: concrete(item) for key, item in value.items()}
    if isinstance(value, list):
        return [concrete(item) for item in value]
    if isinstance(value, str):
        for mark, real in (("<time>", TIME), ("<digest>", DIGEST), ("<run>", "cnd-20260101T000000Z-abcdef"),
                           ("<project>", "/project"), ("<home>", "/home/owner"), ("<tmp>", "/tmp")):
            value = value.replace(mark, real)
    return value


def golden_state(path: Path) -> dict:
    found = json.loads(path.read_text(encoding="utf-8"))["state"]
    return concrete(json.loads(found) if isinstance(found, str) else found)


class SchemaTests(unittest.TestCase):
    def test_the_registry_holds_the_seventeen_kinds_each_with_its_one_carrier(self):
        self.assertEqual(records.registry().kinds, records.KINDS)
        self.assertEqual(set(records.KINDS) - set(records.SHORT_TAGS),
                         {"agent-request", "agent-result", "agent-usage", "item-options", "item-routes", "lease", "process",
                          "questions", "review-strategy", "risk", "run", "state"})
        self.assertEqual(set(records.SHORT_TAGS), {"conformance-report", "observer-report", "prompt-diff",
                                                   "provider-gates", "review-verdict"})
        for kind in records.KINDS:
            node, schema_id = records.registry().for_kind(kind)
            self.assertEqual(schema_id, f"urn:swissknifeman:orch:records:{kind}:v1")
            self.assertIs(node.get("additionalProperties"), False, kind)  # a closed root
            self.assertIn("$defs", node, kind)  # where later items add their fields
            carrier, value = records.TAGS[kind]
            other = "schema" if carrier == "$schema" else "$schema"
            self.assertEqual(node["properties"][carrier]["const"], value, kind)
            self.assertNotIn(other, node["properties"], kind)
            self.assertEqual(value, schema_id if carrier == "$schema" else records.SHORT_TAGS[kind])

    def test_item_options_refers_to_run_options_and_does_not_copy_it(self):
        node, _ = records.registry().for_kind("item-options")
        self.assertEqual(node["properties"]["options"], {"$ref": "urn:swissknifeman:orch:conductor:run-options:v1"})
        self.assertNotIn("stages", json.dumps(node))

    def test_every_valid_example_passes_and_every_invalid_one_fails_with_its_code(self):
        for kind in records.KINDS:
            valid = sorted((EXAMPLES / "valid" / kind).glob("*.json"))
            invalid = sorted((EXAMPLES / "invalid" / kind).glob("*.json"))
            self.assertTrue(valid and invalid, kind)
            for path in valid:
                with self.subTest(path=path.name):
                    self.assertEqual(records.problems(json.loads(path.read_text(encoding="utf-8")), kind), [])
            for path in invalid:
                with self.subTest(path=path.name):
                    doc = json.loads(path.read_text(encoding="utf-8"))
                    codes = {issue.code for issue in schema.validate(doc, kind, records.registry())}
                    self.assertIn(path.name.split("-", 1)[0], codes)
                    self.assertNotEqual(records.problems(doc, kind), [])

    def test_every_golden_state_matches_the_state_schema(self):
        paths = sorted(GOLDEN.glob("*.json"))
        self.assertEqual(len(paths), 17)
        for path in paths:
            with self.subTest(golden=path.stem):
                self.assertEqual(records.problems(golden_state(path), "state"), [])

    def test_a_state_of_p2_and_p3_fields_is_valid_and_a_wrong_value_is_not(self):
        state = golden_state(GOLDEN / "green.json")
        state.update(executor_session_task_digest=DIGEST, executor_session_answers=[DIGEST], policy_stage_skipped=True)
        piece = state["items"]["W1"]
        piece["usage_by_agent"] = {"agent-1": {"streams/executor.1.jsonl": {"input": 1, "cached": 0, "output": 2,
                                                                            "usage_complete": True, "step": "executor.1"}}}
        piece["steps"]["checks.1"]["result"][0].update(reused=True, original_seconds=1.5, skipped=False)
        self.assertEqual(records.problems(state, "state"), [])
        piece["stage_usage"]["executor.1"]["input"] = "100"
        piece["review_marks"]["1"]["out/W1.txt"] = 7
        found = records.problems(state, "state")
        self.assertTrue(any(line.startswith("/items/W1/stage_usage/executor.1/input:") for line in found), found)
        self.assertTrue(any(line.startswith("/items/W1/review_marks/1/out~1W1.txt:") for line in found), found)

    def test_state_validation_cost(self):
        state = golden_state(GOLDEN / "finding-triage-correction.json")
        registry = records.registry()
        took = []
        for _ in range(30):
            start = time.perf_counter()
            schema.validate(state, "state", registry)
            took.append(time.perf_counter() - start)
        print(f"\nvalidate(state) median {statistics.median(took) * 1000:.2f} ms on finding-triage-correction "
              f"({len(json.dumps(state))} bytes)")


class TagTests(unittest.TestCase):
    def test_tag_states_of_a_dollar_schema_kind(self):
        tag = "urn:swissknifeman:orch:records:state:v1"
        self.assertEqual(records.tag_state("state", {"$schema": tag}), "v1")
        self.assertEqual(records.tag_state("state", {"items": {}}), "v0")
        self.assertEqual(records.tag_state("state", ["not", "an", "object"]), "v0")
        for doc in ({"$schema": "urn:swissknifeman:orch:records:run:v1"}, {"$schema": tag, "schema": "x/v1"},
                    {"schema": "x/v1"}):
            self.assertEqual(records.tag_state("state", doc), "conflict", doc)

    def test_a_short_kind_keeps_its_published_carrier(self):
        self.assertEqual(records.TAGS["review-verdict"], ("schema", "orch-conductor-review-verdict/v1"))
        self.assertEqual(records.tag_state("provider-gates", {"schema": "provider-gates/v1", "gates": {}}), "v1")
        migrated = records.migrate_v0("provider-gates", {"gates": {}})
        self.assertEqual(migrated, {"schema": "provider-gates/v1", "gates": {}})
        self.assertNotIn("$schema", migrated)
        self.assertEqual(records.tag_state("provider-gates", {"$schema": "urn:swissknifeman:orch:records:provider-gates:v1"}),
                         "conflict")
        self.assertEqual(records.tag_state("prompt-diff", {"schema": "prompt-diff/v2"}), "conflict")

    def test_migrate_v0_copies_and_stamp_never_changes_the_callers_object(self):
        routes = {"executor": {"provider": "fake", "argv": ["x"]}}
        stamped = records.stamp("item-routes", routes)
        self.assertEqual(stamped["$schema"], "urn:swissknifeman:orch:records:item-routes:v1")
        self.assertNotIn("$schema", routes)
        self.assertIs(records.stamp("item-routes", stamped), stamped)

    def test_the_options_record_is_a_run_options_layer_that_gives_the_options_back(self):
        effective = {"skills": {"reviewer": ["a"], "executor": ["auto"]}, "on_blocked": "stop"}
        layer = records.options_layer(effective)
        self.assertEqual(layer["skills"], [{"role": "executor", "names": ["auto"]}, {"role": "reviewer", "names": ["a"]}])
        self.assertEqual(records.options_effective(layer), effective)
        v0 = {"scenario": "full", "options": effective, "sources": {}, "digest": DIGEST, "claim_route": None}
        self.assertEqual(records.migrate_v0("item-options", v0)["options"]["skills"], layer["skills"])
        self.assertEqual(records.problems(v0, "item-options"), [])


class ReadWriteTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_write_tags_checks_and_keeps_the_file_on_refusal(self):
        path = self.root / "routes.json"
        records.write(path, {"executor": {"provider": "fake", "argv": ["x"]}}, "item-routes")
        written = path.read_bytes()
        self.assertEqual(json.loads(written)["$schema"], "urn:swissknifeman:orch:records:item-routes:v1")
        with self.assertRaises(Stop) as caught:
            records.write(path, {"executor": {"argv": ["x"]}}, "item-routes")
        self.assertEqual(caught.exception.code, "RECORD_INVALID")
        self.assertRegex(caught.exception.message, r"routes\.json: /executor: missing required property 'provider'; "
                                                   r"settle or release the items of this run, or start a new run$")
        self.assertEqual(path.read_bytes(), written)
        self.assertEqual(oct(path.stat().st_mode & 0o777), "0o600")

    def test_read_names_the_pointer_and_at_most_three_problems(self):
        path = self.root / "lease.json"
        write_json(path, {"pid": "1", "host": 2, "started_at": 3, "command": 4, "extra": 5})
        with self.assertRaises(Stop) as caught:
            records.read(path, "lease")
        self.assertEqual(caught.exception.code, "RECORD_INVALID")
        self.assertEqual(caught.exception.message.count(": expected") + caught.exception.message.count("unexpected"), 3)
        self.assertTrue(caught.exception.message.startswith(f"{path}: /"))

    def test_a_conflicting_tag_is_refused_and_the_file_is_not_touched(self):
        path = self.root / "options.json"
        path.write_text(json.dumps({"schema": "item-options/v1", "options": {}}), encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaises(Stop) as caught:
            records.read(path, "item-options")
        self.assertEqual((caught.exception.code, path.read_bytes()), ("RECORD_INVALID", before))
        self.assertIn("/schema: unknown or conflicting record tag", caught.exception.message)

    def test_a_missing_file_is_none_and_bytes_that_are_not_json_are_state_corrupt(self):
        self.assertIsNone(records.read(self.root / "none.json", "run"))
        (self.root / "bad.json").write_text("{nope", encoding="utf-8")
        with self.assertRaises(Stop) as caught:
            records.read(self.root / "bad.json", "questions")
        self.assertEqual(caught.exception.code, "STATE_CORRUPT")

    def test_run_store_load_create_and_save_hold_the_store_lock(self):
        store = RunStore(self.root, "cnd-locks")
        held = []

        class Counting:
            def __init__(self, lock):
                self.lock = lock

            def __enter__(self):
                held.append(1)
                return self.lock.__enter__()

            def __exit__(self, *exc):
                return self.lock.__exit__(*exc)

        store.lock = Counting(store.lock)
        store.create({"run_id": "cnd-locks", "items": ["W1"]})
        store.save({"status": "running", "items": {}, "claims": {}})
        run_doc, state = store.load()
        self.assertEqual(len(held), 3)
        self.assertEqual((run_doc["$schema"], state["$schema"]), (records.TAGS["run"][1], records.TAGS["state"][1]))
        with self.assertRaises(Stop) as caught:
            store.save({"status": "running", "invented": True})
        self.assertEqual(caught.exception.code, "STATE_INVALID")
        self.assertIn("/invented: unexpected property 'invented'", caught.exception.message)


def replaying_engine():
    """The parts of a conductor that ``loop.step`` and ``checks_stage.run_checks`` touch when a step is closed: a step
    that is not closed would compute, and that fails the test."""
    found = SimpleNamespace(store=SimpleNamespace(mutating=nullcontext), progress=mock.Mock(),
                            _compute_checks=mock.Mock(side_effect=AssertionError("a closed step must not run again")))
    found._step = lambda *args, **kwargs: loop.step(found, *args, **kwargs)
    return found


class StepRecordTests(unittest.TestCase):
    """A done step is replayed by resume: it must carry the result its reader takes (F2), and the producer's own
    records must load (F1)."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def load(self, state: dict) -> dict:
        store = RunStore(self.root, "cnd-steps")
        store.directory.mkdir(parents=True, exist_ok=True)
        (store.directory / engine.RUN_FILE).write_text(json.dumps({"run_id": "cnd-steps"}), encoding="utf-8")
        (store.directory / engine.STATE_FILE).write_text(json.dumps(state), encoding="utf-8")
        return store.load()[1]

    def test_a_done_step_without_the_result_its_reader_takes_is_state_invalid(self):
        for key, step, pointer in (
                ("checks.1", {"status": "done", "result": {}}, "/items/W1/steps/checks.1/result: expected array"),
                ("checks.1", {"status": "done", "result": [{"id": "V1"}]},
                 "/items/W1/steps/checks.1/result/0: missing required property 'green'"),
                ("commit", {"status": "done"}, "/items/W1/steps/commit: missing required property 'result'"),
                ("executor.1", {"status": "done", "result": {"agent": "a1"}},
                 "/items/W1/steps/executor.1/result: missing required property 'report'"),
                ("brief", {"status": "done", "result": {}}, "/items/W1/steps/brief/result: missing required property 'input_path'"),
                ("review.1", {"status": "done", "result": {"findings": {}}},
                 "/items/W1/steps/review.1/result/findings: missing required property 'verdict'"),
                ("review.1", {"status": "done", "result": {"findings": {"verdict": "GREEN", "findings": {}}}},
                 "/items/W1/steps/review.1/result/findings/findings: expected array"),
                ("triage.1", {"status": "done", "result": {"triage": {}}},
                 "/items/W1/steps/triage.1/result/triage: missing required property"),
                ("mystery.1", {"status": "done"}, "/items/W1/steps/mystery.1: missing required property 'result'")):
            with self.subTest(step=key, shape=step):
                with self.assertRaises(Stop) as caught:
                    self.load({"items": {"W1": {"steps": {key: step}}}})
                self.assertEqual(caught.exception.code, "STATE_INVALID")
                self.assertIn(pointer, caught.exception.message)

    def test_a_malformed_completed_review_is_refused_on_write_and_a_valid_one_is_kept(self):
        store = RunStore(self.root, "cnd-review")
        store.directory.mkdir(parents=True)
        store.create({"run_id": "cnd-review"})
        green = {"status": "done", "result": {"findings": {"findings": [], "verdict": "GREEN"}}}
        unfinished = {"status": "started", "role": "reviewer"}
        store.save({"items": {"W1": {"steps": {"review.1": green, "review.2": unfinished}}}})
        before = (store.directory / engine.STATE_FILE).read_bytes()
        with self.assertRaises(Stop) as caught:
            store.save({"items": {"W1": {"steps": {"review.1": {"status": "done", "result": {"findings": {}}}}}}})
        self.assertEqual(caught.exception.code, "STATE_INVALID")
        self.assertIn("/items/W1/steps/review.1/result/findings: missing required property 'verdict'",
                      caught.exception.message)
        self.assertEqual((store.directory / engine.STATE_FILE).read_bytes(), before)
        self.assertEqual(store.load()[1]["items"]["W1"]["steps"], {"review.1": green, "review.2": unfinished})

    def test_started_and_stopped_steps_need_no_result(self):
        steps = {"checks.1": {"status": "started", "result": {"partial": True}}, "commit": {"status": "stopped", "code": "TIMEOUT"},
                 "mystery.1": {"status": "started"}}
        self.assertEqual(self.load({"items": {"W1": {"steps": steps}}})["items"]["W1"]["steps"], steps)

    def test_closed_steps_of_a_loaded_state_are_replayed_without_running(self):
        rows = [{"id": "V1", "cmd": "true", "exit": 0, "green": True}]
        commit = {"outcome": "committed", "sha": "0" * 40}
        state = self.load({"items": {"W1": {"steps": {"checks.1": {"status": "done", "result": rows},
                                                       "commit": {"status": "done", "result": commit}}}}})
        item = Item("W1", "run-test", state["items"]["W1"], self.root / "W1", {})
        found = replaying_engine()
        self.assertEqual(checks_stage.run_checks(found, item, 1, {"status": "done"}), rows)
        self.assertEqual(found._compute_checks.call_count, 0)
        self.assertEqual(loop.step(found, item, "commit", mock.Mock(side_effect=AssertionError("ran"))), commit)

    def test_the_auto_skills_choice_is_saved_loaded_and_reused(self):
        item = Item("W1", "run-test", {}, self.root / "W1", {}, options={"skills": {"executor": ["auto"]}})
        chosen = {"skills": [{"name": "python", "id": "lib:python", "path": "/s/python/SKILL.md", "tokens": 120}],
                  "excluded": [{"id": "lib:old", "reason": "budget"}], "discoverable": [], "tokens": 120}
        conductor = SimpleNamespace(conductor={"skills_bridge": ["fake-bridge"]}, project=self.root, env={},
                                    _work_paths=lambda _item: [], progress=mock.Mock())
        answer = SimpleNamespace(returncode=0, stdout=json.dumps(chosen), stderr="")
        with mock.patch.object(context.subprocess, "run", return_value=answer) as bridge:
            context.auto_skills(conductor, item, "executor")
        self.assertEqual(bridge.call_count, 1)
        self.assertEqual(item.state["skills_auto"]["executor"]["tokens"], 120)
        store = RunStore(self.root, "cnd-skills")
        store.directory.mkdir(parents=True)
        store.create({"run_id": "cnd-skills"})
        store.save({"items": {"W1": item.state}})
        loaded = store.load()[1]["items"]["W1"]
        again = Item("W1", "run-test", loaded, self.root / "W1", {}, options={"skills": {"executor": ["auto"]}})
        with mock.patch.object(context.subprocess, "run", side_effect=AssertionError("the bridge ran again")):
            self.assertEqual(context.auto_skills(conductor, again, "executor"), item.state["skills_auto"]["executor"])
        for wrong in ([chosen], {"executor": {"skills": "python"}}, {"executor": dict(chosen, unknown=1)}):
            with self.subTest(wrong=wrong), self.assertRaises(Stop) as caught:
                store.save({"items": {"W1": {"skills_auto": wrong}}})
            self.assertEqual(caught.exception.code, "STATE_INVALID")
            self.assertIn("/items/W1/skills_auto", caught.exception.message)


class AnswerSchemaTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.directory = Path(tmp.name)

    def asked(self, answer_schema: dict) -> None:
        store = {}
        question = {"id": "Q1", "revision": 1, "kind": "clarification", "text": "How many?", "blocking": True,
                    "answer_schema": answer_schema}
        questions.record(store, [question], {"run": "cnd-one", "item": "W1", "step": "executor.1"}, TIME)
        questions.save(self.directory, "cnd-one", "W1", store)

    def test_an_integer_answer_schema_takes_5_and_refuses_x(self):
        self.asked({"type": "integer", "minimum": 0})
        with self.assertRaises(questions.QuestionError) as caught:
            questions.answer_file(self.directory, "Q1", text="x", by="owner", now=TIME)
        self.assertEqual(caught.exception.code, "ANSWER_INVALID")
        with self.assertRaises(questions.QuestionError) as caught:
            questions.answer_file(self.directory, "Q1", text="-1", by="owner", now=TIME)
        self.assertIn("/: -1 is less than the minimum 0", caught.exception.message)
        self.assertNotIn("resolution", questions.read(self.directory)["questions"][0])  # nothing written
        entry = questions.answer_file(self.directory, "Q1", text="5", by="owner", now=TIME)
        self.assertEqual(entry["resolution"]["value"], 5)
        self.assertEqual(questions.read(self.directory)["questions"][0]["resolution"]["value"], 5)

    def test_a_string_answer_schema_keeps_the_text_as_it_is(self):
        self.asked({"type": "string", "pattern": "^[a-z]+$"})
        with self.assertRaises(questions.QuestionError):
            questions.answer_file(self.directory, "Q1", text="5abc", by="owner", now=TIME)
        entry = questions.answer_file(self.directory, "Q1", text="abc", by="owner", now=TIME)
        self.assertEqual(entry["resolution"]["value"], "abc")

    def test_an_answer_schema_outside_the_profile_is_ignored_and_says_why(self):
        self.asked({"type": "string", "format": "email"})
        entry = questions.answer_file(self.directory, "Q1", text="not an email", by="owner", now=TIME)
        self.assertEqual(entry["resolution"]["value"], "not an email")
        self.assertIn("unsupported keyword 'format'", entry["answer_schema_ignored"])
        saved = questions.read(self.directory)["questions"][0]
        self.assertEqual(saved["answer_schema_ignored"], entry["answer_schema_ignored"])

    def test_an_answer_schema_with_an_outside_ref_is_ignored(self):
        self.asked({"$ref": "urn:elsewhere:thing:v1"})
        entry = questions.answer_file(self.directory, "Q1", text="1", by="owner", now=TIME)
        self.assertIn("$ref outside the schema", entry["answer_schema_ignored"])

    def test_a_local_ref_the_validator_cannot_resolve_makes_the_schema_ignored(self):
        for answer_schema, reason in (
                ({"$ref": "#/properties/value", "properties": {"value": {"type": "integer"}}}, "unsupported $ref fragment"),
                ({"$ref": "#/$defs/absent", "$defs": {"n": {"type": "integer"}}}, "does not resolve"),
                ({"$ref": "#"}, "a $ref cycle"),
                ({"oneOf": [{"$ref": "#/$defs/a"}], "$defs": {"a": {"not": {"$ref": "#"}}}}, "a $ref cycle")):
            for text in ("5", "use the staging cluster"):  # numeric text and ordinary text: neither is converted
                with self.subTest(answer_schema=answer_schema, text=text):
                    for path in self.directory.iterdir():
                        path.unlink()
                    self.asked(answer_schema)
                    entry = questions.answer_file(self.directory, "Q1", text=text, by="owner", now=TIME)
                    self.assertEqual(entry["resolution"]["value"], text)  # taken as given, not checked
                    self.assertIn(reason, entry["answer_schema_ignored"])
                    saved = questions.read(self.directory)["questions"][0]
                    self.assertEqual((saved["resolution"]["value"], saved["answer_schema_ignored"]),
                                     (text, entry["answer_schema_ignored"]))

    def test_a_ref_cycle_through_a_property_is_applicable_and_checks_the_answer(self):
        self.asked({"$ref": "#/$defs/node", "$defs": {"node": {"type": "object", "additionalProperties": False,
                                                               "properties": {"next": {"$ref": "#/$defs/node"}}}}})
        entry = questions.answer_file(self.directory, "Q1", text='{"next": {"next": {}}}', by="owner", now=TIME)
        self.assertNotIn("answer_schema_ignored", entry)
        with self.assertRaises(questions.QuestionError) as caught:
            questions.answer_file(self.directory, "Q1", text='{"next": 1}', by="owner", now=TIME)
        self.assertEqual(caught.exception.code, "ANSWER_INVALID")

    def test_a_resolvable_defs_ref_still_checks_the_answer(self):
        self.asked({"$ref": "#/$defs/count", "$defs": {"count": {"type": "integer", "minimum": 0}}})
        for text in ("x", "-1"):
            with self.subTest(text=text), self.assertRaises(questions.QuestionError) as caught:
                questions.answer_file(self.directory, "Q1", text=text, by="owner", now=TIME)
            self.assertEqual(caught.exception.code, "ANSWER_INVALID")
        entry = questions.answer_file(self.directory, "Q1", text="3", by="owner", now=TIME)
        self.assertEqual(entry["resolution"]["value"], 3)
        self.assertNotIn("answer_schema_ignored", entry)


class InvalidQuestionsTests(ConductorCase):
    def blocked(self, **question) -> Path:
        self.script({"executor": [asking(dict(ASK, **question)), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ITEM_BLOCKED")), err)
        return self.run_dir(err)

    def test_a_broken_questions_file_is_questions_invalid_and_keeps_its_bytes(self):
        directory = self.blocked()
        path = directory / "W1" / questions.FILE
        for broken in ("{not json", json.dumps({"run": directory.name, "item": "W1", "questions": [{"id": "Q1"}]})):
            path.write_text(broken, encoding="utf-8")
            code, out, err = self.conduct("answer", "--run", directory.name, "--item", "W1", "--question", "Q1",
                                          "--option", "rename", "--by", "owner")
            self.assertEqual((code, out), (1, ""))
            self.assertTrue(err.startswith("QUESTIONS_INVALID: "), err)
            self.assertEqual(path.read_text(encoding="utf-8"), broken)  # the answer was not written over it
            code, out, err = self.conduct("questions", "--run", directory.name, "--json")
            self.assertEqual((code, json.loads(out)["questions"]), (1, []))
            self.assertIn("QUESTIONS_INVALID: ", err)
        with self.assertRaises(questions.QuestionsInvalid) as caught:
            questions.read(directory / "W1")
        self.assertEqual(caught.exception.code, "QUESTIONS_INVALID")

    def test_resume_stops_on_a_questions_file_that_does_not_match(self):
        directory = self.blocked()
        path = directory / "W1" / questions.FILE
        document = json.loads(path.read_text(encoding="utf-8"))
        document["questions"][0]["status"] = "maybe"
        path.write_text(json.dumps(document), encoding="utf-8")
        before = path.read_bytes()
        self.reopen_source()
        code, _, err = self.conduct("resume", "--run", directory.name, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "QUESTIONS_INVALID")), err)
        self.assertEqual(path.read_bytes(), before)
        self.assertIn("/questions/0/status: must be one of", self.state(err)["stop"]["message"])

    def test_an_ignored_answer_schema_is_said_when_resume_hands_the_answer_over(self):
        directory = self.blocked(options=[], kind="clarification", answer_schema={"type": "string", "format": "date"})
        code, out, err = self.conduct("answer", "--run", directory.name, "--item", "W1", "--question", "Q1",
                                      "--text", "tomorrow", "--by", "owner")
        self.assertEqual(code, 0, err)
        self.assertIn("unsupported keyword 'format'", json.loads(out)["answer_schema_ignored"])
        self.assertIn("ANSWER_SCHEMA_IGNORED: ", err)
        self.reopen_source()
        code, _, err = self.conduct("resume", "--run", directory.name, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        ignored = [line for line in self.lines(err) if line.get("reason_code") == "ANSWER_SCHEMA_IGNORED"]
        self.assertEqual(len(ignored), 1, err)
        self.assertIn("Q1", ignored[0]["message"])
        self.assertIn("Answer: tomorrow (by owner)", self.prompt("executor", 2))

    def test_a_routes_record_that_does_not_match_is_record_invalid_in_status(self):
        directory = self.blocked()
        routes = directory / "W1" / "routes.json"
        document = json.loads(routes.read_text(encoding="utf-8"))
        document["executor"]["argv"] = "claude -p"
        routes.write_text(json.dumps(document), encoding="utf-8")
        code, _, err = self.conduct("status", "--run", directory.name, "--json")
        self.assertEqual(code, 1)
        self.assertTrue(re.match(r"RECORD_INVALID: .*routes\.json: /executor/argv: expected array", err), err)
        self.assertEqual(json.loads(routes.read_text(encoding="utf-8"))["executor"]["argv"], "claude -p")

    def reopen_source(self) -> None:
        doc = self.source()
        doc["items"]["W1"]["status"] = "todo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")

    def test_the_records_of_a_finished_run_are_v1(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        directory = self.run_dir(err)
        for path, kind in ((directory / engine.RUN_FILE, "run"), (directory / engine.STATE_FILE, "state"),
                           (directory / "W1" / "options.json", "item-options"),
                           (directory / "W1" / "routes.json", "item-routes")):
            with self.subTest(kind=kind):
                doc = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(records.tag_state(kind, doc), "v1")
                self.assertEqual(records.problems(doc, kind), [])


if __name__ == "__main__":
    unittest.main()
