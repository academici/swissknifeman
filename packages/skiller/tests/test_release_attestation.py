"""Version identity is tied to delivered bytes, including the historical incident."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from skiller.release_attestation import check_transition, tree_digest


class ReleaseAttestationTests(unittest.TestCase):
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
