"""Tests analyst/pathology.py — detectors workflow-pathologies by run-report.

Fixtures - inlinedict's in the form of a real report SCHEMA=2 hook run-report
(the run-report hook of harness). Everyone
detector protected by a pair «fires / doesn't work»; separately - protective
contract: SCHEMA=1-the report and outright garbage are not dropped detect().

Launch: bash scripts/test.sh"""
import unittest

from analyst.pathology import detect


def base_report(**over):
    """Full «healthy» SCHEMA=2-report: not a single detector is triggered.
    Cases pointwise overlap the required sections through **over."""
    r = {
        "schema": 2,
        "tools": {"total": 10, "by_name": {"Read": 5, "Edit": 2, "Bash": 3}},
        "files_changed": [],
        "tool_failures": [],
        "bash": {"tests": [], "lints": [], "failed": []},
        "workflows": [],
        "devloop": None,
        "maind": None,
        "usage": {
            "totals": {"in": 1000, "out": 200, "cache_read": 9000, "cache_creation": 500},
            "by_model": {},
            "cache_hit": 0.9,
            "agents": [{
                "label": "main", "model": "claude-opus-4",
                "in": 1000, "out": 200, "cache_read": 9000, "cache_creation": 500,
                "msgs": 2, "thinking_chars": 100, "text_chars": 900, "tool_errors": 0,
            }],
            "subagents_parsed": 0, "subagents_skipped": 0,
        },
        "reads": {"total": 5, "unique": 5, "top_rereads": []},
        "error_loops": [],
        "retrieval": {"calls": 1, "by_tool": {"WebSearch": 1}, "result_chars": 100,
                      "queries": ["x"], "repeated_queries": []},
        "protected_writes": [],
    }
    r.update(over)
    return r


def codes(findings):
    return [f["code"] for f in findings]


def one(findings, code):
    """The only find with this code (crashes if there is not exactly one of them)."""
    hits = [f for f in findings if f["code"] == code]
    assert len(hits) == 1, f"1 find expected {code}, found {len(hits)}"
    return hits[0]


class TestContract(unittest.TestCase):
    """Protective contract: purity, form of discovery, degradation, no exceptions."""

    def test_healthy_report_is_clean(self):
        self.assertEqual(detect(base_report()), [])

    def test_non_dict_input(self):
        # not-dict input → empty list, no exception
        self.assertEqual(detect(None), [])
        self.assertEqual(detect([]), [])
        self.assertEqual(detect("trash"), [])

    def test_schema1_report_no_new_fields(self):
        # SCHEMA=1: no usage/reads/error_loops/retrieval/protected_writes —
        # detect does not crash on «calm» report is empty
        r = {"schema": 1,
             "tools": {"total": 5, "by_name": {"Read": 5}},
             "files_changed": [], "tool_failures": [],
             "bash": {"tests": [], "lints": [], "failed": []},
             "workflows": [], "devloop": None}
        self.assertEqual(detect(r), [])

    def test_schema1_partial_findings_still_work(self):
        # detectors living on SCHEMA=1-fields, work without SCHEMA=2-slices
        r = {"schema": 1, "tools": {"total": 3, "by_name": {}},
             "files_changed": ["/x.py"], "bash": {"tests": [], "lints": [], "failed": []}}
        self.assertIn("no-verify", codes(detect(r)))

    def test_garbage_values_do_not_crash(self):
        # garbage in all slices: detectors go out one by one, detect survives
        r = {"tools": [], "files_changed": "x", "bash": "no", "devloop": 42,
             "usage": 5, "reads": "y", "error_loops": {"a": 1},
             "retrieval": None, "protected_writes": None,
             "workflows": False}
        self.assertEqual(detect(r), [])
        r2 = base_report()
        r2["reads"] = {"total": "many", "unique": None, "top_rereads": "?"}
        r2["error_loops"] = [None, "x", {"tool": "Bash"}, {"len": "five"}]
        self.assertIsInstance(detect(r2), list)

    def test_finding_shape(self):
        r = base_report(protected_writes=["/p/skills/a/SKILL.md"])
        f = one(detect(r), "protected-write")
        self.assertEqual(set(f), {"code", "severity", "metric", "threshold",
                                  "evidence", "data"})
        self.assertIn(f["severity"], ("info", "attention"))
        self.assertIsInstance(f["evidence"], str)
        self.assertIsInstance(f["data"], dict)


class TestFileReread(unittest.TestCase):
    def test_fires(self):
        r = base_report(reads={"total": 20, "unique": 10,
                               "top_rereads": [{"path": "/a.py", "count": 6}]})
        f = one(detect(r), "file-reread")
        self.assertEqual(f["severity"], "attention")
        self.assertAlmostEqual(f["metric"], 0.5)
        self.assertIn("/a.py", f["evidence"])

    def test_quiet_below_ratio(self):
        r = base_report(reads={"total": 20, "unique": 13, "top_rereads": []})  # 0.35
        self.assertNotIn("file-reread", codes(detect(r)))

    def test_quiet_below_total(self):
        # the share is high, but there are few readings - no statistics
        r = base_report(reads={"total": 8, "unique": 2, "top_rereads": []})
        self.assertNotIn("file-reread", codes(detect(r)))


