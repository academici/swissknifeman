"""Tests orchestrate — delegation of commands to neighboring packages (whitelist, argv, rc)."""
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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


_PARTNER_VARS = ("SKM_SKILLER_BIN", "SKM_SKILLER_ROOT", "SKM_HARNESS_BIN", "SKM_HARNESS_ROOT",
                 "MAIND_SKM_BIN", "MAIND_HARNESS_BIN", "MAIND_BRAIN_BIN")


class TestPartnerLookup(unittest.TestCase):
    """Neighbors are found through aicore.util.partners; a missing one exits with PARTNER_UNAVAILABLE."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        _, self.env = make_repo(self.tmp)
        self.cfg = merge_defaults({"projects": [{"id": "f", "name": "F", "local_path": "/x"}]})
        patcher = mock.patch.dict(os.environ, {"PATH": str(self.tmp / "empty")})
        patcher.start()
        self.addCleanup(patcher.stop)
        for var in _PARTNER_VARS:
            os.environ.pop(var, None)
        orch._warned.clear()

    def run_cap(self, cap):
        calls = {}
        with mock.patch.object(orch.subprocess, "run", _fake_run(calls)):
            orch.run_capability(self.env, self.cfg, "f", cap)
        return calls["argv"]

    def test_skiller_found_by_new_variable(self):
        os.environ["SKM_SKILLER_BIN"] = str(_fake_bin(self.tmp, "skiller"))
        self.assertTrue(self.run_cap("skm:lock")[0].endswith("/skiller"))

    def test_legacy_variable_first_with_one_warning(self):
        os.environ["SKM_SKILLER_BIN"] = str(_fake_bin(self.tmp, "new"))
        os.environ["MAIND_SKM_BIN"] = str(_fake_bin(self.tmp, "old"))
        self.assertTrue(self.run_cap("skm:lock")[0].endswith("/old"))

    def test_harness_found_by_root(self):
        root = self.tmp / "h"
        (root / "bin").mkdir(parents=True)
        _fake_bin(root / "bin", "harness")
        os.environ["SKM_HARNESS_ROOT"] = str(root)
        self.assertEqual(self.run_cap("env:hooks")[0], str(root / "bin" / "harness"))

    def test_missing_partner_exits_with_code(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            orch.run_capability(self.env, self.cfg, "f", "env:apply")
        self.assertIn("PARTNER_UNAVAILABLE: harness not found", err.getvalue())

    def test_brain_cli_lives_in_the_vault(self):
        vault = self.tmp / "vault"
        (vault / "bin").mkdir(parents=True)
        _fake_bin(vault / "bin", "brain")
        with mock.patch("maind.provision.orchestrate.brain_path", return_value=str(vault)):
            self.assertEqual(self.run_cap("brain:list")[0], str(vault / "bin" / "brain"))

    def test_brain_without_vault_is_unavailable(self):
        err = io.StringIO()
        with mock.patch("maind.provision.orchestrate.brain_path", return_value=None), \
                contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            orch.run_capability(self.env, self.cfg, "f", "brain:list")
        self.assertIn("PARTNER_UNAVAILABLE: brain", err.getvalue())

    def test_legacy_brain_bin_warns_once(self):
        os.environ["MAIND_BRAIN_BIN"] = str(_fake_bin(self.tmp, "brain"))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.run_cap("brain:list")
            self.run_cap("brain:list")
        self.assertEqual(err.getvalue().count("MAIND_BRAIN_BIN_DEPRECATED"), 1)


if __name__ == "__main__":
    unittest.main()
