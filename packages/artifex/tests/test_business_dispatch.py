from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from artifex import activity, business_dispatch


PLAN = Path(__file__).resolve().parents[3] / "plans" / "2026.08.03-ARTIFEX-SUPERVISOR"
G2 = "ef08406d7ca630d46e9e9e8bca0d10ea73b141d984615bded75f19d7eea13f09"
G2B = "1" * 64


class BusinessDispatchTests(unittest.TestCase):
    def test_indexed_d105_is_read_only_and_g2_linked(self):
        path = PLAN / "artifacts/P5/trial-admissions/p5.2-slice-01-worktree-core.json"
        value = business_dispatch.load_indexed(PLAN, path, g2_digest=G2, g2b_digest="1" * 64)
        self.assertEqual(("business-trial", 0), (value["purpose"], value["usage"]["used_slices"]))

    def test_g2_substitution_or_unindexed_file_refuses(self):
        path = PLAN / "artifacts/P5/trial-admissions/p5.2-slice-01-worktree-core.json"
        with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "G2_PREDECESSOR_MISMATCH"):
            business_dispatch.load_indexed(PLAN, path, g2_digest="0" * 64, g2b_digest="1" * 64)
        with tempfile.TemporaryDirectory() as directory:
            foreign = Path(directory) / "admission.json"; foreign.write_text(json.dumps({}), encoding="utf-8")
            with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "ADMISSION_PATH_EXTERNAL"):
                business_dispatch.load_indexed(PLAN, foreign, g2_digest=G2, g2b_digest="1" * 64)


class _FakeCodex:
    BUSINESS_VERSION = "fake-codex-version"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def resolve_binary(self) -> str:
        return "fake-codex"

    def build_business_argv(self, request, *, schema_path, cwd, binary):
        self.calls.append("build")
        return ["fake-codex", "exec"]

    def fold_records(self, rows, request, *, exit_code):
        self.calls.append("fold")
        return {"worker_succeeded": True, "acceptance_state": "not_evaluated", "exit_class": "success",
                "reason_code": "OK", "event_count": 1}


class _FakeClaude:
    BUSINESS_VERSION = "fake-claude-version"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def resolve_binary(self) -> str:
        return "fake-claude"

    def build_business_argv(self, request, *, schema_path, cwd, mcp_config_path, binary):
        self.calls.append("build")
        return ["fake-claude", "-p", "prompt-placeholder"]

    def fold_business_records(self, rows, request, *, exit_code):
        self.calls.append("fold")
        return {"worker_succeeded": True, "acceptance_state": "not_evaluated", "exit_class": "success",
                "reason_code": "OK", "event_count": 1}


def _fake_runner(calls):
    def runner(argv, *, cwd, env, stdin, timeout_ms, max_output_bytes, max_event_count, normalizer):
        calls.append("run")
        normalized = normalizer([], 0)
        return {"kind": "success" if normalized.get("worker_succeeded") else "provider_unavailable",
                "reason_code": normalized.get("reason_code", "PROVIDER_PROTOCOL_UNKNOWN"),
                "process_count": 1, "duration_ms": 1, "event_count": normalized.get("event_count", 0)}
    return runner


class BusinessActivityRunTests(unittest.TestCase):
    """D118 package-owned seam: composes build_business_argv/fold/worker.run once each."""

    def setUp(self):
        self.codex_admission = json.loads(
            (PLAN / "artifacts/P5/trial-admissions/p5.2-slice-01-worktree-core.json").read_text(encoding="utf-8"))
        self.claude_admission = json.loads(
            (PLAN / "artifacts/P5/trial-admissions/p5.2-slice-02-worktree-binding.json").read_text(encoding="utf-8"))

    def test_codex_seam_calls_build_argv_run_and_fold_exactly_once(self):
        fake_codex = _FakeCodex()
        port = activity.BusinessProviderActivityPort(
            PLAN, self.codex_admission, g2_digest=G2, g2b_digest=G2B,
            modules={"codex": fake_codex, "claude-code": _FakeClaude()},
            runner=_fake_runner(fake_codex.calls), version_probe=lambda binary, provider: fake_codex.BUSINESS_VERSION)
        with tempfile.TemporaryDirectory() as cwd:
            result = port.run(cwd=Path(cwd), binary="fake-codex")
        self.assertEqual(["build", "run", "fold"], fake_codex.calls)
        self.assertEqual(("success", "OK"), (result["kind"], result["reason_code"]))

    def test_claude_seam_calls_build_argv_run_and_business_fold_exactly_once(self):
        fake_claude = _FakeClaude()
        port = activity.BusinessProviderActivityPort(
            PLAN, self.claude_admission, g2_digest=G2, g2b_digest=G2B,
            modules={"codex": _FakeCodex(), "claude-code": fake_claude},
            runner=_fake_runner(fake_claude.calls), version_probe=lambda binary, provider: fake_claude.BUSINESS_VERSION)
        with tempfile.TemporaryDirectory() as cwd:
            result = port.run(cwd=Path(cwd), binary="fake-claude")
        self.assertEqual(["build", "run", "fold"], fake_claude.calls)
        self.assertEqual(("success", "OK"), (result["kind"], result["reason_code"]))

    def test_provider_version_drift_refuses_before_any_seam_call(self):
        fake_codex = _FakeCodex()
        port = activity.BusinessProviderActivityPort(
            PLAN, self.codex_admission, g2_digest=G2, g2b_digest=G2B,
            modules={"codex": fake_codex, "claude-code": _FakeClaude()},
            runner=_fake_runner(fake_codex.calls), version_probe=lambda binary, provider: "installed-drifted-version")
        with tempfile.TemporaryDirectory() as cwd:
            result = port.run(cwd=Path(cwd), binary="fake-codex")
        self.assertEqual([], fake_codex.calls)
        self.assertEqual(("provider_unavailable", "MAPPING_UNKNOWN", 0),
                         (result["kind"], result["reason_code"], result["process_count"]))


if __name__ == "__main__":
    unittest.main()
