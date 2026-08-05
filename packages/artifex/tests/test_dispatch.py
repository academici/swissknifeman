from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from artifex import dispatch


ROOT = Path(__file__).resolve().parents[3]
PLAN = ROOT / "plans" / ("2026" + ".08.03-ARTIFEX-SUPERVISOR")
P1 = PLAN / "artifacts/P1"
P2 = PLAN / "artifacts/P2"


class DispatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admission_path = P2 / "p3-smoke-admissions/codex.json"
        cls.admission = json.loads(cls.admission_path.read_text(encoding="utf-8"))

    def test_committed_admissions_are_exactly_indexed_and_verified(self):
        index = json.loads((P2 / "p3-smoke-admission-index-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(2, len(index["admissions"]))
        seen = set()
        for row in index["admissions"]:
            value = dispatch.load_indexed_admission(PLAN, PLAN / row["path"])
            self.assertEqual(row["task_id"], value["task"]["task_id"])
            self.assertEqual(row["provider"], value["task"]["provider"])
            self.assertEqual(0, value["usage"]["used_slices"])
            seen.add((row["task_id"], row["provider"]))
        self.assertEqual(2, len(seen))

    def test_parent_item_grant_index_and_cross_provider_inputs_refuse_before_projection(self):
        with self.assertRaisesRegex(dispatch.DispatchRefusal, "PARENT_ITEM_AS_TASK"):
            dispatch.verify_task({"schema_version": "task-contract/v1"})
        with self.assertRaisesRegex(dispatch.DispatchRefusal, "UNKNOWN_SCHEMA_VERSION"):
            dispatch.verify_admission(self.admission["grant"])
        malformed = copy.deepcopy(self.admission)
        malformed["dispatch"]["provider"] = "other"
        malformed["admission_hash"] = dispatch.canonical_hash(malformed, "admission_hash")
        with self.assertRaisesRegex(dispatch.DispatchRefusal, "IDENTITY_MISMATCH"):
            dispatch.verify_admission(malformed)
        with tempfile.TemporaryDirectory() as temp:
            foreign = Path(temp) / "grant.json"; foreign.write_text(json.dumps(self.admission["grant"]), encoding="utf-8")
            with self.assertRaisesRegex(dispatch.DispatchRefusal, "ADMISSION_NOT_INDEXED"):
                dispatch.load_indexed_admission(PLAN, foreign)

    def test_hash_usage_and_replay_mutations_refuse(self):
        for path, expected in (("admission_hash", "ADMISSION_HASH_MISMATCH"), ("usage", "REPLAY_INVALID")):
            value = copy.deepcopy(self.admission)
            if path == "admission_hash":
                value[path] = "f" * 64
            else:
                value[path]["used_slices"] = 1
                value["admission_hash"] = dispatch.canonical_hash(value, "admission_hash")
            with self.subTest(path=path), self.assertRaisesRegex(dispatch.DispatchRefusal, expected):
                dispatch.verify_admission(value)
        task, grant = self.admission["task"], self.admission["grant"]
        identity = self.admission["dispatch"]
        replay = [{"event": "dispatch_intent", "grant_id": grant["grant_id"], "task_id": task["task_id"],
                   "idempotency_key": "f" * 64}]
        with self.assertRaisesRegex(dispatch.DispatchRefusal, "USAGE_LIMIT_EXCEEDED"):
            dispatch.strict_replay(replay, task, grant, identity)

    def test_builder_reproduces_committed_carriers_byte_for_byte(self):
        spec = importlib.util.spec_from_file_location("admission_builder", P2 / "build-p3-smoke-admissions.py")
        module = importlib.util.module_from_spec(spec); assert spec.loader is not None; spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "plan"; output = root / "artifacts/P2/p3-smoke-admissions"
            replay, manifest, admission = root / "artifacts/P2/p3-smoke-replay-v1.jsonl", root / "artifacts/P2/p3-smoke-dispatch-manifest-index-v1.json", root / "artifacts/P2/p3-smoke-admission-index-v1.json"
            module.build(P1 / "p3-smoke-task-set-v1.json", P1 / "p3-smoke-dispatch-grants-v1.json", replay, manifest, admission, output)
            for generated, committed in ((replay, P2 / replay.name), (manifest, P2 / manifest.name), (admission, P2 / admission.name),
                                         (output / "codex.json", P2 / "p3-smoke-admissions/codex.json"),
                                         (output / "claude-code.json", P2 / "p3-smoke-admissions/claude-code.json")):
                self.assertEqual(committed.read_bytes(), generated.read_bytes(), generated.name)


if __name__ == "__main__":
    unittest.main()
