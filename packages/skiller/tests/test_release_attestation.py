"""Version identity is tied to delivered bytes, including the historical incident."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from skiller.release_attestation import Source, check_transition, tree_digest
import subprocess
import tempfile


class ReleaseAttestationTests(unittest.TestCase):
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
