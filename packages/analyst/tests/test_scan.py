"""Tests scan (P2): maind project registry, namespace-isolation, clustering, ≥N-gate, artifacts."""
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

from analyst import lessons, scan
from analyst.common import Env
from tests.maind_stub import install_maind_stub, without_maind


class TestScan(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _project(self, pid, namespaces, trigger, action):
        """Create a project directory with one ephemeral-lesson; return registry entry."""
        ppath = self.base / pid
        L = lessons.new_lesson(trigger=trigger, action=action, scope=f"project:{pid}",
                               session_id=f"s-{pid}")
        lessons.save_lesson(str(ppath), L, "ephemeral")
        return {"id": pid, "local_path": str(ppath), "namespaces": namespaces, "enabled": True}

    def test_load_and_enabled_filter(self):
        install_maind_stub(self, [
            {"id": "a", "local_path": "/x", "namespaces": ["axioma"], "enabled": True},
            {"id": "b", "local_path": "/y", "namespaces": ["axioma"], "enabled": False},
            {"id": "c", "local_path": "", "namespaces": ["axioma"], "enabled": True},
        ])
        projs = scan.load_projects()
        self.assertEqual(len(projs), 3)
        en = scan.enabled_projects(projs)
        self.assertEqual([p["id"] for p in en], ["a"])   # b disabled, c without local_path

    def test_cross_project_pattern_detected(self):
        # three projects of one namespace with a SIMILAR lesson → pattern
        trig, act = "laravel service placement in domain layer", "put service classes under Domain"
        projs = [self._project(pid, ["axioma"], trig, act) for pid in ("p1", "p2", "p3")]
        buckets = scan.gather_by_namespace(projs)
        self.assertIn("axioma", buckets)
        patterns = scan.detect_patterns(buckets, min_projects=3, threshold=0.5)
        self.assertEqual(len(patterns), 1)
        self.assertEqual(patterns[0]["weight"], 3)
        self.assertEqual(sorted(patterns[0]["projects"]), ["p1", "p2", "p3"])

    def test_below_threshold_projects_no_pattern(self):
        trig, act = "same trigger text here", "same action text here"
        projs = [self._project(pid, ["axioma"], trig, act) for pid in ("p1", "p2")]
        patterns = scan.detect_patterns(scan.gather_by_namespace(projs), min_projects=3)
        self.assertEqual(patterns, [])

    def test_namespace_isolation(self):
        # same lesson, but projects in DIFFERENT namespace → are NOT clustered together
        trig, act = "identical lesson trigger", "identical lesson action"
        projs = [
            self._project("p1", ["axioma"], trig, act),
            self._project("p2", ["axioma"], trig, act),
            self._project("p3", ["other"], trig, act),
        ]
        patterns = scan.detect_patterns(scan.gather_by_namespace(projs), min_projects=3)
        # axioma has only 2 projects, other — 1 → none namespace does not work ≥3
        self.assertEqual(patterns, [])

    def test_dissimilar_lessons_no_cluster(self):
        projs = [
            self._project("p1", ["axioma"], "laravel service domain", "domain layer"),
            self._project("p2", ["axioma"], "vue reactive refs", "use ref not reactive"),
            self._project("p3", ["axioma"], "docker compose networks", "bridge mode"),
        ]
        patterns = scan.detect_patterns(scan.gather_by_namespace(projs), min_projects=3)
        self.assertEqual(patterns, [])

    def test_write_artifacts(self):
        trig, act = "shared pattern trigger words", "shared pattern action words"
        projs = [self._project(pid, ["axioma"], trig, act) for pid in ("p1", "p2", "p3")]
        patterns = scan.detect_patterns(scan.gather_by_namespace(projs), min_projects=3)
        env = Env(self.base, "scan", home=self.home)
        written = scan.write_artifacts(env, patterns)
        self.assertEqual(len(written), 1)
        pid = written[0]
        idx = env.state_dir / "index" / "by_pattern" / f"{pid}.json"
        sug = env.state_dir / "suggestions" / f"{pid}.md"
        self.assertTrue(idx.is_file() and sug.is_file())
        data = json.loads(idx.read_text(encoding="utf-8"))
        self.assertEqual(data["weight"], 3)
        self.assertIn("Not a skill", sug.read_text(encoding="utf-8"))

    # ── reconcile / prune orphaned artifacts (P2-debt) ───────────────────
    def _seed_pattern(self, env, pid, namespace):
        """Seed to disk index+suggestion existing pattern (namespace — in FIELD)."""
        idx = env.state_dir / "index" / "by_pattern" / f"{pid}.json"
        sug = env.state_dir / "suggestions" / f"{pid}.md"
        idx.parent.mkdir(parents=True, exist_ok=True)
        sug.parent.mkdir(parents=True, exist_ok=True)
        idx.write_text(json.dumps({"pattern_id": pid, "namespace": namespace}), encoding="utf-8")
        sug.write_text("# stale draft", encoding="utf-8")
        return idx, sug

    def _run_json(self, env, argv):
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            scan.cmd_scan(env, argv + ["--json"])
        return json.loads(out.getvalue())

    def test_stale_scope_excludes_foreign_namespace(self):
        # Adversarial S2: scan --namespace A (written is empty, the pattern has disappeared) does NOT flag ns B obsolete.
        existing = [
            {"pattern_id": "axioma-x", "namespace": "axioma", "index_path": None, "suggestion_path": None},
            {"pattern_id": "other-y", "namespace": "other", "index_path": None, "suggestion_path": None},
        ]
        stale = scan.stale_pattern_ids(existing, written_ids=set(), scanned_namespaces={"axioma"})
        self.assertEqual(stale, {"axioma-x"})   # other-y OUT scope run → not an orphan

    def test_stale_written_kept(self):
        existing = [{"pattern_id": "axioma-live", "namespace": "axioma",
                     "index_path": None, "suggestion_path": None}]
        stale = scan.stale_pattern_ids(existing, {"axioma-live"}, {"axioma"})
        self.assertEqual(stale, set())          # regenerated by this run → alive

    def test_list_existing_patterns_skips_broken(self):
        env = Env(self.base, "scan", home=self.home)
        self._seed_pattern(env, "good-1", "axioma")
        (env.state_dir / "index" / "by_pattern" / "bad.json").write_text("{oops", encoding="utf-8")
        (env.state_dir / "index" / "by_pattern" / "noname.json").write_text(
            json.dumps({"pattern_id": "noname"}), encoding="utf-8")   # without namespace
        existing = scan.list_existing_patterns(env)
        self.assertEqual([e["pattern_id"] for e in existing], ["good-1"])

    def test_prune_artifacts_removes_both_missing_ok(self):
        env = Env(self.base, "scan", home=self.home)
        idx, sug = self._seed_pattern(env, "p-1", "axioma")
        sug.unlink()   # suggestion is already missing - missing_ok should not crash
        removed = scan.prune_artifacts(env, {"p-1", "absent"})
        self.assertEqual(removed, ["absent", "p-1"])
        self.assertFalse(idx.exists())

    def test_orphan_pruned_on_rescan(self):
        # registry: 1 enabled-project ns axioma, no patterns (<min) → orphaned file ns axioma is removed
        install_maind_stub(self, [self._project("p1", ["axioma"], "solo lesson trig", "solo action")])
        env = Env(self.base, "scan", home=self.home)
        idx, sug = self._seed_pattern(env, "axioma-orphan", "axioma")
        payload = self._run_json(env, [])
        self.assertEqual(payload["pruned"], ["axioma-orphan"])
        self.assertFalse(idx.exists() or sug.exists())   # index+suggestion synchronously removed

    def test_scoped_scan_does_not_prune_foreign_namespace(self):
        # Adversarial S2 (end-to-end): scan --namespace axioma does not touch files ns other
        install_maind_stub(self, [self._project("p1", ["axioma"], "trig words", "act words")])
        env = Env(self.base, "scan", home=self.home)
        a_idx, a_sug = self._seed_pattern(env, "axioma-orphan", "axioma")
        b_idx, b_sug = self._seed_pattern(env, "other-keep", "other")
        payload = self._run_json(env, ["--namespace", "axioma"])
        self.assertEqual(payload["pruned"], ["axioma-orphan"])
        self.assertFalse(a_idx.exists() or a_sug.exists())
        self.assertTrue(b_idx.exists() and b_sug.exists())   # alien ns not rescanned → untouched

    def test_dry_run_reports_but_does_not_delete(self):
        install_maind_stub(self, [self._project("p1", ["axioma"], "trig words", "act words")])
        env = Env(self.base, "scan", home=self.home)
        idx, sug = self._seed_pattern(env, "axioma-orphan", "axioma")
        payload = self._run_json(env, ["--dry-run"])
        self.assertEqual(payload["pruned"], ["axioma-orphan"])   # would-prune
        self.assertTrue(idx.exists() and sug.exists())            # but nothing was deleted

    def test_no_prune_keeps_orphans(self):
        install_maind_stub(self, [self._project("p1", ["axioma"], "trig words", "act words")])
        env = Env(self.base, "scan", home=self.home)
        idx, sug = self._seed_pattern(env, "axioma-orphan", "axioma")
        payload = self._run_json(env, ["--no-prune"])
        self.assertEqual(payload["pruned"], [])
        self.assertTrue(idx.exists() and sug.exists())

    def test_broken_index_not_deleted_and_scan_survives(self):
        install_maind_stub(self, [self._project("p1", ["axioma"], "trig words", "act words")])
        env = Env(self.base, "scan", home=self.home)
        bad = env.state_dir / "index" / "by_pattern" / "broken.json"
        bad.parent.mkdir(parents=True, exist_ok=True)
        bad.write_text("{ not json", encoding="utf-8")
        payload = self._run_json(env, [])           # does not drop scan
        self.assertNotIn("broken", payload["pruned"])
        self.assertTrue(bad.exists())               # unclassified is not deleted

    def test_nondefault_params_skip_autoprune(self):
        # [POSSIBLE-DEFECT] non-standard parameters → auto-prun skipped (protection against churn)
        install_maind_stub(self, [self._project("p1", ["axioma"], "trig words", "act words")])
        env = Env(self.base, "scan", home=self.home)
        idx, sug = self._seed_pattern(env, "axioma-orphan", "axioma")
        payload = self._run_json(env, ["--min-projects", "5"])
        self.assertEqual(payload["pruned"], [])
        self.assertTrue(idx.exists() and sug.exists())

    def test_cmd_scan_json_and_isolation_endtoend(self):
        trig, act = "cross project shared lesson", "the shared resolution action"
        projs = [self._project(pid, ["axioma"], trig, act) for pid in ("p1", "p2", "p3")]
        projs.append(self._project("lonely", ["solo"], trig, act))
        install_maind_stub(self, projs)
        env = Env(self.base, "scan", home=self.home)
        import io
        from contextlib import redirect_stdout
        out = io.StringIO()
        with redirect_stdout(out):
            scan.cmd_scan(env, ["--json"])
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["projects_scanned"], 4)
        self.assertEqual(len(payload["patterns"]), 1)   # only axioma (3), solo isolated (1)
        self.assertEqual(payload["patterns"][0]["namespace"], "axioma")

    def test_scan_without_maind_reports_partner_unavailable(self):
        without_maind(self)
        env = Env(self.base, "scan", home=self.home)
        err = io.StringIO()
        with self.assertRaises(SystemExit) as cm, redirect_stderr(err):
            scan.cmd_scan(env, ["--json"])
        self.assertEqual(cm.exception.code, 1)
        self.assertIn("PARTNER_UNAVAILABLE: maind not found (set SKM_MAIND_ROOT or put maind on PATH); "
                      "the cross-project scan needs the project registry", err.getvalue())
        self.assertNotIn("Traceback", err.getvalue())

    def test_scan_rejects_non_list_registry(self):
        install_maind_stub(self, {"projects": []})
        env = Env(self.base, "scan", home=self.home)
        err = io.StringIO()
        with self.assertRaises(SystemExit), redirect_stderr(err):
            scan.cmd_scan(env, ["--json"])
        self.assertIn("PARTNER_BAD_OUTPUT", err.getvalue())


if __name__ == "__main__":
    unittest.main()
