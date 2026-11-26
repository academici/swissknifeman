"""Facade `skiller doctor --settings` (P1.4): delegation to the host `settings_doctor`
command via subprocess, returning the return code, graceful skip when the command is
not configured or not installed. Check logic in skiller NO (D10) — testing only
facade behavior, not taxonomy (its tests live with the host tool).

Plus P4.2 `skiller doctor --effective-source`: composed read-only doctor —
here (Files item'and names exactly this test file), testing the facade as well
(`--settings`), and composed-diagnostics record-shape/fixtures separately."""
import contextlib
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from unittest import mock

from skiller.common import Env
from skiller.host import clear_host_cache
from skiller.doctor import (
    EffectiveSourceDoctorError,
    build_effective_source_report,
    cmd_doctor,
    gather_effective_source_diagnostics,
)

FIXTURES_DATA = Path(__file__).resolve().parent / "fixtures_data"


def _run(fn, *a):
    buf = io.StringIO()
    exc = None
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            fn(*a)
        except SystemExit as e:
            exc = e
    return exc, buf.getvalue()


class DoctorSettingsFacadeCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        # root — tmpdir outside any host: the command comes only from the synthetic
        # host config below, its binary only from the env override.
        self.env = Env(self.tmp / "registry", home=self.home)
        (self.tmp / "registry").mkdir()
        self.host = self.tmp / "host.json"
        self.write_host({"commands": {"settings_doctor": {
            "argv": ["bin/env-tool", "doctor", "--settings"], "env_override": "SKM_ENV_TOOL_BIN",
            "install_hint": "env-tool/install.sh"}}})
        clear_host_cache()
        patcher = mock.patch.dict(os.environ, {"SKILLER_HOST_CONFIG": str(self.host)})
        patcher.start()
        os.environ.pop("SKM_ENV_TOOL_BIN", None)
        self.addCleanup(patcher.stop)
        self.addCleanup(clear_host_cache)

    def tearDown(self):
        self._tmp.cleanup()

    def write_host(self, config):
        self.host.write_text(json.dumps({"schema_version": 1, **config}), encoding="utf-8")
        clear_host_cache()

    # command not installed → warn with the host install hint and graceful skip (rc 0)
    def test_missing_command_warns_and_skips(self):
        exc, out = _run(cmd_doctor, self.env, ["--settings", "--target", str(self.tmp)])
        self.assertIsNone(exc)  # not sys.exit — facade missed softly
        self.assertIn("settings doctor command not configured or not installed", out)
        self.assertIn("(install: env-tool/install.sh)", out)

    def test_empty_host_skips_without_hint(self):
        self.write_host({})
        exc, out = _run(cmd_doctor, self.env, ["--settings", "--target", str(self.tmp)])
        self.assertIsNone(exc)
        self.assertIn("settings-doctor not available", out)
        self.assertNotIn("install:", out)

    # command present → return code is thrown (2 → sys.exit(2)), argv from the host.
    # The stub does not write to stdout: subprocess inherits real fd (redirect_stdout
    # only catches python-level sys.stdout) — checking the return code contract.
    def test_proxies_command_exit_code_and_argv(self):
        log = self.tmp / "argv.log"
        stub = self.tmp / "env-tool-stub"
        stub.write_text(f"#!/usr/bin/env bash\nprintf '%s\\n' \"$*\" > {log}\nexit 2\n",
                        encoding="utf-8")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        os.environ["SKM_ENV_TOOL_BIN"] = str(stub)
        exc, _out = _run(cmd_doctor, self.env, ["--settings", "--target", str(self.tmp)])
        self.assertIsInstance(exc, SystemExit)
        self.assertEqual(exc.code, 2)
        self.assertEqual(log.read_text(encoding="utf-8").strip(),
                         f"doctor --settings --target {self.tmp}")


class EffectiveSourceDoctorFixtureCase(unittest.TestCase):
    """P4.2: `build_effective_source_report` against the committed healthy/degraded
    fixtures — pure composition, no filesystem/subprocess involved (the gathering
    functions that DO touch the filesystem are exercised by `EffectiveSourceDoctorLiveCase`
    below against the real repo, read-only)."""

    def setUp(self):
        self.cases = json.loads(
            (FIXTURES_DATA / "effective-source-doctor-cases.json").read_text(encoding="utf-8"))["cases"]

    def test_healthy_case_folds_to_ok(self):
        case = self.cases["healthy"]
        report = build_effective_source_report(case["diagnostics"])
        self.assertEqual(report["overall"], case["expected_overall"])
        self.assertEqual(report["schema_version"], "effective-source-doctor/v1")

    def test_degraded_case_folds_to_degraded(self):
        case = self.cases["degraded"]
        report = build_effective_source_report(case["diagnostics"])
        self.assertEqual(report["overall"], case["expected_overall"])

    def test_missing_required_key_raises(self):
        broken = [{"id": "x", "owner": "o", "source": "s", "status": "ok", "evidence": {}}]  # no quality/next_command
        with self.assertRaises(EffectiveSourceDoctorError):
            build_effective_source_report(broken)

    def test_out_of_vocabulary_status_raises(self):
        broken = [{"id": "x", "owner": "o", "source": "s", "status": "green",
                  "evidence": {}, "quality": {}, "next_command": "c"}]
        with self.assertRaises(EffectiveSourceDoctorError):
            build_effective_source_report(broken)


class EffectiveSourceDoctorLiveCase(unittest.TestCase):
    """`--effective-source` against the real registry (read-only, this repo's own
    checked-out tree) — proves the CLI wiring and the record shape hold on live data,
    not just the fixture. No write is asserted at the Validation shell-command layer
    (git status before/after); here we only assert shape/no-crash."""

    def test_gather_and_build_round_trip(self):
        from skiller.common import Env as RealEnv
        root = Path(__file__).resolve().parents[1]
        env = RealEnv(root)
        diagnostics = gather_effective_source_diagnostics(env, repo_root=root.parents[1])
        report = build_effective_source_report(diagnostics)
        self.assertEqual(report["schema_version"], "effective-source-doctor/v1")
        self.assertEqual({d["id"] for d in report["diagnostics"]},
                          {"identity-ownership", "cache", "capability-reference-coverage",
                           "hook-ownership", "trace-quality"})
        for d in report["diagnostics"]:
            self.assertIn(d["status"], ("ok", "degraded", "unknown", "n/a"))
        self.assertIn(report["overall"], ("ok", "degraded"))

    def test_cli_effective_source_json_prints_one_document(self):
        from skiller.common import Env as RealEnv
        root = Path(__file__).resolve().parents[1]
        env = RealEnv(root)
        exc, out = _run(cmd_doctor, env, ["--effective-source", "--json"])
        self.assertIsNone(exc)
        doc = json.loads(out)
        self.assertEqual(doc["schema_version"], "effective-source-doctor/v1")


if __name__ == "__main__":
    unittest.main()
