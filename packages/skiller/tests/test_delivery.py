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
from skiller.delivery import deliver, project_readback, recover_lock, verify_surface
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
