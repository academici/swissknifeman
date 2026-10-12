"""`skiller topology` is an alias of `maind topology`; integrate reads the map through maind."""
import contextlib
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tests.fixtures as fx
from skiller.integrate import _block_prereqs
from skiller.topology_alias import cmd_topology

FAKE = """#!/bin/sh
echo "$@" > "$FAKE_LOG"
if [ "$1 $2 $3" = "topology show --json" ]; then echo "$FAKE_SHOW"; fi
exit ${FAKE_EXIT:-0}
"""


class TopologyAliasCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        _, self.env = fx.make_registry(self.tmp)
        self.fake = self.tmp / "maind"
        self.fake.write_text(FAKE)
        self.fake.chmod(self.fake.stat().st_mode | stat.S_IXUSR)
        self.log = self.tmp / "log"

    def tearDown(self):
        self._tmp.cleanup()

    def _env(self, **extra):
        base = {"SKM_MAIND_BIN": str(self.fake), "FAKE_LOG": str(self.log),
                "FAKE_SHOW": '{"version": 1, "nodes": {"brain": {"path": "/b"}}}'}
        base.update(extra)
        return mock.patch.dict(os.environ, base)

    def _no_maind(self):
        return mock.patch.dict(os.environ, {"SKM_MAIND_BIN": "", "SKM_MAIND_ROOT": "",
                                            "PATH": str(self.tmp / "empty")})

    def test_forwards_to_maind_with_one_warning(self):
        err = io.StringIO()
        with self._env(), contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as ctx:
            cmd_topology(self.env, ["show", "--json"])
        self.assertEqual(ctx.exception.code, 0)
        self.assertEqual(self.log.read_text().strip(), "topology show --json")
        self.assertEqual(err.getvalue().count("SKILLER_TOPOLOGY_MOVED"), 1)

    def test_passes_the_exit_code(self):
        with self._env(FAKE_EXIT="4"), contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit) as ctx:
            cmd_topology(self.env, ["init"])
        self.assertEqual(ctx.exception.code, 4)

    def test_without_maind_exits_3_with_partner_unavailable(self):
        err = io.StringIO()
        with self._no_maind(), contextlib.redirect_stderr(err), \
                self.assertRaises(SystemExit) as ctx:
            cmd_topology(self.env, ["show"])
        self.assertEqual(ctx.exception.code, 3)
        self.assertIn("PARTNER_UNAVAILABLE: maind not found", err.getvalue())

    def _prereqs(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            _block_prereqs(self.env, True, False)
        return out.getvalue()

    def test_integrate_reports_a_configured_map(self):
        with self._env():
            self.assertIn("✓ topology configured", self._prereqs())

    def test_integrate_reports_an_empty_map(self):
        with self._env(FAKE_SHOW='{"version": 1, "nodes": {}}'):
            self.assertIn("✗ no topology", self._prereqs())

    def test_integrate_without_maind_names_the_gap(self):
        with self._no_maind():
            self.assertIn("no topology (maind not found)", self._prereqs())


if __name__ == "__main__":
    unittest.main()