class TestToolErrorLoop(unittest.TestCase):
    def test_info_at_3(self):
        r = base_report(error_loops=[{"tool": "Bash", "len": 3, "snippet": "boom"}])
        f = one(detect(r), "tool-error-loop")
        self.assertEqual(f["severity"], "info")
        self.assertIn("Bash", f["evidence"])

    def test_attention_at_5(self):
        r = base_report(error_loops=[{"tool": "Edit", "len": 5, "snippet": "no line"},
                                     {"tool": "Bash", "len": 3, "snippet": "boom"}])
        found = [f for f in detect(r) if f["code"] == "tool-error-loop"]
        self.assertEqual([f["severity"] for f in found], ["attention", "info"])

    def test_quiet_short_series(self):
        r = base_report(error_loops=[{"tool": "Bash", "len": 2, "snippet": "x"}])
        self.assertNotIn("tool-error-loop", codes(detect(r)))


class TestNoOpRun(unittest.TestCase):
    def test_fires(self):
        r = base_report(tools={"total": 25, "by_name": {}},
                        retrieval={"calls": 0, "by_tool": {}, "result_chars": 0,
                                   "queries": [], "repeated_queries": []})
        self.assertEqual(one(detect(r), "no-op-run")["severity"], "info")

    def test_quiet_with_retrieval(self):
        r = base_report(tools={"total": 25, "by_name": {}})  # retrieval.calls=1 in the database
        self.assertNotIn("no-op-run", codes(detect(r)))

    def test_quiet_few_tools(self):
        r = base_report(retrieval={"calls": 0, "by_tool": {}, "result_chars": 0,
                                   "queries": [], "repeated_queries": []})
        self.assertNotIn("no-op-run", codes(detect(r)))


class TestNoVerify(unittest.TestCase):
    def test_fires_on_untested_changes(self):
        r = base_report(files_changed=["/x.py", "/y.py"])
        f = one(detect(r), "no-verify")
        self.assertEqual(f["severity"], "attention")
        self.assertEqual(f["metric"], 2)

    def test_quiet_when_tests_ran(self):
        r = base_report(files_changed=["/x.py"],
                        bash={"tests": [{"command": "pytest", "ok": True}],
                              "lints": [], "failed": []})
        self.assertNotIn("no-verify", codes(detect(r)))

    def test_devloop_without_verify(self):
        r = base_report(devloop={"tool_failures": [], "workarounds": ["hack"]})
        self.assertEqual(one(detect(r), "no-verify-devloop")["severity"], "info")

    def test_devloop_with_results_quiet(self):
        r = base_report(devloop={"results": ["ok"], "workarounds": []})
        self.assertNotIn("no-verify-devloop", codes(detect(r)))
        r = base_report(devloop={"verify": {"tests": "green"}})
        self.assertNotIn("no-verify-devloop", codes(detect(r)))


class TestCacheMiss(unittest.TestCase):
    def test_fires(self):
        r = base_report(usage={
            "totals": {"in": 150_000, "out": 1000, "cache_read": 50_000,
                       "cache_creation": 10_000},
            "by_model": {}, "cache_hit": 0.25, "agents": []})
        f = one(detect(r), "cache-miss")
        self.assertEqual(f["severity"], "info")
        self.assertIn("unstable prefix", f["evidence"])

    def test_quiet_small_volume(self):
        r = base_report(usage={
            "totals": {"in": 50_000, "out": 100, "cache_read": 10_000,
                       "cache_creation": 0},
            "by_model": {}, "cache_hit": 0.17, "agents": []})
        self.assertNotIn("cache-miss", codes(detect(r)))

    def test_quiet_cache_hit_none(self):
        # cache_hit=None (no login) — no signal and no crash
        u = base_report()["usage"]
        u["cache_hit"] = None
        self.assertNotIn("cache-miss", codes(detect(base_report(usage=u))))


class TestOverthinking(unittest.TestCase):
    def _agent(self, model, th, tx, label="agent-1"):
        return {"label": label, "model": model, "in": 100, "out": 50,
                "cache_read": 0, "cache_creation": 0, "msgs": 2,
                "thinking_chars": th, "text_chars": tx, "tool_errors": 0}

    def test_fires_on_haiku(self):
        u = base_report()["usage"]
        u["agents"] = u["agents"] + [self._agent("claude-haiku-4", 7000, 3000)]
        f = one(detect(base_report(usage=u)), "overthinking")
        self.assertEqual(f["severity"], "info")
        self.assertAlmostEqual(f["metric"], 0.7)

    def test_quiet_on_opus_same_ratio(self):
        u = base_report()["usage"]
        u["agents"] = u["agents"] + [self._agent("claude-opus-4", 7000, 3000)]
        self.assertNotIn("overthinking", codes(detect(base_report(usage=u))))

    def test_quiet_haiku_low_ratio(self):
        u = base_report()["usage"]
        u["agents"] = u["agents"] + [self._agent("claude-haiku-4", 3000, 7000)]
        self.assertNotIn("overthinking", codes(detect(base_report(usage=u))))


