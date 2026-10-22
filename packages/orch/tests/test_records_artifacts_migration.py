"""records/v1, part 2 (P4.9): the published short tags survive write -> read -> write byte for byte, a short kind without
its tag (v0) gets ``schema`` and never ``$schema``, a conflicting tag is refused, and the agent and process records of a
run started before records/v1 still drive its resume."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from orch.conductor import agents, gates, process, records
from orch.conductor.application import recovery
from orch.conductor.domain.stop import Stop

EXAMPLES = records.CONTRACT_DIR / "examples" / "valid"
SHORT = {"review-verdict": "two-rounds.json", "provider-gates": "two-gates.json",
         "observer-report": "slow-run-with-agents.json", "prompt-diff": "correction-round.json",
         "conformance-report": "cao.json"}
V0 = {"process": {"pid": 4242, "pgid": 4242, "start_ticks": 123, "started_at": "2026-10-20T10:00:00Z"},
      "agent-request": {"agent_run_id": "agent-old-1", "role": "executor", "route": {"provider": "codex"},
                        "step": "executor.1", "attempt": 1, "prompt": "p.md", "started_at": "2026-10-20T10:00:00Z"},
      "agent-result": {"exit": 0, "decisions": [], "duration_s": 3.2, "stream": None, "lingered": False},
      "agent-usage": {"input": 17, "cached": 0, "output": 4, "usage_complete": True}}
FILES = {"process": "process.json", "agent-request": "request.json", "agent-result": "result.json",
         "agent-usage": "usage.json"}


def example(kind: str) -> dict:
    return json.loads((EXAMPLES / kind / SHORT[kind]).read_text(encoding="utf-8"))


class ShortTagTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_e1_write_read_write_keeps_the_bytes_and_only_the_published_tag(self):
        for kind in SHORT:
            with self.subTest(kind=kind):
                first, second = self.root / f"{kind}-1.json", self.root / f"{kind}-2.json"
                records.write(first, example(kind), kind)
                records.write(second, records.read(first, kind), kind)
                self.assertEqual(first.read_bytes(), second.read_bytes())
                doc = json.loads(first.read_text(encoding="utf-8"))
                self.assertEqual(doc["schema"], records.SHORT_TAGS[kind])
                self.assertNotIn("$schema", doc)

    def test_e2_a_short_kind_without_its_tag_is_read_with_schema_and_the_file_is_kept(self):
        for kind in SHORT:
            with self.subTest(kind=kind):
                path = self.root / f"{kind}.json"
                doc = {key: value for key, value in example(kind).items() if key != "schema"}
                path.write_text(json.dumps(doc), encoding="utf-8")
                before = path.read_bytes()
                found = records.read(path, kind)
                self.assertEqual(found["schema"], records.SHORT_TAGS[kind])
                self.assertNotIn("$schema", found)
                self.assertEqual(path.read_bytes(), before)
                stamped = self.root / f"{kind}-stamped.json"
                records.write(stamped, doc, kind)  # a write adds the published carrier, not $schema
                self.assertEqual(json.loads(stamped.read_text(encoding="utf-8"))["schema"], records.SHORT_TAGS[kind])

    def test_e3_a_review_verdict_with_dollar_schema_another_tag_or_both_is_refused(self):
        doc = example("review-verdict")
        bare = {key: value for key, value in doc.items() if key != "schema"}
        for variant in ({**bare, "$schema": "urn:swissknifeman:orch:records:review-verdict:v1"},
                        {**bare, "schema": "other/v1"},
                        {**doc, "$schema": "urn:swissknifeman:orch:records:review-verdict:v1"}):
            with self.subTest(variant={key: variant.get(key) for key in records.CARRIERS}):
                path = self.root / "review-verdict.json"
                path.write_text(json.dumps(variant), encoding="utf-8")
                before = path.read_bytes()
                with self.assertRaises(Stop) as caught:
                    records.read(path, "review-verdict")
                self.assertEqual(caught.exception.code, "RECORD_INVALID")
                self.assertIn(records.TAG_CONFLICT, caught.exception.message)
                self.assertEqual(path.read_bytes(), before)
                with self.assertRaises(Stop):
                    records.write(self.root / "out.json", variant, "review-verdict")
                self.assertFalse((self.root / "out.json").exists())

    def test_a_gates_file_with_dollar_schema_is_a_tag_conflict(self):
        path = self.root / "orch" / gates.FILE
        path.parent.mkdir()
        path.write_text(json.dumps({"$schema": "urn:swissknifeman:orch:records:provider-gates:v1", "gates": {}}),
                        encoding="utf-8")
        with self.assertRaises(gates.GateError) as caught:
            gates.active(0, file=path)
        self.assertIn(records.TAG_CONFLICT, caught.exception.message)

    def test_a_written_gates_file_keeps_its_published_tag_and_reads_back(self):
        path = self.root / "orch" / gates.FILE
        entry = gates.set_gate("codex", until=1_800_000_600, code="PROVIDER_QUOTA", run_id="r1", now=1_800_000_000,
                               file=path)
        doc = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((doc["schema"], "$schema" in doc), ("provider-gates/v1", False))
        self.assertEqual(records.read(path, "provider-gates")["gates"]["codex"], entry)

    def test_the_review_verdict_reads_as_a_reader_outside_orch_reads_it(self):
        # a reader of the published artifact takes the file with json.loads and no orch import: the shape is unchanged
        doc = example("review-verdict")
        path = self.root / "review-verdict.json"
        records.write(path, doc, "review-verdict")
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), doc)


class OldAgentRecordTests(unittest.TestCase):
    """(e5) process.json and the agent records written before records/v1 carry no tag."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.events = mock.patch.object(recovery.events, "emit")
        self.emitted = self.events.start()
        self.addCleanup(self.events.stop)

    def old_folder(self, name: str, kinds=("agent-request", "process")) -> Path:
        folder = self.directory / "W1" / agents.AGENTS / name
        folder.mkdir(parents=True)
        for kind in kinds:
            (folder / FILES[kind]).write_text(json.dumps(dict(V0[kind], agent_run_id=name) if kind == "agent-request"
                                                         else V0[kind]), encoding="utf-8")
        return folder

    def test_old_records_are_read_with_dollar_schema_and_the_files_are_not_touched(self):
        folder = self.old_folder("agent-old-1", tuple(FILES))
        for kind, name in FILES.items():
            with self.subTest(kind=kind):
                before = (folder / name).read_bytes()
                found = records.read(folder / name, kind)
                self.assertEqual(found["$schema"], records.TAGS[kind][1])
                self.assertNotIn("schema", found)
                self.assertEqual((folder / name).read_bytes(), before)
        self.assertEqual(agents.read(self.directory / "W1"),
                         [{"agent_run_id": "agent-old-1", "role": "executor", "step": "executor.1", "status": "ok",
                           "tokens": {"input": 17, "cached": 0, "output": 4}}])

    def test_resume_closes_an_orphan_of_an_old_run_and_of_a_new_one(self):
        old = self.old_folder("agent-old-1")
        new = agents.start(self.directory / "W1", "agent-new-2", role="executor", route={"provider": "codex"},
                           step="executor.1", attempt=1, prompt="p.md", parent=None,
                           started_at="2026-10-22T10:00:00Z")["directory"]
        records.write(new / "process.json", dict(V0["process"], pid=4343, pgid=4343), "process")
        before = (old / "process.json").read_bytes(), (old / "request.json").read_bytes()
        run = SimpleNamespace(directory=self.directory, state={"items": {"W1": {"steps": {}}}}, run_id="cnd-x",
                              settings=None, project=self.directory, config_file=None)
        with mock.patch.object(process, "start_ticks", return_value=999), \
                mock.patch.object(recovery.os, "killpg") as kill:
            recovery.kill_orphaned_roles(run)  # the pid now names another process: closed, never signalled
        kill.assert_not_called()
        self.assertEqual(((old / "process.json").read_bytes(), (old / "request.json").read_bytes()), before)
        for folder in (old, new):
            result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
            self.assertEqual((result["$schema"], result["error"]["code"]), (records.TAGS["agent-result"][1], "ORPHANED"))
        self.assertEqual([row["status"] for row in agents.read(self.directory / "W1")], ["failed", "failed"])
        self.assertEqual(self.emitted.call_count, 2)


if __name__ == "__main__":
    unittest.main()
