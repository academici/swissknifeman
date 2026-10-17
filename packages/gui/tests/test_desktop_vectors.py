"""The desktop shell vectors (desktop/tests/vectors/*.json) checked by the Python oracle.

The same files are read by ``desktop/src-tauri/core/tests/vectors.rs``; they are the only source of expected values.
"""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import desktop_oracle as oracle  # noqa: E402

VECTORS = Path(__file__).resolve().parents[1] / "desktop" / "tests" / "vectors"


def load(name: str) -> dict:
    return json.loads((VECTORS / name).read_text(encoding="utf-8"))


class VectorIntegrity(unittest.TestCase):
    def test_minimum_sizes(self):
        self.assertGreaterEqual(len(load("adapter.json")["cases"]), 20)
        self.assertGreaterEqual(len(load("ready.json")["cases"]), 8)
        self.assertGreaterEqual(len(load("batch.json")["cases"]), 6)
        self.assertEqual([d["attempt"] for d in load("backoff.json")["delays"]], list(range(11)))

    def test_cases_are_named_and_unique(self):
        for file in ("adapter.json", "ready.json", "batch.json"):
            names = [c.get("name") for c in load(file)["cases"]]
            self.assertTrue(all(isinstance(n, str) and n for n in names), file)
            self.assertEqual(len(names), len(set(names)), file)
        names = [c.get("name") for c in load("backoff.json")["policy"]]
        self.assertEqual(len(names), len(set(names)))

    def test_cases_have_expect(self):
        for file in ("adapter.json", "ready.json"):
            for case in load(file)["cases"]:
                self.assertIn("expect", case, case["name"])
        for case in load("backoff.json")["policy"]:
            self.assertIn("expect", case, case["name"])
        for case in load("batch.json")["cases"]:
            polls = [op for op in case["ops"] if op["op"] == "poll"]
            self.assertTrue(polls, case["name"])
            self.assertTrue(all("expect" in op for op in polls), case["name"])

    def test_adapter_covers_the_required_inputs(self):
        cases = {c["name"]: c for c in load("adapter.json")["cases"]}
        paths = {c["path"] for c in cases.values()}
        for path in ("/v1/../x", "/v1/%2e%2e/x", "/v1/a\\b", "/v1/a\u0000b", "/v1/a b", "/v1/a#frag", "http://x/v1/"):
            self.assertIn(path, paths)
        self.assertIn("/v1/" + "a" * 2045, paths)
        bodies = {c["body_len"] for c in cases.values()}
        self.assertTrue({1048576, 1048577} <= bodies)
        methods = {c["method"] for c in cases.values()}
        self.assertTrue({"GET", "POST", "PATCH", "DELETE", "PUT", "HEAD"} <= methods)


class AdapterVectors(unittest.TestCase):
    def test_cases(self):
        for case in load("adapter.json")["cases"]:
            with self.subTest(case["name"]):
                code = oracle.validate_request(case["method"], case["path"], case["body_len"])
                expect = case["expect"]
                self.assertEqual({"ok": True} if code is None else {"error": code}, expect)


class ReadyVectors(unittest.TestCase):
    def test_cases(self):
        for case in load("ready.json")["cases"]:
            with self.subTest(case["name"]):
                parsed = oracle.parse_ready(case["line"])
                expect = case["expect"]
                self.assertEqual({"error": "READY_INVALID"} if parsed is None else {"ok": parsed}, expect)


class BackoffVectors(unittest.TestCase):
    def test_delay_table(self):
        for row in load("backoff.json")["delays"]:
            with self.subTest(row["attempt"]):
                self.assertEqual(oracle.backoff_delay(row["attempt"]), row["ms"])

    def test_policy(self):
        for case in load("backoff.json")["policy"]:
            with self.subTest(case["name"]):
                policy = oracle.Policy()
                got = []
                for event in case["events"]:
                    if event == "reset":
                        policy.reset()
                        got.append(None)
                    else:
                        got.append(policy.on_exit(event["started_ms"], event["exited_ms"]))
                self.assertEqual(got, case["expect"])


class BatchVectors(unittest.TestCase):
    def test_cases(self):
        limits = load("batch.json")["limits"]
        for case in load("batch.json")["cases"]:
            with self.subTest(case["name"]):
                batcher = oracle.Batcher(limits["max_frames"], limits["max_age_ms"], limits["queue_limit"])
                for op in case["ops"]:
                    if op["op"] == "push":
                        batcher.push(op["frame"], op["t"])
                    elif op["op"] == "push_n":
                        for i in range(op.get("start", 0), op.get("start", 0) + op["count"]):
                            batcher.push(f"{op['prefix']}{i}", op["t"])
                    else:
                        got = batcher.poll(op["t"])
                        if got is None:
                            self.assertIsNone(op["expect"], case["name"])
                        else:
                            frames, dropped = got
                            self.assertEqual(
                                {"count": len(frames), "first": frames[0], "last": frames[-1], "dropped": dropped},
                                op["expect"],
                            )


if __name__ == "__main__":
    unittest.main()
