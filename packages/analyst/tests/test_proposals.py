"""Tests proposals (P4.3): deterministic id, edit-safe writer (like suggest.py),
status via separate audit-line (history is not overwritten), handoff-print by type,
and invariant «zero records out the analyst state directory»."""
import io
import json
import re
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from analyst import proposals
from analyst.common import Env


class TestProposals(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.env = Env(self.base, "proposals", home=self.home)

    def tearDown(self):
        self._tmp.cleanup()

    def _run_json(self, argv):
        out = io.StringIO()
        with redirect_stdout(out):
            proposals.cmd_proposals(self.env, argv + ["--json"])
        return json.loads(out.getvalue())

    def _proposal_paths(self, ptype, pid):
        d = self.env.state_dir / "proposals" / ptype / pid
        return d / "PROPOSAL.md", d / "proposal.meta.json"

    # ── pure generators ─────────────────────────────────────────────────────
    def test_make_proposal_id_deterministic_and_type_scoped(self):
        id1 = proposals.make_proposal_id("stack-pack", "Single extension-point dev-loop")
        id2 = proposals.make_proposal_id("stack-pack", "Single extension-point dev-loop")
        self.assertEqual(id1, id2)
        # change title → other id
        id3 = proposals.make_proposal_id("stack-pack", "Another header")
        self.assertNotEqual(id1, id3)
        # same title, other type → other id (type is included in the hash)
        id4 = proposals.make_proposal_id("docs", "Single extension-point dev-loop")
        self.assertNotEqual(id1, id4)

    def test_build_proposal_md_deterministic_no_timestamp(self):
        pid = proposals.make_proposal_id("docs", "T")
        t1 = proposals.build_proposal_md("docs", pid, "T", "summary", "body", "docs/reference.md")
        t2 = proposals.build_proposal_md("docs", pid, "T", "summary", "body", "docs/reference.md")
        self.assertEqual(t1, t2)
        # none ISO-dates/time in body (determinism seed_sha256)
        self.assertNotRegex(t1, r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")

    def test_build_proposal_md_embeds_type_specific_handoff(self):
        pid = proposals.make_proposal_id("stack-pack", "T")
        md = proposals.build_proposal_md("stack-pack", pid, "T", "s", "b", "")
        self.assertIn("agent-packs", md)
        self.assertIn("harness agent-packs upgrade", md)

    def test_handoff_steps_differ_by_type(self):
        sp = proposals.handoff_steps("stack-pack")
        po = proposals.handoff_steps("project-override")
        docs = proposals.handoff_steps("docs")
        self.assertNotEqual(sp, po)
        self.assertNotEqual(po, docs)
        self.assertTrue(any("agent-packs" in s for s in sp))
        self.assertTrue(any("override" in s for s in po))
        self.assertTrue(any("docs/" in s for s in docs))

    def test_handoff_steps_unknown_type_falls_back_to_docs(self):
        self.assertEqual(proposals.handoff_steps("bogus"), proposals.handoff_steps("docs"))

    # ── create: entry + meta ────────────────────────────────────────────────
    def test_create_writes_md_and_meta_status_draft(self):
        payload = self._run_json(["create", "--type", "docs", "--title", "Additional amendment",
                                  "--summary", "summary", "--target", "docs/reference.md"])
        self.assertEqual(payload["write_status"], "created")
        self.assertEqual(payload["status"], "draft")
        md, meta_p = self._proposal_paths("docs", payload["id"])
        self.assertTrue(md.is_file() and meta_p.is_file())
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        self.assertEqual(meta["status"], "draft")
        self.assertEqual(meta["type"], "docs")
        self.assertEqual(meta["target"], "docs/reference.md")
        self.assertEqual(meta["seed_sha256"], proposals._seed_hash(md.read_text(encoding="utf-8")))

    def test_create_unknown_type_dies(self):
        with self.assertRaises(SystemExit):
            proposals.cmd_proposals(self.env, ["create", "--type", "bogus", "--title", "T"])

    def test_create_missing_title_dies(self):
        with self.assertRaises(SystemExit):
            proposals.cmd_proposals(self.env, ["create", "--type", "docs"])

    def test_create_body_file_missing_dies(self):
        with self.assertRaises(SystemExit):
            proposals.cmd_proposals(self.env, ["create", "--type", "docs", "--title", "T",
                                                "--body-file", str(self.base / "nope.txt")])

    # ── dry-run ───────────────────────────────────────────────────────────────
    def test_dry_run_writes_nothing(self):
        payload = self._run_json(["create", "--type", "docs", "--title", "T", "--dry-run"])
        self.assertEqual(payload["status"], "dry-run")
        md, _ = self._proposal_paths("docs", payload["id"])
        self.assertFalse(md.exists())

    # ── edit-safety (D6, like suggest.py) ────────────────────────────────────
    def test_recreate_unedited_updates_not_skips(self):
        p1 = self._run_json(["create", "--type", "docs", "--title", "T", "--summary", "s1"])
        # same input → unchanged
        p2 = self._run_json(["create", "--type", "docs", "--title", "T", "--summary", "s1"])
        self.assertEqual(p2["write_status"], "unchanged")
        # content has changed, the body was not controlled by hands → updated
        p3 = self._run_json(["create", "--type", "docs", "--title", "T", "--summary", "s2"])
        self.assertEqual(p3["write_status"], "updated")
        self.assertEqual(p1["id"], p3["id"])
        md, _ = self._proposal_paths("docs", p3["id"])
        self.assertIn("s2", md.read_text(encoding="utf-8"))

    def test_recreate_preserves_human_edits_and_status(self):
        p1 = self._run_json(["create", "--type", "docs", "--title", "T", "--summary", "s1"])
        self._run_json(["status", p1["id"], "accepted"])
        md, meta_p = self._proposal_paths("docs", p1["id"])
        md.write_text(md.read_text(encoding="utf-8") + "\nMANUAL EDITING\n", encoding="utf-8")

        p2 = self._run_json(["create", "--type", "docs", "--title", "T", "--summary", "s2"])
        self.assertEqual(p2["write_status"], "skipped-edited")
        self.assertIn("MANUAL EDITING", md.read_text(encoding="utf-8"))
        # status set BEFORE manual editing is not rolled back content-update
        self.assertEqual(json.loads(meta_p.read_text(encoding="utf-8"))["status"], "accepted")

        p3 = self._run_json(["create", "--type", "docs", "--title", "T", "--summary", "s2",
                             "--force"])
        self.assertEqual(p3["write_status"], "forced")
        self.assertNotIn("MANUAL EDITING", md.read_text(encoding="utf-8"))
        # --force also saves the status (does not rollback review-progress on draft)
        self.assertEqual(json.loads(meta_p.read_text(encoding="utf-8"))["status"], "accepted")

    # ── status: separate audit-line, history is not overwritten ──────────
    def test_status_transition_appends_audit_history(self):
        p1 = self._run_json(["create", "--type", "docs", "--title", "T"])
        pid = p1["id"]
        self._run_json(["status", pid, "accepted", "--note", "ok, apply"])
        self._run_json(["status", pid, "rejected", "--note", "changed their mind"])

        audit = proposals.read_audit(self.env)
        transitions = [a for a in audit if a.get("id") == pid]
        self.assertEqual(len(transitions), 2)
        self.assertEqual(transitions[0]["from"], "draft")
        self.assertEqual(transitions[0]["to"], "accepted")
        self.assertEqual(transitions[1]["from"], "accepted")
        self.assertEqual(transitions[1]["to"], "rejected")
        # final status - in meta.json (current pointer)
        _, meta_p = self._proposal_paths("docs", pid)
        self.assertEqual(json.loads(meta_p.read_text(encoding="utf-8"))["status"], "rejected")

    def test_status_same_value_is_noop_no_audit_duplicate(self):
        p1 = self._run_json(["create", "--type", "docs", "--title", "T"])
        pid = p1["id"]
        self._run_json(["status", pid, "accepted"])
        before = len(proposals.read_audit(self.env))
        self._run_json(["status", pid, "accepted"])   # same status again
        after = len(proposals.read_audit(self.env))
        self.assertEqual(before, after)

    def test_status_unknown_id_dies(self):
        with self.assertRaises(SystemExit):
            proposals.cmd_proposals(self.env, ["status", "missing", "accepted"])

    def test_status_invalid_value_dies(self):
        p1 = self._run_json(["create", "--type", "docs", "--title", "T"])
        with self.assertRaises(SystemExit):
            proposals.cmd_proposals(self.env, ["status", p1["id"], "bogus"])

    # ── list / show / handoff ────────────────────────────────────────────────
    def test_list_filters_by_type_and_status(self):
        self._run_json(["create", "--type", "docs", "--title", "A"])
        p_sp = self._run_json(["create", "--type", "stack-pack", "--title", "B"])
        self._run_json(["status", p_sp["id"], "accepted"])

        all_items = self._run_json(["list"])["proposals"]
        self.assertEqual(len(all_items), 2)

        docs_only = self._run_json(["list", "--type", "docs"])["proposals"]
        self.assertEqual(len(docs_only), 1)
        self.assertEqual(docs_only[0]["type"], "docs")

        accepted_only = self._run_json(["list", "--status", "accepted"])["proposals"]
        self.assertEqual([i["id"] for i in accepted_only], [p_sp["id"]])

    def test_show_returns_meta_and_body(self):
        p1 = self._run_json(["create", "--type", "docs", "--title", "T", "--summary", "resume"])
        payload = self._run_json(["show", p1["id"]])
        self.assertEqual(payload["meta"]["id"], p1["id"])
        self.assertIn("resume", payload["body"])

    def test_show_unknown_dies(self):
        with self.assertRaises(SystemExit):
            proposals.cmd_proposals(self.env, ["show", "missing"])

    def test_handoff_command_prints_type_specific_steps(self):
        p1 = self._run_json(["create", "--type", "project-override", "--title", "T",
                             "--target", "azguard"])
        payload = self._run_json(["handoff", p1["id"]])
        self.assertEqual(payload["type"], "project-override")
        joined = "\n".join(payload["handoff"])
        self.assertIn("override", joined)
        self.assertIn("azguard", joined)

    def test_unknown_subcommand_dies(self):
        with self.assertRaises(SystemExit):
            proposals.cmd_proposals(self.env, ["bogus"])

    def test_help_does_not_die(self):
        out = io.StringIO()
        with redirect_stdout(out):
            proposals.cmd_proposals(self.env, [])
        self.assertIn("proposals", out.getvalue())

    # ── invariant: zero records out ~/.swissknifeman/analyst/ ────────────────
    def test_zero_writes_outside_swissknifeman_analyst(self):
        allowed_root = self.home / ".local" / "state" / "swissknifeman" / "analyst"
        before = {str(p) for p in self.base.rglob("*")}

        p1 = self._run_json(["create", "--type", "stack-pack", "--title", "General extension-point",
                             "--summary", "s", "--target", "packages/harness/.../laravel-package"])
        self._run_json(["create", "--type", "docs", "--title", "Doc fix", "--summary", "s2"])
        self._run_json(["list"])
        self._run_json(["show", p1["id"]])
        self._run_json(["status", p1["id"], "accepted", "--note", "go"])
        self._run_json(["handoff", p1["id"]])
        # edit-safety path also writes (skipped-edited meta refresh)
        md, _ = self._proposal_paths("stack-pack", p1["id"])
        md.write_text(md.read_text(encoding="utf-8") + "\nmanual editing\n", encoding="utf-8")
        self._run_json(["create", "--type", "stack-pack", "--title", "General extension-point",
                        "--summary", "s-changed", "--target", "x"])
        # dry-run — shouldn't write anything either
        self._run_json(["create", "--type", "docs", "--title", "T2", "--dry-run"])

        after = {str(p) for p in self.base.rglob("*")}
        new_paths = after - before
        self.assertTrue(new_paths, "test did not execute any records - does not check the invariant")
        # the only valid marker paths OUTSIDE the tree analyst/ — its parent directories
        # (`~/.local/state/swissknifeman` and above, created on the first call); everything
        # else - strictly inside allowed_root.
        allowed_markers = {str(parent) for parent in allowed_root.parents}
        offenders = [p for p in new_paths
                     if p not in allowed_markers and not p.startswith(str(allowed_root))]
        self.assertEqual(offenders, [], f"records out {allowed_root}: {offenders}")


if __name__ == "__main__":
    unittest.main()
