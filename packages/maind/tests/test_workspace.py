"""Tests workspace — single trust space Claude Code (hub-scoped).

The most security-sensitive primitive next to mcpconfig: entry in
.claude/settings.local.json must be additive (do not overwrite someone else's) and idempotent."""
import json
import tempfile
import unittest
from pathlib import Path

from aicore.state import list_backups
from maind.provision import workspace
from maind.provision import sync
from maind.config import merge_defaults
from maind.probe import probe_project
from tests.fixtures import make_repo


def _cfg(paths):
    """Config with projects according to given (id, local_path[, enabled]) tuples."""
    projects = []
    for item in paths:
        pid, lp = item[0], item[1]
        rec = {"id": pid, "name": pid.title(), "local_path": lp}
        if len(item) > 2:
            rec["enabled"] = item[2]
        projects.append(rec)
    return {"projects": projects}


class TestEligiblePaths(unittest.TestCase):
    def test_filters_disabled_missing_and_pathless(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "a"; a.mkdir()
            b = Path(tmp) / "b"; b.mkdir()
            cfg = _cfg([
                ("a", str(a)),
                ("b", str(b), False),                 # disabled → pass
                ("ghost", str(Path(tmp) / "nope")),   # no directory → pass
                ("nopath", None),                     # no local_path → pass
            ])
            self.assertEqual(workspace.eligible_paths(cfg), [str(a)])

    def test_sorted_unique(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "z"; a.mkdir()
            b = Path(tmp) / "m"; b.mkdir()
            cfg = _cfg([("z", str(a)), ("m", str(b)), ("dup", str(a))])
            self.assertEqual(workspace.eligible_paths(cfg), sorted([str(a), str(b)]))


class TestBuildFragment(unittest.TestCase):
    def test_dirs_allow_double_slash_and_mode(self):
        frag = workspace.build_fragment(["/home/u/proj"], allow=True, mode=True)
        perms = frag["permissions"]
        self.assertEqual(perms["additionalDirectories"], ["/home/u/proj"])
        self.assertIn("Read(//home/u/proj/**)", perms["allow"])  # absolute path → //
        self.assertIn("Edit(//home/u/proj/**)", perms["allow"])
        self.assertEqual(perms["defaultMode"], "acceptEdits")

    def test_toggles(self):
        frag = workspace.build_fragment(["/x"], allow=False, mode=False)
        self.assertNotIn("allow", frag["permissions"])
        self.assertNotIn("defaultMode", frag["permissions"])


class TestMergeSettings(unittest.TestCase):
    def test_preserves_foreign_and_unions(self):
        existing = {
            "permissions": {
                "additionalDirectories": ["/keep/me"],
                "deny": ["Bash(rm*)"],            # someone else's key - don't touch it
                "allow": ["Bash(git*)"],
            },
            "hooks": {"x": 1},                    # extraneous upper key - do not touch
        }
        frag = workspace.build_fragment(["/new/dir"], allow=True, mode=True)
        merged, changed = workspace.merge_settings(existing, frag)
        self.assertTrue(changed)
        perms = merged["permissions"]
        self.assertIn("/keep/me", perms["additionalDirectories"])
        self.assertIn("/new/dir", perms["additionalDirectories"])
        self.assertIn("Bash(git*)", perms["allow"])      # alien allow saved
        self.assertIn("Read(//new/dir/**)", perms["allow"])
        self.assertEqual(perms["deny"], ["Bash(rm*)"])   # deny untouched
        self.assertEqual(merged["hooks"], {"x": 1})

    def test_does_not_override_user_mode(self):
        existing = {"permissions": {"defaultMode": "plan"}}
        frag = workspace.build_fragment(["/x"], allow=False, mode=True)
        merged, _ = workspace.merge_settings(existing, frag)
        self.assertEqual(merged["permissions"]["defaultMode"], "plan")  # user selection

    def test_idempotent(self):
        frag = workspace.build_fragment(["/x"], allow=True, mode=True)
        merged1, c1 = workspace.merge_settings({}, frag)
        merged2, c2 = workspace.merge_settings(merged1, frag)
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(merged1, merged2)

    def test_does_not_mutate_input(self):
        existing = {"permissions": {"additionalDirectories": ["/a"]}}
        frag = workspace.build_fragment(["/b"], allow=False, mode=False)
        workspace.merge_settings(existing, frag)
        self.assertEqual(existing["permissions"]["additionalDirectories"], ["/a"])


class TestSync(unittest.TestCase):
    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            _root, env = make_repo(tmp)
            proj = Path(tmp) / "proj"; proj.mkdir()
            cfg = _cfg([("p", str(proj))])
            r = workspace.sync(env, cfg, dry=True)
            self.assertTrue(r["changed"])
            self.assertFalse(workspace.hub_settings_path(env).exists())

    def test_writes_then_idempotent_then_backup_on_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            _root, env = make_repo(tmp)
            a = Path(tmp) / "a"; a.mkdir()
            b = Path(tmp) / "b"; b.mkdir()
            path = workspace.hub_settings_path(env)
            def saved():
                return list_backups(env.root)

            r1 = workspace.sync(env, _cfg([("a", str(a))]))
            self.assertTrue(r1["changed"])
            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertIn(str(a), data["permissions"]["additionalDirectories"])
            self.assertEqual(data["permissions"]["defaultMode"], "acceptEdits")
            self.assertEqual(saved(), [])  # first entry - there was no file, nothing to back up

            r2 = workspace.sync(env, _cfg([("a", str(a))]))
            self.assertFalse(r2["changed"])  # idempotent - we don’t write anything
            self.assertEqual(saved(), [])

            r3 = workspace.sync(env, _cfg([("a", str(a)), ("b", str(b))]))
            self.assertTrue(r3["changed"])
            self.assertEqual(r3["dirs_added"], [str(b)])
            # real change → a backup under .swissknifeman/backups before recording
            [(_stamp, files)] = saved()
            self.assertEqual([f.relative_to(f.parents[1]) for f in files],
                             [Path(".claude/settings.local.json")])

    def test_broken_settings_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            _root, env = make_repo(tmp)
            path = workspace.hub_settings_path(env)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{ broken", encoding="utf-8")
            with self.assertRaises(SystemExit):
                workspace.sync(env, _cfg([]))


class TestAudit(unittest.TestCase):
    def test_covered_missing_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            _root, env = make_repo(tmp)
            a = Path(tmp) / "a"; a.mkdir()
            b = Path(tmp) / "b"; b.mkdir()
            # trust only a + one extra path (drift)
            workspace.sync(env, _cfg([("a", str(a))]))
            cfg = _cfg([("a", str(a)), ("b", str(b))])
            au = workspace.audit(env, cfg)
            self.assertEqual([c["id"] for c in au["covered"]], ["a"])
            self.assertEqual([m["id"] for m in au["missing"]], ["b"])
            self.assertEqual(au["registry_count"], 2)


class TestProviderTrust(unittest.TestCase):
    def test_codex_trust_and_full_access_are_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            _root, env = make_repo(tmp)
            project = Path(tmp) / "codex"; project.mkdir()
            config = merge_defaults({"projects": [{"id": "codex", "name": "Codex",
                "local_path": str(project), "providers": {"contract_version": "1.0.0",
                "selection": {"claude-code": {"enabled": False}, "codex": {"enabled": True}}}}]})
            context = sync.contexts(env, config, config["projects"])[0]
            untrusted = workspace.provider_trust(context, trusted=False)
            self.assertEqual(untrusted[0]["provider_id"], "codex")
            self.assertIn("HARNESS_TRUST_REQUIRED", untrusted[0]["diagnostics"])
            trusted = workspace.provider_trust(context, trusted=True)
            self.assertTrue(trusted[0]["green"])
            full = workspace.provider_trust(context, trusted=True,
                profile_id="trusted-full-access")
            self.assertIn("HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED", full[0]["diagnostics"])

    def test_legacy_probe_shape_is_unchanged_without_provider_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            _root, env = make_repo(tmp)
            project = Path(tmp) / "legacy"; project.mkdir()
            config = merge_defaults({"projects": [{"id": "legacy", "name": "Legacy",
                "local_path": str(project)}]})
            report = probe_project(env, config, config["projects"][0], memory_reachable=False)
            self.assertIn("trusted", report)
            self.assertNotIn("provider_trust", report)


if __name__ == "__main__":
    unittest.main()
