"""The sandbox probe: it reads the PATH and runs ``bwrap … true``; nothing real is needed (PATH and run are replaced)."""
from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))

from orch import sandbox  # noqa: E402


def done(code: int, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], code, "", stderr)


def which(found: dict):
    return lambda name: found.get(name)


@mock.patch.object(sandbox.sys, "platform", "linux")
class ProbeTests(unittest.TestCase):
    def probe(self, found, run):
        with mock.patch.object(sandbox.shutil, "which", which(found)), mock.patch.object(sandbox.subprocess, "run", run):
            return sandbox._probe()

    def test_available_when_the_namespaces_start(self):
        run = mock.Mock(return_value=done(0))
        result = self.probe({"bwrap": "/usr/bin/bwrap", "socat": "/usr/bin/socat"}, run)
        self.assertEqual((result["available"], result["reason"]), (True, None))
        self.assertEqual([row["name"] for row in result["checked"]], ["bwrap", "socat", "bwrap-user-net-namespaces"])
        argv = run.call_args[0][0]
        self.assertEqual(argv[0], "/usr/bin/bwrap")
        self.assertIn("--unshare-net", argv)
        self.assertEqual(argv[-1], "true")

    def test_a_refused_namespace_gives_the_first_line_of_bwrap(self):
        error = "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted\nmore"
        result = self.probe({"bwrap": "/b", "socat": "/s"}, mock.Mock(return_value=done(1, error)))
        self.assertEqual((result["available"], result["reason"]),
                         (False, "bwrap: loopback: Failed RTM_NEWADDR: Operation not permitted"))

    def test_a_missing_helper_is_named_and_bwrap_is_not_run(self):
        run = mock.Mock()
        result = self.probe({"socat": "/s"}, run)
        self.assertEqual((result["available"], result["reason"]), (False, "bwrap not found on PATH"))
        run.assert_not_called()
        result = self.probe({"bwrap": "/b"}, mock.Mock(return_value=done(0)))
        self.assertEqual(result["reason"], "socat not found on PATH")

    def test_a_timeout_is_a_failure(self):
        run = mock.Mock(side_effect=subprocess.TimeoutExpired("bwrap", 10))
        result = self.probe({"bwrap": "/b", "socat": "/s"}, run)
        self.assertFalse(result["available"])
        self.assertIn("did not finish", result["reason"])

    def test_the_result_is_cached_for_the_process(self):
        with mock.patch.object(sandbox, "_probe", return_value={"available": True}) as probe, \
                mock.patch.object(sandbox, "_cached", None):
            sandbox.probe()
            sandbox.probe()
            self.assertEqual(probe.call_count, 1)
            sandbox.probe(refresh=True)
            self.assertEqual(probe.call_count, 2)


class OtherPlatformTests(unittest.TestCase):
    def test_macos_needs_no_bubblewrap(self):
        with mock.patch.object(sandbox.sys, "platform", "darwin"):
            self.assertTrue(sandbox._probe()["available"])


if __name__ == "__main__":
    unittest.main()
