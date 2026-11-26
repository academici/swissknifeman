"""records/v1 (P4.3): runs written before the records have no tag (v0). They are read through ``migrate_v0`` in memory,
their files are not rewritten by a read, and they resume; records that do not match stop with the code of their kind."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

from orch.conductor import engine, questions, records
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import RunStore
from tests.test_conductor import GREEN, ConductorCase, executor_ok
from tests.test_conductor_questions import ASK, asking

V0 = Path(__file__).resolve().parent / "fixtures" / "records-v0"
QUESTION_RUN = "cnd-20261020T080000Z-0a0b0c"
STOPPED_RUN = "cnd-20261020T090000Z-0d0e0f"
NEWER_STATE = ("executor_session_task_digest", "executor_session_answers", "policy_stage_skipped")
NEWER_PIECE = ("review_marks", "stage_usage", "usage_by_agent")


def bytes_of(directory: Path) -> dict:
    return {path.relative_to(directory).as_posix(): path.read_bytes() for path in sorted(directory.rglob("*.json"))}


class V0FixtureTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name)

    def store(self, run_id: str) -> RunStore:
        store = RunStore(self.project, run_id)
        shutil.copytree(V0 / run_id, store.directory)
        return store

    def test_the_fixtures_are_v0(self):
        for path in sorted(V0.rglob("*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            self.assertFalse({"$schema", "schema"} & set(doc), path)

    def test_load_reads_v0_with_the_tag_and_leaves_the_files_as_they_were(self):
        for run_id in (QUESTION_RUN, STOPPED_RUN):
            with self.subTest(run=run_id):
                store = self.store(run_id)
                before = bytes_of(store.directory)
                run_doc, state = store.load()
                self.assertEqual((run_doc["$schema"], state["$schema"]), (records.TAGS["run"][1], records.TAGS["state"][1]))
                self.assertEqual(run_doc["run_id"], run_id)
                self.assertEqual(bytes_of(store.directory), before)
        found = questions.read(self.store_dir(QUESTION_RUN) / "W1")
        self.assertEqual((found["$schema"], found["questions"][0]["status"]), (records.TAGS["questions"][1], "applied"))

    def store_dir(self, run_id: str) -> Path:
        return RunStore(self.project, run_id).directory

    def test_a_save_after_a_v0_load_writes_v1(self):
        store = self.store(STOPPED_RUN)
        _, state = store.load()
        store.save(state)
        saved = json.loads((store.directory / engine.STATE_FILE).read_text(encoding="utf-8"))
        self.assertEqual(records.tag_state("state", saved), "v1")
        self.assertEqual({key: value for key, value in saved.items() if key != "$schema"},
                         json.loads((V0 / STOPPED_RUN / engine.STATE_FILE).read_text(encoding="utf-8")))

    def test_an_unknown_state_key_is_state_invalid_with_its_pointer(self):
        store = self.store(STOPPED_RUN)
        path = store.directory / engine.STATE_FILE
        state = json.loads(path.read_text(encoding="utf-8"))
        state["items"]["W1"]["steps"]["brief"]["surprise"] = 1
        path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(Stop) as caught:
            store.load()
        self.assertEqual(caught.exception.code, "STATE_INVALID")
        self.assertIn(f"{path}: /items/W1/steps/brief/surprise: unexpected property 'surprise'", caught.exception.message)
        self.assertTrue(caught.exception.message.endswith("; settle or release the items of this run, or start a new run"))

    def test_a_v0_state_with_a_done_step_its_reader_cannot_replay_is_state_invalid_before_resume(self):
        store = self.store(STOPPED_RUN)
        path = store.directory / engine.STATE_FILE
        original = json.loads(path.read_text(encoding="utf-8"))
        for key, step, pointer in (("checks.1", {"status": "done", "result": {}}, "/items/W1/steps/checks.1/result"),
                                   ("commit", {"status": "done"}, "/items/W1/steps/commit")):
            with self.subTest(step=key):
                state = json.loads(json.dumps(original))
                state["items"]["W1"]["steps"][key] = step
                path.write_text(json.dumps(state), encoding="utf-8")
                with self.assertRaises(Stop) as caught:
                    store.load()
                self.assertEqual(caught.exception.code, "STATE_INVALID")
                self.assertIn(pointer, caught.exception.message)

    def test_a_v0_state_with_the_auto_skills_choice_loads(self):
        store = self.store(STOPPED_RUN)
        path = store.directory / engine.STATE_FILE
        state = json.loads(path.read_text(encoding="utf-8"))
        choice = {"skills": [{"name": "python", "id": "lib:python"}], "excluded": [], "discoverable": [], "tokens": 40}
        state["items"]["W1"].update(skills_auto={"executor": choice},
                                    skills_checked={"executor": {"names": ["python"], "excluded": []}})
        path.write_text(json.dumps(state), encoding="utf-8")
        _, loaded = store.load()
        self.assertEqual(loaded["items"]["W1"]["skills_auto"]["executor"], choice)

    def test_a_run_record_that_is_not_an_object_is_run_invalid(self):
        store = self.store(STOPPED_RUN)
        (store.directory / engine.RUN_FILE).write_text("[1, 2]", encoding="utf-8")
        with self.assertRaises(Stop) as caught:
            store.load()
        self.assertEqual(caught.exception.code, "RUN_INVALID")
        self.assertIn("/: expected object, got array", caught.exception.message)

    def test_bytes_that_are_not_json_stay_state_corrupt(self):
        store = self.store(STOPPED_RUN)
        (store.directory / engine.STATE_FILE).write_text("{\"items\": ", encoding="utf-8")
        with self.assertRaises(Stop) as caught:
            store.load()
        self.assertEqual(caught.exception.code, "STATE_CORRUPT")

    def test_a_state_tagged_as_another_kind_is_state_invalid(self):
        store = self.store(STOPPED_RUN)
        path = store.directory / engine.STATE_FILE
        state = json.loads(path.read_text(encoding="utf-8"))
        path.write_text(json.dumps({"$schema": records.TAGS["run"][1], **state}), encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaises(Stop) as caught:
            store.load()
        self.assertEqual(caught.exception.code, "STATE_INVALID")
        self.assertIn("/$schema: unknown or conflicting record tag", caught.exception.message)
        self.assertEqual(path.read_bytes(), before)


class V0ResumeTests(ConductorCase):
    """A run left by the code before records/v1: the same files without tags and without the fields added since."""

    def test_a_v0_run_with_an_answer_resumes_to_the_end_and_writes_v1(self):
        self.script({"executor": [asking(dict(ASK)), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (4, ("waiting", "WAITING_DECISION")), err)
        directory = self.run_dir(err)
        self.downgrade(directory)
        questions.answer_file(directory / "W1", "Q1", option="rename", by="owner", now="2026-10-22T00:00:00Z")
        self.assertEqual(records.tag_state("questions", json.loads((directory / "W1" / questions.FILE).read_text())), "v1")
        doc = self.source()
        doc["items"]["W1"]["status"] = "todo"
        self.state_file.write_text(json.dumps(doc), encoding="utf-8")
        code, _, resumed = self.conduct("resume", "--run", directory.name, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(resumed)), (0, ("finished", None)), resumed)
        self.assertIn("Answer: rename (by owner)", self.prompt("executor", 2))
        for path, kind in ((directory / engine.STATE_FILE, "state"), (directory / "W1" / "routes.json", "item-routes"),
                           (directory / "W1" / "options.json", "item-options")):
            with self.subTest(kind=kind):
                self.assertEqual(records.tag_state(kind, json.loads(path.read_text(encoding="utf-8"))), "v1")
        self.assertEqual(records.tag_state("run", json.loads((directory / engine.RUN_FILE).read_text())), "v0")  # never rewritten
        self.assertEqual(self.state(resumed)["items"]["W1"]["outcome"], "done")

    def test_resume_of_a_v0_run_that_does_not_match_stops_with_run_invalid(self):
        self.script({"executor": [asking(dict(ASK))], "reviewer": [GREEN]})
        _, _, err = self.run_items("W1")
        directory = self.run_dir(err)
        (directory / engine.RUN_FILE).write_text(json.dumps({"run_id": directory.name, "items": "W1"}), encoding="utf-8")
        code, _, resumed = self.conduct("resume", "--run", directory.name)
        self.assertEqual(code, 1)
        self.assertTrue(resumed.startswith("RUN_INVALID: "), resumed)
        self.assertIn("/items: expected array, got string", resumed)

    @staticmethod
    def downgrade(directory: Path) -> None:
        """Strip the records/v1 tags and the state fields that P2.4/P3.10 added: what an older conductor left."""
        for path in [directory / engine.RUN_FILE, directory / engine.STATE_FILE, *directory.glob("*/questions.json"),
                     *directory.glob("*/options.json"), *directory.glob("*/routes.json")]:
            doc = json.loads(path.read_text(encoding="utf-8"))
            doc.pop("$schema", None)
            if path.name == engine.STATE_FILE:
                for key in NEWER_STATE:
                    doc.pop(key, None)
                for piece in doc.get("items", {}).values():
                    for key in NEWER_PIECE:
                        piece.pop(key, None)
            if path.name == "options.json":  # the merged skills map of the earlier writer
                doc["options"] = records.options_effective(doc["options"])
            path.write_text(json.dumps(doc), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
