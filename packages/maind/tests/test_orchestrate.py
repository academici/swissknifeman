"""Tests orchestrate — delegation of commands to neighboring packages (whitelist, argv, rc)."""
import os
import tempfile
import unittest
from pathlib import Path

import maind.provision.orchestrate as orch
from maind.config import merge_defaults
from tests.fixtures import make_repo


def _fake_run(store, rc=0):
    def run(argv, **k):
        store["argv"] = list(argv)
        return type("R", (), {"returncode": rc})()
    return run


def _fake_bin(tmp, name="skm"):
    p = Path(tmp) / name
    p.write_text("#!/bin/sh\n", encoding="utf-8")
    p.chmod(0o755)
    return p


class TestOrchestrate(unittest.TestCase):
    def test_run_capability_argv(self):
        calls = {}
        orig = orch.subprocess.run
        orch.subprocess.run = _fake_run(calls)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            os.environ["MAIND_SKM_BIN"] = str(_fake_bin(tmp))
            try:
                cfg = merge_defaults({"projects": [
                    {"id": "flexcrm", "name": "F", "local_path": "/x/flexcrm"}]})
                rc = orch.run_capability(env, cfg, "flexcrm", "skm:lock")
                self.assertEqual(rc, 0)
                argv = calls["argv"]
                self.assertTrue(argv[0].endswith("/skm"))
                self.assertIn("lock", argv)
                self.assertIn("--target", argv)
                self.assertIn("/x/flexcrm", argv)
            finally:
                del os.environ["MAIND_SKM_BIN"]
                orch.subprocess.run = orig

    def test_passthrough_and_rc(self):
        calls = {}
        orig = orch.subprocess.run
        orch.subprocess.run = _fake_run(calls, rc=2)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            os.environ["MAIND_BRAIN_BIN"] = str(_fake_bin(tmp, "brain"))
            try:
                cfg = merge_defaults({"projects": [{"id": "flexcrm", "name": "F",
                                                    "local_path": "/x"}]})
                rc = orch.run_capability(env, cfg, "flexcrm", "brain:sync", ["--dry-run"])
                self.assertEqual(rc, 2)             # rc abandoned
                self.assertIn("--dry-run", calls["argv"])  # passthrough
                self.assertIn("flexcrm", calls["argv"])    # {project}
            finally:
                del os.environ["MAIND_BRAIN_BIN"]
                orch.subprocess.run = orig

    def test_env_capabilities_route_to_harness(self):
        # env:mcp / env:hooks — granular rolling out of the environment through harness
        # (next to env:apply). Checking sibling, subcommand and {path}-substitution.
        for cap, sub in (("env:mcp", "mcp"), ("env:hooks", "hooks"),
                         ("env:apply", "permissions")):
            calls = {}
            orig = orch.subprocess.run
            orch.subprocess.run = _fake_run(calls)
            with tempfile.TemporaryDirectory() as tmp:
                _, env = make_repo(tmp)
                os.environ["MAIND_HARNESS_BIN"] = str(_fake_bin(tmp, "harness"))
                try:
                    cfg = merge_defaults({"projects": [
                        {"id": "flexcrm", "name": "F", "local_path": "/x/flexcrm"}]})
                    rc = orch.run_capability(env, cfg, "flexcrm", cap)
                    self.assertEqual(rc, 0)
                    argv = calls["argv"]
                    self.assertTrue(argv[0].endswith("/harness"), cap)
                    self.assertEqual(argv[1], sub, cap)
                    self.assertIn("--target", argv)
                    self.assertIn("/x/flexcrm", argv)
                finally:
                    del os.environ["MAIND_HARNESS_BIN"]
                    orch.subprocess.run = orig

    def test_unknown_capability_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            with self.assertRaises(SystemExit):
                orch.run_capability(env, merge_defaults({}), "x", "bogus:cap")

    def test_missing_sibling_dies(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            # brain resolves via integrations.brain.path; sent to the catalog
            # without bin/brain → launcher not found → SystemExit. (env-override is missing.)
            cfg = merge_defaults({
                "projects": [{"id": "flexcrm", "name": "F", "local_path": "/x"}],
                "integrations": {"brain": {"path": f"{tmp}/no-brain-vault"}},
            })
            with self.assertRaises(SystemExit):
                orch.run_capability(env, cfg, "flexcrm", "brain:status")

    def test_skm_update_is_dry_capable(self):
        # skm:update — in DRY_CAPABLE: honest --dry-run through skiller (`skiller update`
        # can do its own --dry-run), and not fake print+rc0 — otherwise `maind sync --dry-run` would give
        # false green preview for the new provider skills-catalog (same trap as
        # used to be with agent-pack — see comment DRY_CAPABLE in orchestrate.py).
        calls = {}
        orig = orch.subprocess.run
        orch.subprocess.run = _fake_run(calls)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            os.environ["MAIND_SKM_BIN"] = str(_fake_bin(tmp))
            try:
                cfg = merge_defaults({"projects": [
                    {"id": "flexcrm", "name": "F", "local_path": "/x/flexcrm"}]})
                rc = orch.run_capability(env, cfg, "flexcrm", "skm:update", dry=True)
                self.assertEqual(rc, 0)
                argv = calls["argv"]
                self.assertIn("update", argv)
                self.assertIn("--dry-run", argv)
            finally:
                del os.environ["MAIND_SKM_BIN"]
                orch.subprocess.run = orig

    def test_dry_run_does_not_execute(self):
        called = {"ran": False}
        orig = orch.subprocess.run

        def run(*a, **k):
            called["ran"] = True
            return type("R", (), {"returncode": 0})()
        orch.subprocess.run = run
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            os.environ["MAIND_SKM_BIN"] = str(_fake_bin(tmp))
            try:
                cfg = merge_defaults({"projects": [{"id": "f", "name": "F",
                                                    "local_path": "/x"}]})
                rc = orch.run_capability(env, cfg, "f", "skm:lock", dry=True)
                self.assertEqual(rc, 0)
                self.assertFalse(called["ran"])
            finally:
                del os.environ["MAIND_SKM_BIN"]
                orch.subprocess.run = orig


if __name__ == "__main__":
    unittest.main()
