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


def _budgets(**overrides):
    value = {"cost_limit_microunits": 5000000, "max_envelope_bytes": 65536, "max_event_count": 64,
             "max_output_bytes": 16384, "max_slices": 1, "max_turns": 8, "timeout_ms": 180000,
             "token_limit": 8000}
    value.update(overrides)
    return value


def _row(**overrides):
    value = {"trial_id": "t1", "scenario": "reconstruct bounded subset", "kind": "repository-slice",
             "files": ["a.py", "b.py"], "base_commit": "0" * 40, "provider": "codex",
             "route": {"model_class": "implementation", "effort": "high"},
             "capabilities": ["structured_output"], "acceptance_refs": ["REL-ACCEPTED-SCOPE"],
             "validation": ["scoped-git-diff"], "budgets": _budgets()}
    value.update(overrides)
    return value


def _catalog(rows):
    body = {"trials": rows}
    body["catalog_hash"] = business_dispatch._hash(body, "catalog_hash")
    return body


def _task_from_row(row, **overrides):
    value = {"task_id": row["trial_id"], "catalog_hash": None, "files": row["files"],
             "base_commit": row["base_commit"], "provider": row["provider"], "route": row["route"],
             "capabilities": row["capabilities"], "acceptance_refs": row["acceptance_refs"],
             "validation": row["validation"], "budgets": row["budgets"]}
    value.update(overrides)
    return value


def _write_catalog(directory, catalog):
    path = Path(directory) / "catalog.json"
    path.write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
    return path


