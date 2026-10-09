"""Shared helpers of the extension tests: temporary HOME-free locations and fixture paths."""
import io
import os
import tempfile
import unittest
from pathlib import Path

from aicore.ext import errors

FIXTURES = Path(__file__).resolve().parent / "fixtures"
UNITS = FIXTURES / "units"


class TempCase(unittest.TestCase):
    """A temporary project root and machine home; the process environment is never read."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.project = self.tmp / "project"
        (self.project / ".swissknifeman").mkdir(parents=True)
        self.env = {"HOME": str(self.home), "SKM_HOME": str(self.tmp / "skm"), "SKM_UNITS_PATH": str(UNITS)}
        errors.reset_warnings()
        self.addCleanup(errors.reset_warnings)

    @property
    def journal(self) -> Path:
        return self.project / ".swissknifeman" / "state"


def run_cli(*argv, env=None, cwd=None):
    from aicore import cli
    out, err = io.StringIO(), io.StringIO()
    code = cli.main(list(argv), env=env, cwd=cwd, out=out, err=err)
    return code, out.getvalue(), err.getvalue()
