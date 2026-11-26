"""Antigravity native hooks participate in the managed artifact transaction."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from aicore.provider.values import ProviderId
from harness.hooks import block_codex_lifecycle


PACKAGE = Path(__file__).resolve().parents[1]


class AntigravityHooksTests(unittest.TestCase):
    def deploy(self, root, *, dry=False, repair=False):
        with contextlib.redirect_stdout(io.StringIO()):
            block_codex_lifecycle(
                SimpleNamespace(root=PACKAGE), root,
                surfaces=("context.observer", "lifecycle.command-log"),
                trusted=True, repair=repair, dry=dry,
                provider_id=ProviderId.ANTIGRAVITY)

    def test_native_registration_is_locked_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.deploy(root, dry=True)
            self.assertEqual(list(root.iterdir()), [])
            self.deploy(root)
            target = root / ".agents/hooks.json"
            native = json.loads(target.read_text())
            self.assertIn("SessionStart", native["swissknifeman"])
            self.assertIn("run_command", native["swissknifeman"]["PreToolUse"][0]["matcher"])
            lock = json.loads((root / ".swissknifeman/provider-artifacts.lock.json").read_text())
            self.assertIn(".agents/hooks.json", json.dumps(lock))
            before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
            self.deploy(root)
            self.assertEqual(before, {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()})
            native["other-owner"] = {"SessionStart": []}
            target.write_text(json.dumps(native))
            with self.assertRaises(SystemExit):
                self.deploy(root)
            self.deploy(root, repair=True)
            self.assertEqual(json.loads(target.read_text())["other-owner"], native["other-owner"])

    def test_invalid_or_symlink_hooks_refuse_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".agents").mkdir()
            target = root / ".agents/hooks.json"
            for invalid in ("{", "[]"):
                target.write_text(invalid)
                with self.assertRaises(SystemExit):
                    self.deploy(root)
                self.assertEqual(target.read_text(), invalid)
                self.assertFalse((root / ".antigravity").exists())
            target.unlink()
            outside = root / "outside.json"
            outside.write_text("{}")
            target.symlink_to(outside)
            with self.assertRaises(SystemExit):
                self.deploy(root)
            self.assertEqual(outside.read_text(), "{}")