class CatalogResolutionTests(unittest.TestCase):
    """D121 — hash-verified catalog resolution: the catalog is a second source, never authority."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.row = _row()
        self.catalog = _catalog([self.row])
        self.catalog_path = _write_catalog(self.tmp.name, self.catalog)
        self.task = _task_from_row(self.row, catalog_hash=self.catalog["catalog_hash"])

    def test_matching_row_resolves(self):
        row = business_dispatch.resolve_task_description(self.catalog_path, {"task": self.task})
        self.assertEqual(("reconstruct bounded subset", "repository-slice"), (row["scenario"], row["kind"]))

    def test_absent_catalog_file_refuses(self):
        missing = Path(self.tmp.name) / "does-not-exist.json"
        with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "CATALOG_UNAVAILABLE"):
            business_dispatch.resolve_task_description(missing, {"task": self.task})

    def test_malformed_catalog_refuses(self):
        bad = Path(self.tmp.name) / "bad.json"
        bad.write_text("not json", encoding="utf-8")
        with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "CATALOG_UNAVAILABLE"):
            business_dispatch.resolve_task_description(bad, {"task": self.task})

    def test_tampered_catalog_content_refuses_on_hash_mismatch(self):
        tampered = _catalog([dict(self.row, scenario="a different scenario entirely")])
        path = _write_catalog(self.tmp.name, tampered)
        with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "CATALOG_HASH_MISMATCH"):
            business_dispatch.resolve_task_description(path, {"task": self.task})

    def test_missing_row_refuses(self):
        task = dict(self.task, task_id="no-such-trial")
        with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "CATALOG_ROW_MISSING"):
            business_dispatch.resolve_task_description(self.catalog_path, {"task": task})

    def test_duplicate_row_refuses(self):
        catalog = _catalog([self.row, dict(self.row)])
        path = _write_catalog(self.tmp.name, catalog)
        task = _task_from_row(self.row, catalog_hash=catalog["catalog_hash"])
        with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "CATALOG_ROW_MISSING"):
            business_dispatch.resolve_task_description(path, {"task": task})

    def test_cross_check_field_divergence_refuses(self):
        divergent_values = {
            "files": ["c.py"], "base_commit": "1" * 40, "provider": "claude-code",
            "route": {"model_class": "frontier", "effort": "high"}, "capabilities": ["machine_events"],
            "acceptance_refs": ["SEC-AUTHORITY"], "validation": ["rollback-to-exact-base"],
        }
        for field, value in divergent_values.items():
            with self.subTest(field=field):
                task = _task_from_row(self.row, catalog_hash=self.catalog["catalog_hash"])
                task[field] = value
                with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "CATALOG_ROW_DIVERGENT"):
                    business_dispatch.resolve_task_description(self.catalog_path, {"task": task})

    def test_budget_key_divergence_refuses(self):
        for key in self.row["budgets"]:
            with self.subTest(key=key):
                task = _task_from_row(self.row, catalog_hash=self.catalog["catalog_hash"])
                task["budgets"] = dict(task["budgets"], **{key: task["budgets"][key] + 1})
                with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "CATALOG_ROW_DIVERGENT"):
                    business_dispatch.resolve_task_description(self.catalog_path, {"task": task})

    def test_absent_scenario_or_kind_on_row_refuses(self):
        for field in ("scenario", "kind"):
            with self.subTest(field=field):
                row = dict(self.row); row[field] = ""
                catalog = _catalog([row])
                path = _write_catalog(self.tmp.name, catalog)
                task = _task_from_row(row, catalog_hash=catalog["catalog_hash"])
                with self.assertRaisesRegex(business_dispatch.BusinessRefusal, "CATALOG_ROW_DIVERGENT"):
                    business_dispatch.resolve_task_description(path, {"task": task})


class _FakeCodex:
    BUSINESS_VERSION = "fake-codex-version"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def resolve_binary(self) -> str:
        return "fake-codex"

    def build_business_argv(self, request, *, schema_path, cwd, binary):
        self.calls.append("build")
        return ["fake-codex", "exec"]

    def fold_records(self, rows, request, *, exit_code, include_economy=False, wall_duration_ms=None):
        self.calls.append("fold")
        result = {"worker_succeeded": True, "acceptance_state": "not_evaluated", "exit_class": "success",
                  "reason_code": "OK", "event_count": 1}
        if include_economy:
            result["economy"] = {"worker": {"input_tokens": 1, "cached_input_tokens": 0, "output_tokens": 2,
                                            "reasoning_tokens": 3, "cost_microunits": None, "duration_ms": None,
                                            "turns": 1},
                                 "coordinator": {field: 0 for field in ("input_tokens", "cached_input_tokens",
                                                                        "output_tokens", "reasoning_tokens",
                                                                        "cost_microunits", "duration_ms", "turns")},
                                 "unknown_reasons": {"worker/cost_microunits": "fake: no cost",
                                                     "worker/duration_ms": "fake: no duration"},
                                 "inclusion_bases": {}, "zero_bases": {}}
        return result


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
        result = {"kind": "success" if normalized.get("worker_succeeded") else "provider_unavailable",
                 "reason_code": normalized.get("reason_code", "PROVIDER_PROTOCOL_UNKNOWN"),
                 "process_count": 1, "duration_ms": 1, "event_count": normalized.get("event_count", 0)}
        if "economy" in normalized:
            result["economy"] = normalized["economy"]
        return result
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

    def test_codex_seam_fills_wrapper_measured_duration_into_the_economy_envelope(self):
        """D123/D127 — codex reports no per-turn duration; the seam fills it from the
        wrapper's own measured wall-clock ``duration_ms`` and clears the placeholder reason."""
        fake_codex = _FakeCodex()
        port = activity.BusinessProviderActivityPort(
            PLAN, self.codex_admission, g2_digest=G2, g2b_digest=G2B,
            modules={"codex": fake_codex, "claude-code": _FakeClaude()},
            runner=_fake_runner(fake_codex.calls), version_probe=lambda binary, provider: fake_codex.BUSINESS_VERSION)
        with tempfile.TemporaryDirectory() as cwd:
            result = port.run(cwd=Path(cwd), binary="fake-codex")
        self.assertEqual(result["duration_ms"], result["economy"]["worker"]["duration_ms"])
        self.assertNotIn("worker/duration_ms", result["economy"]["unknown_reasons"])
        self.assertIn("worker/cost_microunits", result["economy"]["unknown_reasons"])

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

    def test_business_prompt_states_scenario_and_names_exact_files_only(self):
        """D121 — the seam's prompt is a measurable variable, not a silent gap."""
        catalog_path = PLAN / "artifacts/P5/trial-catalog-v1.json"
        row = business_dispatch.resolve_task_description(catalog_path, self.codex_admission)
        port = activity.BusinessProviderActivityPort(PLAN, self.codex_admission, g2_digest=G2, g2b_digest=G2B)
        prompt = port._prompt(row)
        self.assertIn(row["scenario"], prompt)
        self.assertIn(row["kind"], prompt)
        for file in self.codex_admission["task"]["files"]:
            self.assertIn(file, prompt)
        self.assertNotIn(row["historical_patch_sha256"], prompt)
        self.assertNotIn("historical_patch_sha256", prompt)

    def test_missing_catalog_refuses_before_any_provider_call(self):
        with tempfile.TemporaryDirectory() as plan_dir:
            (Path(plan_dir) / "artifacts/P5").mkdir(parents=True)
            fake_codex = _FakeCodex()
            port = activity.BusinessProviderActivityPort(
                Path(plan_dir), self.codex_admission, g2_digest=G2, g2b_digest=G2B,
                modules={"codex": fake_codex, "claude-code": _FakeClaude()},
                runner=_fake_runner(fake_codex.calls),
                version_probe=lambda binary, provider: fake_codex.BUSINESS_VERSION)
            with tempfile.TemporaryDirectory() as cwd:
                result = port.run(cwd=Path(cwd), binary="fake-codex")
        self.assertEqual([], fake_codex.calls)
        self.assertEqual(("provider_unavailable", "CATALOG_UNAVAILABLE", 0),
                         (result["kind"], result["reason_code"], result["process_count"]))


if __name__ == "__main__":
    unittest.main()
