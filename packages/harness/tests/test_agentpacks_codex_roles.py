"""Internal documentation."""
import json
import tempfile
import unittest
from pathlib import Path

from harness import agentpacks as ap
from tests.fixtures import make_project, real_env


# repo-grounded: configs/common/agent-packs/roles.json).
_PACK = "role-maintainer"


def _install_claude_pack(proj, pack, prefix="acme"):
    lock_path = proj / ".claude" / "agent-pack.lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps({
        "schema": 1,
        "packs": {pack: {"version": "1.0.0", "answers": {"PACK_PREFIX": prefix}, "files": []}},
    }))


class CodexRoleLifecycleCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.env = real_env(self.tmp)
        self.proj = make_project(self.tmp, "p")


    def test_no_installed_pack_yields_no_projections(self):
        pairs, excluded = ap.expected_codex_role_projections(self.env, self.proj)
        self.assertEqual(pairs, ())
        self.assertEqual(excluded, ())


    def test_workflow_carrier_role_is_named_excluded(self):
        _install_claude_pack(self.proj, "_common")
        pairs, excluded = ap.expected_codex_role_projections(self.env, self.proj)
        self.assertEqual(pairs, ())
        self.assertEqual(len(excluded), 1)
        pack_id, role_id, reason = excluded[0]
        self.assertEqual((pack_id, role_id), ("_common", "orchestrator"))
        self.assertIn("command.workflow-carrier", reason)


    def test_render_creates_files_and_is_idempotent(self):
        _install_claude_pack(self.proj, _PACK)
        rc = ap.do_codex_role_render(self.env, self.proj)
        self.assertEqual(rc, 0)
        toml_files = sorted((self.proj / ".codex" / "agents").glob("*.toml"))
        self.assertGreater(len(toml_files), 0)
        for f in toml_files:
            self.assertTrue(f.name.startswith("acme-"))
        lock = ap.load_codex_roles_lock(self.proj)
        self.assertEqual(len(lock["roles"]), len(toml_files))

        before = {f: f.read_bytes() for f in toml_files}
        rc2 = ap.do_codex_role_render(self.env, self.proj)
        self.assertEqual(rc2, 0)
        for f, content in before.items():
            self.assertEqual(f.read_bytes(), content)


    def test_render_refuses_foreign_file(self):
        _install_claude_pack(self.proj, _PACK)
        pairs, _ = ap.expected_codex_role_projections(self.env, self.proj)
        target_path = self.proj / pairs[0][1].target_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text("foreign content, not ours\n")
        ap.do_codex_role_render(self.env, self.proj)
        self.assertEqual(target_path.read_text(), "foreign content, not ours\n")
        lock = ap.load_codex_roles_lock(self.proj)
        self.assertNotIn(pairs[0][1].target_path, lock.get("roles", {}))


    def test_render_repairs_managed_drift(self):
        _install_claude_pack(self.proj, _PACK)
        ap.do_codex_role_render(self.env, self.proj)
        pairs, _ = ap.expected_codex_role_projections(self.env, self.proj)
        target_path = self.proj / pairs[0][1].target_path
        target_path.write_text("locally edited\n")
        state = ap.codex_role_state(self.proj, pairs[0][1])
        self.assertEqual(state, "managed-drift")
        ap.do_codex_role_render(self.env, self.proj)
        self.assertEqual(target_path.read_bytes(), pairs[0][1].rendered)


    def test_doctor_reports_drift_with_strict(self):
        _install_claude_pack(self.proj, _PACK)
        ap.do_codex_role_render(self.env, self.proj)
        pairs, _ = ap.expected_codex_role_projections(self.env, self.proj)
        (self.proj / pairs[0][1].target_path).write_text("drifted\n")
        rc_clean = ap.do_codex_role_doctor(self.env, self.proj, json_out=True, strict=True)
        self.assertEqual(rc_clean, 1)
        rc_lenient = ap.do_codex_role_doctor(self.env, self.proj, json_out=True, strict=False)
        self.assertEqual(rc_lenient, 0)


    def test_remove_only_deletes_unmodified_files(self):
        _install_claude_pack(self.proj, _PACK)
        ap.do_codex_role_render(self.env, self.proj)
        pairs, _ = ap.expected_codex_role_projections(self.env, self.proj)
        drifted_path = self.proj / pairs[0][1].target_path
        drifted_path.write_text("locally edited, must survive remove\n")
        ap.do_codex_role_remove(self.env, self.proj, _PACK)
        self.assertTrue(drifted_path.exists())
        self.assertEqual(drifted_path.read_text(), "locally edited, must survive remove\n")
        for _role, projection in pairs[1:]:
            self.assertFalse((self.proj / projection.target_path).exists())
        lock = ap.load_codex_roles_lock(self.proj)
        self.assertIn(pairs[0][1].target_path, lock.get("roles", {}))


    def test_remove_all_clean_drops_lock_file(self):
        _install_claude_pack(self.proj, _PACK)
        ap.do_codex_role_render(self.env, self.proj)
        ap.do_codex_role_remove(self.env, self.proj, _PACK)
        self.assertEqual(list((self.proj / ".codex" / "agents").glob("*.toml")), [])
        self.assertFalse(ap.codex_roles_lock_path(self.proj).exists())


    def test_render_pack_filter_scopes_to_one_pack(self):
        _install_claude_pack(self.proj, _PACK)
        rc = ap.do_codex_role_render(self.env, self.proj, pack="nonexistent-pack")
        self.assertEqual(rc, 0)
        self.assertEqual(list((self.proj / ".codex" / "agents").glob("*.toml"))
                         if (self.proj / ".codex" / "agents").exists() else [], [])


if __name__ == "__main__":
    unittest.main()
