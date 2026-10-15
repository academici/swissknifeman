"""One public CLI: the conductor is the ``conduct`` group of ``orch.py`` (``swissknifeman orch conduct ...``)."""
from __future__ import annotations

import json
from pathlib import Path
import unittest
from unittest.mock import patch

from orch import cli

ROOT = Path(__file__).resolve().parents[1]


class ConductGroupTests(unittest.TestCase):
    def test_conduct_arguments(self):
        self.assertEqual(cli._conduct_args(["conduct", "status", "--json"]), ["status", "--json"])
        self.assertEqual(cli._conduct_args(["--config", "c.toml", "--project", "/p", "conduct", "run"]),
                         ["--config", "c.toml", "--project", "/p", "run"])
        self.assertEqual(cli._conduct_args(["--config=c.toml", "conduct"]), ["--config=c.toml"])
        self.assertIsNone(cli._conduct_args(["validate", "exec", "f.json"]))
        self.assertIsNone(cli._conduct_args([]))

    def test_main_hands_the_group_to_the_conductor(self):
        with patch("orch.conductor.cli.main", return_value=7) as conduct:
            self.assertEqual(cli.main(["conduct", "status"]), 7)
        conduct.assert_called_once_with(["status"])

    def test_manifest_declares_one_public_cli(self):
        unit = json.loads((ROOT / "unit.json").read_text(encoding="utf-8"))
        self.assertEqual(unit["provides"]["cli"], ["scripts/orch.py"])


if __name__ == "__main__":
    unittest.main()
