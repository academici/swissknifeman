"""Recovery refuses changed bytes and delivery receipts reflect actual readback."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from core.provider.lock import LOCK_RELATIVE_PATH, parse_lock
from core.provider.runtime import codex_migrated_command_skill
from skiller.common import MANIFEST, SKILL_MANAGED_MARKER
from skiller.delivery import (deliver, project_readback, prune_provider_caches,
                              recover_lock, release_history, verify_surface)
from skiller.release_attestation import digest, tree_digest


def surface(files, source="packages/task"):
    hashed = {path: digest(data) for path, data in files.items()}
    return {"source": source, "files": hashed, "tree_digest": tree_digest(hashed)}


def attestation(files):
    return {"schema_version": "release-attestation/v1",
            "umbrella": {"version": "1.0.0", "tag": "v1.0.0", "date": "2026-09-13"},
            "units": [{"id": "task", "version": "1.0.0",
                       "providers": {"codex": surface(files)}, "tree_digest": "unit"}]}


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def test_readback_rejects_unknown_extras_and_matching_symlink(self):
        self.write(self.root / "SKILL.md", b"managed")
        expected = surface({"SKILL.md": b"managed"})
        self.assertEqual(verify_surface(self.root, expected, reject_extras=True), [])
        self.write(self.root / "unexpected.txt", b"unknown")
        self.assertTrue(verify_surface(self.root, expected, reject_extras=True))
        self.write(self.root / "outside.txt", b"managed")
        (self.root / "SKILL.md").unlink()
        (self.root / "SKILL.md").symlink_to(self.root / "outside.txt")
        self.assertTrue(verify_surface(self.root, expected))

    def test_vendor_actual_flat_and_bucket_manifest_records_verify_managed_marker(self):
        canonical = b"---\nname: test\ndescription: test\n---\nBody\n"
        source = self.root / "source"
        self.write(source / "SKILL.md", canonical)
        marked = canonical.replace(b"---\nBody", b"---\n" + SKILL_MANAGED_MARKER.encode() + b"\nBody")
        for layout, record, destination in (
                ("flat", {"flat_name": "test", "source_path": str(source)}, "test"),
                ("bucket", {"path": "quality/test", "source_path": str(source)}, "quality/test")):
            with self.subTest(layout=layout):
                target = self.root / layout
                folder = target / ".ai/skills"
                self.write(folder / destination / "SKILL.md", marked)
                self.write(folder / MANIFEST, json.dumps({"layout": layout, "skills": [record]}).encode())
                rows = project_readback(target, attestation({}))
                self.assertTrue(rows)
                self.assertTrue(all(row["status"] == "current" for row in rows), rows)
                self.write(folder / destination / "SKILL.md", b"user edit")
                rows = project_readback(target, attestation({}))
                self.assertTrue(any(row["status"] != "current" for row in rows), rows)

    def test_provider_extra_requires_exact_source_bound_migration_bytes(self):
        source = self.root / "source"
        self.write(source / "commands/plan-design.md",
                   b"---\ndescription: Design a bounded plan\n---\nDo the declared work.\n")
        cache = self.root / "cache"
        self.write(cache / "SKILL.md", b"managed")
        expected = surface({"SKILL.md": b"managed"}, source=str(source))
        relative = ".codex-plugin/migrated-command-skills/source-command-plan-design/SKILL.md"
        generated = codex_migrated_command_skill(source, relative)
        self.assertIsNotNone(generated)
        self.write(cache / relative, generated)
        self.assertEqual(verify_surface(cache, expected, reject_extras=True), [])
        self.write(cache / relative, generated + b"\nModified instructions.")
        self.assertTrue(verify_surface(cache, expected, reject_extras=True))

    def test_native_cache_readback_allows_unattested_package_files(self):
        cache = self.root / "cache"
        self.write(cache / "SKILL.md", b"managed")
        self.write(cache / "docs/generated-search-index.json", b"cache state")
        expected = surface({"SKILL.md": b"managed"})
        self.assertEqual(verify_surface(cache, expected), [])
        self.assertTrue(verify_surface(cache, expected, reject_extras=True))

    def test_release_history_discovers_tagged_committed_snapshots(self):
        good = attestation({})
        good["umbrella"]["tag"] = "v0.9.0"
        calls = []

        def run(command, **_kwargs):
            calls.append(command)
            if command[1:3] == ["tag", "--list"]:
                return SimpleNamespace(stdout="v1.0.0\nv0.9.0\nv0.8.0\n", returncode=0)
            if command[-1] == "v0.9.0:releases/v0.9.0.json":
                return SimpleNamespace(stdout=json.dumps(good), returncode=0)
            if command[-1] == "v0.9.0^{commit}":
                return SimpleNamespace(stdout="0123456789abcdef\n", returncode=0)
            return SimpleNamespace(stdout="", returncode=1)

        with patch("skiller.delivery.subprocess.run", side_effect=run):
            discovered = release_history(self.root, "v1.0.0")
        self.assertEqual(discovered[0]["umbrella"], good["umbrella"])
        self.assertEqual(discovered[0]["_tag_commit"], "0123456789abcdef")
        self.assertNotIn(["git", "show", "v1.0.0:releases/v1.0.0.json"], calls)

    def test_cache_gc_prunes_only_unreferenced_exact_known_and_supports_dry_run(self):
        env = SimpleNamespace(home=self.root / "home")
        current = attestation({"SKILL.md": b"current"})
        current["units"][0]["version"] = "2.0.0"
        current["units"][0]["providers"]["claude-code"] = surface({"SKILL.md": b"current"})
        old = attestation({"SKILL.md": b"old"})
        old["units"][0]["version"] = "1.0.0"
        old["units"][0]["providers"]["claude-code"] = surface({"SKILL.md": b"old"})
        old["_tag_commit"] = "0123456789abcdef"
        cache = env.home / ".claude/plugins/cache/swissknifeman/task"
        self.write(env.home / ".claude/plugins/installed_plugins.json",
                   json.dumps({"plugins": {}}).encode())
        self.write(cache / "1.0.0/SKILL.md", b"old")
        self.write(cache / "0123456789ab/SKILL.md", b"old")
        self.write(cache / "2.0.0/SKILL.md", b"current")
        self.write(cache / "intermediate-sha/SKILL.md", b"current")
        self.write(cache / "mystery/SKILL.md", b"unknown")
        with patch("skiller.delivery.shutil.which", return_value=None):
            planned = prune_provider_caches(env, current, [old], dry_run=True)
        self.assertTrue((cache / "1.0.0").is_dir())
        self.assertEqual(next(row for row in planned if row["version"] == "1.0.0")["status"], "planned")
        self.assertEqual(next(row for row in planned if row["version"] == "0123456789ab")["status"], "planned")
        self.assertEqual(next(row for row in planned if row["version"] == "2.0.0")["classification"], "current")
        intermediate = next(row for row in planned if row["version"] == "intermediate-sha")
        self.assertEqual(intermediate["classification"], "exact-current-superseded")
        self.assertEqual(intermediate["status"], "planned")
        self.assertEqual(next(row for row in planned if row["version"] == "mystery")["status"], "blocked")
        with patch("skiller.delivery.shutil.which", return_value=None):
            applied = prune_provider_caches(env, current, [old])
        pruned = next(row for row in applied if row["version"] == "1.0.0")
        self.assertEqual(pruned["status"], "pruned")
        self.assertEqual(pruned["readback"], {"exists": False})
        self.assertFalse((cache / "1.0.0").exists())
        self.assertFalse((cache / "0123456789ab").exists())
        self.assertFalse((cache / "intermediate-sha").exists())
        self.assertTrue((cache / "mystery").exists())

    def test_cache_gc_preserves_declared_reference_even_when_superseded(self):
        env = SimpleNamespace(home=self.root / "home")
        current, old = attestation({}), attestation({"SKILL.md": b"old"})
        current["units"][0]["version"] = "2.0.0"
        old["units"][0]["version"] = "1.0.0"
        old["units"][0]["providers"]["claude-code"] = surface({"SKILL.md": b"old"})
        path = env.home / ".claude/plugins/cache/swissknifeman/task/1.0.0"
        self.write(path / "SKILL.md", b"old")
        installed = {"plugins": {"task@swissknifeman": [{"installPath": str(path)}]}}
        self.write(env.home / ".claude/plugins/installed_plugins.json", json.dumps(installed).encode())
        with patch("skiller.delivery.shutil.which", return_value=None):
            rows = prune_provider_caches(env, current, [old])
        self.assertEqual(rows[0]["classification"], "referenced")
        self.assertTrue(path.is_dir())

    def test_cache_gc_blocks_modified_known_cache(self):
        env = SimpleNamespace(home=self.root / "home")
        current, old = attestation({}), attestation({"SKILL.md": b"expected"})
        current["units"][0]["version"] = "2.0.0"
        old["units"][0]["version"] = "1.0.0"
        old["units"][0]["providers"]["claude-code"] = surface({"SKILL.md": b"expected"})
        path = env.home / ".claude/plugins/cache/swissknifeman/task/1.0.0"
        self.write(path / "SKILL.md", b"modified")
        self.write(env.home / ".claude/plugins/installed_plugins.json",
                   json.dumps({"plugins": {}}).encode())
        with patch("skiller.delivery.shutil.which", return_value=None):
            rows = prune_provider_caches(env, current, [old])
        self.assertEqual(rows[0]["status"], "blocked")
        self.assertEqual(rows[0]["classification"], "modified-or-unknown")
        self.assertTrue(path.is_dir())

    def test_recovery_refuses_symlink_even_when_known_bytes_match(self):
        target = self.root / "project"
        path = target / ".agents/plugins/bundles/task/SKILL.md"
        self.write(self.root / "external.md", b"known")
        path.parent.mkdir(parents=True)
        path.symlink_to(self.root / "external.md")
        rows, blocked = recover_lock(target, attestation({"SKILL.md": b"known"}), [], self.root / "backup")
        self.assertTrue(blocked)
        self.assertFalse((target / LOCK_RELATIVE_PATH).exists())
        self.assertEqual((self.root / "external.md").read_bytes(), b"known")

    def test_recovery_cannot_write_lock_through_symlinked_state_directory(self):
        target = self.root / "project"
        self.write(target / ".agents/plugins/bundles/task/SKILL.md", b"known")
        external = self.root / "external-state"
        external.mkdir()
        (target / ".swissknifeman").symlink_to(external, target_is_directory=True)
        try:
            rows, blocked = recover_lock(target, attestation({"SKILL.md": b"known"}), [], self.root / "backup")
        except ValueError:
            pass  # A containment error is also a fail-closed recovery result.
        else:
            self.assertTrue(blocked)
        self.assertFalse((external / "provider-artifacts.lock.json").exists())

    def test_known_old_recovers_ownership_without_changing_files(self):
        target = self.root / "project"
        path = target / ".agents/plugins/bundles/task/SKILL.md"
        self.write(path, b"old")
        current = attestation({"SKILL.md": b"current"})
        previous = attestation({"SKILL.md": b"old"})
        rows, blocked = recover_lock(target, current, [previous], self.root / "backup")
        self.assertEqual(blocked, [])
        self.assertEqual(rows[0]["classification"], "exact-known-old")
        self.assertEqual(path.read_bytes(), b"old")
        records = parse_lock((target / LOCK_RELATIVE_PATH).read_bytes()).records
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].rendered_hash, digest(b"old"))

    def test_modified_preimage_blocks_entire_recovery_and_dry_run_writes_no_lock(self):
        target = self.root / "project"
        known = target / ".agents/plugins/bundles/task/known.txt"
        modified = target / ".agents/plugins/bundles/task/SKILL.md"
        self.write(known, b"known")
        self.write(modified, b"user edit")
        current = attestation({"known.txt": b"known", "SKILL.md": b"current"})
        rows, blocked = recover_lock(target, current, [], self.root / "backup")
        self.assertTrue(blocked)
        self.assertFalse((target / LOCK_RELATIVE_PATH).exists())
        self.assertEqual(modified.read_bytes(), b"user edit")
        self.write(modified, b"current")
        rows, blocked = recover_lock(target, current, [], self.root / "backup", dry_run=True)
        self.assertFalse(blocked)
        self.assertFalse((target / LOCK_RELATIVE_PATH).exists())
        self.assertFalse((self.root / "backup").exists())

    def test_fleet_failure_keeps_other_roots_and_durable_partial_receipt(self):
        checkout = self.root / "checkout"
        value = attestation({})
        self.write(checkout / "releases/v1.0.0.json", json.dumps(value).encode())
        good, bad = self.root / "good", self.root / "bad"
        good.mkdir()
        bad.mkdir()
        env = SimpleNamespace(root=checkout, home=self.root / "home")

        def update(_env, target, **_kwargs):
            if target == bad:
                raise ValueError("broken-target")
            return True

        result = SimpleNamespace(stdout="abc\n", returncode=0)
        with patch("skiller.delivery.find_monorepo_root", return_value=checkout), \
                patch("skiller.delivery.check", return_value=[]), \
                patch("skiller.delivery.build", side_effect=ValueError("no-history")), \
                patch("skiller.delivery.subprocess.run", return_value=result), \
                patch("skiller.delivery.load_db", return_value={"projects": [{"path": str(good)}, {"path": str(bad)}]}), \
                patch("skiller.delivery.recover_lock", return_value=([], [])), \
                patch("skiller.delivery.update_one", side_effect=update), \
                patch("skiller.delivery.project_readback", return_value=[{"surface": "test", "status": "current"}]):
            receipt = deliver(env, "v1.0.0", all_projects=True, native=False)
        self.assertEqual(receipt["status"], "PARTIAL")
        statuses = {row["root"]: row["status"] for row in receipt["targets"]}
        self.assertEqual(statuses[str(good)], "updated")
        self.assertEqual(statuses[str(bad)], "blocked")
        self.assertEqual(json.loads(Path(receipt["receipt"]).read_text()), receipt)

    def test_native_claude_updates_project_scope_in_its_own_directory(self):
        checkout, project = self.root / "checkout", self.root / "project"
        project.mkdir()
        value = attestation({})
        value["units"][0]["providers"]["claude-code"] = surface({})
        self.write(checkout / "releases/v1.0.0.json", json.dumps(value).encode())
        env = SimpleNamespace(root=checkout, home=self.root / "home")
        cache = self.root / "cache"
        installation = {"scope": "local", "projectPath": str(project), "installPath": str(cache)}
        self.write(env.home / ".claude/plugins/installed_plugins.json", json.dumps({"plugins": {"task@swissknifeman": [installation]}}).encode())
        with patch("skiller.delivery.find_monorepo_root", return_value=checkout), \
                patch("skiller.delivery.check", return_value=[]), \
                patch("skiller.delivery.build", side_effect=ValueError("no-history")), \
                patch("skiller.delivery.subprocess.run", return_value=SimpleNamespace(stdout="abc\n", returncode=0)), \
                patch("skiller.delivery.shutil.which", side_effect=lambda name: name if name == "claude" else None), \
                patch("skiller.delivery._run", return_value=(True, "updated")) as runner:
            receipt = deliver(env, "v1.0.0")
        runner.assert_any_call(["claude", "plugin", "update", "task@swissknifeman", "--scope", "local", "--yes"], cwd=str(project))
        self.assertEqual(receipt["status"], "GREEN")
