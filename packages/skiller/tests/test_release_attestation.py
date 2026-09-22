"""Version identity is tied to delivered bytes, including the historical incident."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from skiller.release_attestation import (Source, check_transition, surface, tree_digest,
                                         version_errors)
import subprocess
import tempfile


class ReleaseAttestationTests(unittest.TestCase):
    def test_byte_consistent_snapshot_still_rejects_stale_expected_task_version(self):
        value = {"units": [{
            "id": "task", "version": "0.21.0", "expected_version": "0.24.0",
            "version_source": "umbrella", "required_providers": ["claude-code", "codex"],
            "provider_versions": {"claude-code": "0.21.0", "codex": "0.21.0"},
            "providers": {"claude-code": {}, "codex": {}},
        }]}
        errors = version_errors(value)
        self.assertIn(
            "RELEASE_EXPECTED_VERSION_MISMATCH: task expected 0.24.0 from umbrella, got 0.21.0",
            errors)
        self.assertIn(
            "RELEASE_VERSION_SURFACE_MISMATCH: task codex=0.21.0, expected 0.24.0",
            errors)

    def test_version_surfaces_and_required_providers_are_independent_gates(self):
        value = {"units": [{
            "id": "task", "version": "0.24.0", "expected_version": "0.24.0",
            "version_source": "umbrella", "required_providers": ["claude-code", "codex"],
            "provider_versions": {"claude-code": "0.23.0"},
            "providers": {"claude-code": {}},
        }]}
        self.assertEqual(version_errors(value), [
            "RELEASE_VERSION_SURFACE_MISMATCH: task claude-code=0.23.0, expected 0.24.0",
            "RELEASE_PROVIDER_MISSING: task codex",
        ])

    def test_live_source_ignores_ambient_ignored_telemetry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", folder], check=True)
            (root / ".gitignore").write_text("telemetry/\n")
            (root / "lib").mkdir()
            (root / "lib/source.py").write_text("source\n")
            (root / "lib/telemetry").mkdir()
            (root / "lib/telemetry/session.json").write_text("ambient\n")
            self.assertEqual(Source(root).files("lib"), ["lib/source.py"])

    def test_deleted_tracked_files_change_live_surface_without_breaking_historical_ref(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", folder], check=True)
            (root / "skills").mkdir()
            (root / "skills/keep.md").write_text("retained capability\n")
            removed = root / "skills/removed.md"
            removed.write_text("removed CORE member\n")
            subprocess.run(["git", "add", "skills"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                            "commit", "-qm", "fixture"], cwd=root, check=True)
            previous = surface(Source(root, "HEAD"), "skills", ["."])
            removed.unlink()  # Deliberately leave the deleted path in the git index.
            current = surface(Source(root), "skills", ["."])
            self.assertEqual(set(current["files"]), {"keep.md"})
            self.assertEqual(set(previous["files"]), {"keep.md", "removed.md"})
            self.assertEqual(surface(Source(root, "HEAD"), "skills", ["."]), previous)
            def release(value, version="1.0.0"):
                return {"units": [{"id": "core", "version": version,
                                   "providers": {"codex": value},
                                   "tree_digest": value["tree_digest"]}]}
            self.assertEqual(check_transition(release(previous), release(current)),
                             ["RELEASE_IMMUTABLE_TUPLE: core@1.0.0"])
            self.assertEqual(check_transition(release(previous), release(current, "1.0.1")), [])

    def test_missing_and_external_symlink_targets_are_not_treated_as_deletions(self):
        for outside in (False, True):
            with self.subTest(outside=outside), tempfile.TemporaryDirectory() as folder:
                root = Path(folder) / "repo"
                root.mkdir()
                subprocess.run(["git", "init", "-q", str(root)], check=True)
                (root / "skills").mkdir()
                link = root / "skills/broken.md"
                target = Path(folder) / "outside.md" if outside else root / "missing.md"
                link.symlink_to(target)
                source = Source(root)
                self.assertIn("skills/broken.md", source.files("skills"))
                with self.assertRaises(ValueError if outside else FileNotFoundError):
                    surface(source, "skills", ["."])

    def test_deleted_path_below_replaced_symlink_parent_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            parent = root / "skills"
            parent.mkdir()
            (parent / "tracked.md").write_text("tracked\n")
            subprocess.run(["git", "add", "skills/tracked.md"], cwd=root, check=True)
            (parent / "tracked.md").unlink()
            parent.rmdir()
            parent.symlink_to(Path(folder) / "missing-outside")
            source = Source(root)
            self.assertIn("skills/tracked.md", source.files("skills"))
            with self.assertRaisesRegex(ValueError, "RELEASE_PATH_UNCONTAINED"):
                source.read("skills/tracked.md")

    def test_added_native_proof_does_not_change_old_bytes(self):
        old = {"units": [{"id": "task", "version": "1.0.0", "providers": {"codex": {"tree_digest": "same"}}, "tree_digest": "old-proof"}]}
        new = deepcopy(old)
        new["units"][0]["providers"]["codex-native"] = {"tree_digest": "additional-proof"}
        new["units"][0]["tree_digest"] = "expanded-proof"
        self.assertEqual(check_transition(old, new), [])
        new["units"][0]["providers"]["codex"]["tree_digest"] = "changed-bytes"
        self.assertEqual(check_transition(old, new), ["RELEASE_IMMUTABLE_TUPLE: task@1.0.0"])

    def test_tree_digest_is_order_independent_and_path_sensitive(self):
        self.assertEqual(tree_digest({"a": "one", "b": "two"}),
                         tree_digest({"b": "two", "a": "one"}))
        self.assertNotEqual(tree_digest({"a": "one"}), tree_digest({"b": "one"}))

    def test_unchanged_unit_needs_no_bump_but_changed_bytes_do(self):
        previous = {"units": [{"id": "task", "version": "1.0.0", "tree_digest": "old"}]}
        current = deepcopy(previous)
        self.assertEqual(check_transition(previous, current), [])
        current["units"][0]["tree_digest"] = "new"
        self.assertEqual(check_transition(previous, current),
                         ["RELEASE_IMMUTABLE_TUPLE: task@1.0.0"])
        current["units"][0]["version"] = "1.0.1"
        self.assertEqual(check_transition(previous, current), [])

    def test_recorded_v014_to_v015_incident_rejects_core_and_task(self):
        fixture = json.loads((Path(__file__).parent / "fixtures_data/release-immutable-incident.json").read_text())
        errors = check_transition(fixture["v0.14.0"], fixture["v0.15.0"])
        self.assertIn("RELEASE_IMMUTABLE_TUPLE: core@0.13.1", errors)
        self.assertIn("RELEASE_IMMUTABLE_TUPLE: task@0.13.3", errors)