class TestRetrievalStuffing(unittest.TestCase):
    def _usage_in(self, tin):
        return {"totals": {"in": tin, "out": 100, "cache_read": 0,
                           "cache_creation": 0},
                "by_model": {}, "cache_hit": 0.5, "agents": []}

    def test_attention_with_repeats(self):
        # 20000 chars / 4 = 5000 current = 50% input 10000 + 2 repeated requests
        r = base_report(usage=self._usage_in(10_000),
                        retrieval={"calls": 4, "by_tool": {}, "result_chars": 20_000,
                                   "queries": ["a", "a2"], "repeated_queries": ["a", "a2"]})
        f = one(detect(r), "retrieval-stuffing")
        self.assertEqual(f["severity"], "attention")
        self.assertAlmostEqual(f["metric"], 0.5)

    def test_info_share_only(self):
        r = base_report(usage=self._usage_in(10_000),
                        retrieval={"calls": 2, "by_tool": {}, "result_chars": 20_000,
                                   "queries": ["a"], "repeated_queries": []})
        self.assertEqual(one(detect(r), "retrieval-stuffing")["severity"], "info")

    def test_quiet_small_share(self):
        r = base_report(usage=self._usage_in(100_000),
                        retrieval={"calls": 2, "by_tool": {}, "result_chars": 20_000,
                                   "queries": [], "repeated_queries": ["a", "b"]})
        self.assertNotIn("retrieval-stuffing", codes(detect(r)))


class TestProtectedWrite(unittest.TestCase):
    def test_fires_always(self):
        r = base_report(protected_writes=["/p/skills/a/SKILL.md"])
        f = one(detect(r), "protected-write")
        self.assertEqual(f["severity"], "attention")
        self.assertIn("/p/skills/a/SKILL.md", f["evidence"])

    def test_quiet_empty(self):
        self.assertNotIn("protected-write", codes(detect(base_report())))


class TestStaticContext(unittest.TestCase):
    def _usage(self, msgs, tin, cache_read):
        return {"totals": {"in": tin, "out": 500, "cache_read": cache_read,
                           "cache_creation": 0},
                "by_model": {}, "cache_hit": 0.9,
                "agents": [{"label": "main", "model": "claude-opus-4",
                            "in": tin, "out": 500, "cache_read": cache_read,
                            "cache_creation": 0, "msgs": msgs,
                            "thinking_chars": 0, "text_chars": 100,
                            "tool_errors": 0}]}

    def test_fires(self):
        # (100k+700k)/5 = 160k current/call = 80% windows > 70%, not enough tools
        r = base_report(usage=self._usage(5, 100_000, 700_000),
                        tools={"total": 10, "by_name": {}})
        f = one(detect(r), "static-context")
        self.assertEqual(f["severity"], "info")
        self.assertIn("skiller budget", f["evidence"])

    def test_quiet_many_tools(self):
        # the same difficult entrance, but a lot of work - it's not «hanging» context
        r = base_report(usage=self._usage(5, 100_000, 700_000),
                        tools={"total": 30, "by_name": {}})
        self.assertNotIn("static-context", codes(detect(r)))

    def test_quiet_few_msgs(self):
        r = base_report(usage=self._usage(2, 100_000, 300_000),
                        tools={"total": 5, "by_name": {}})
        self.assertNotIn("static-context", codes(detect(r)))


class TestFanout(unittest.TestCase):
    def _agents(self, n):
        return [{"label": f"agent-{i}", "model": "claude-sonnet-4", "in": 100,
                 "out": 50, "cache_read": 0, "cache_creation": 0, "msgs": 2,
                 "thinking_chars": 0, "text_chars": 100, "tool_errors": 0}
                for i in range(n)]

    def test_fires(self):
        u = base_report()["usage"]
        u["agents"] = self._agents(9)
        f = one(detect(base_report(usage=u)), "fanout")
        self.assertEqual(f["severity"], "info")
        self.assertEqual(f["metric"], 9)

    def test_quiet_enough_files(self):
        u = base_report()["usage"]
        u["agents"] = self._agents(9)
        r = base_report(usage=u,
                        files_changed=[f"/f{i}.py" for i in range(6)],
                        bash={"tests": [{"command": "pytest", "ok": True}],
                              "lints": [], "failed": []})
        self.assertNotIn("fanout", codes(detect(r)))

    def test_quiet_few_agents(self):
        u = base_report()["usage"]
        u["agents"] = self._agents(8)  # exactly 8 - strict threshold «>»
        self.assertNotIn("fanout", codes(detect(base_report(usage=u))))


if __name__ == "__main__":
    unittest.main()
