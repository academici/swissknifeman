"""P10.3 (2026.07.25-ECO-OPT): резолвинг пути AGENT-RELIABILITY-плана в
`skiller.doctor`, устойчивый к архивации. До правки `_capability_gap_diagnostic`/
`_trace_quality_diagnostic`/`_effective_carrier_set_document` жёстко читали
`repo_root / "plans/2026.07.24-AGENT-RELIABILITY/…"` — на дереве, где план лежит
в `plans/archive/…`, диагностика МОЛЧА уходила в `unknown` с неразрешимым
`next_command: cat …`. Красный сценарий здесь — дерево, несущее ТОЛЬКО архивный
путь; починка — `core.resolve_plan_dir` (D95)."""
import tempfile
import unittest
from pathlib import Path

from skiller.doctor import (
    _CAPABILITY_GAP_FINDING_REL,
    _TRACE_QUALITY_FINDING_REL,
    _effective_carrier_set_document,
    _capability_gap_diagnostic,
    _trace_quality_diagnostic,
)


def _write(path, text="content\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CapabilityGapDiagnosticPlanPathCase(unittest.TestCase):
    def test_live_plan_layout_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write(repo_root / "plans/2026.07.24-AGENT-RELIABILITY" / _CAPABILITY_GAP_FINDING_REL)
            diagnostic = _capability_gap_diagnostic(repo_root)
            self.assertEqual(diagnostic["status"], "degraded")
            self.assertEqual(diagnostic["source"],
                             f"plans/2026.07.24-AGENT-RELIABILITY/{_CAPABILITY_GAP_FINDING_REL}")
            self.assertEqual(diagnostic["next_command"], f"cat {diagnostic['source']}")

    def test_archived_plan_layout_resolves(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write(repo_root / "plans/archive/2026.07.24-AGENT-RELIABILITY" / _CAPABILITY_GAP_FINDING_REL)
            diagnostic = _capability_gap_diagnostic(repo_root)
            self.assertEqual(diagnostic["status"], "degraded")
            self.assertEqual(
                diagnostic["source"],
                f"plans/archive/2026.07.24-AGENT-RELIABILITY/{_CAPABILITY_GAP_FINDING_REL}")
            self.assertEqual(diagnostic["next_command"], f"cat {diagnostic['source']}")

    def test_plan_absent_from_both_layouts_degrades_to_unknown_without_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            diagnostic = _capability_gap_diagnostic(repo_root)
            self.assertEqual(diagnostic["status"], "unknown")
            self.assertEqual(
                diagnostic["source"],
                f"plans/2026.07.24-AGENT-RELIABILITY/{_CAPABILITY_GAP_FINDING_REL}")
            self.assertEqual(diagnostic["next_command"], "skiller doctor --provider-distribution")


class TraceQualityDiagnosticPlanPathCase(unittest.TestCase):
    def test_archived_plan_layout_resolves_when_finding_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write(repo_root / "plans/archive/2026.07.24-AGENT-RELIABILITY" / _TRACE_QUALITY_FINDING_REL)
            diagnostic = _trace_quality_diagnostic(repo_root)
            if diagnostic["status"] == "unknown" and "analyst package not importable" in \
                    diagnostic["evidence"].get("gap", ""):
                self.skipTest("analyst не на PYTHONPATH — optional dependency")
            self.assertEqual(diagnostic["status"], "degraded")
            self.assertEqual(
                diagnostic["source"],
                f"plans/archive/2026.07.24-AGENT-RELIABILITY/{_TRACE_QUALITY_FINDING_REL}")
            self.assertEqual(diagnostic["next_command"], f"cat {diagnostic['source']}")


class EffectiveCarrierSetDocumentPlanPathCase(unittest.TestCase):
    def test_fixture_unit_set_literal_resolves_archived_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            _write(repo_root / "plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/P1.4/fixture-unit-set.json",
                  "{}\n")
            gate_result = {"positive_maps": {"codex": {"a": ["root:codex"]}}}
            doc = _effective_carrier_set_document(gate_result, commit_sha="deadbeef",
                                                   repo_root=repo_root)
            self.assertEqual(
                doc["providers"]["codex"]["fixture_unit_set"],
                "plans/archive/2026.07.24-AGENT-RELIABILITY/artifacts/P1.4/fixture-unit-set.json")

    def test_fixture_unit_set_literal_falls_back_when_plan_absent(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            gate_result = {"positive_maps": {"codex": {}}}
            doc = _effective_carrier_set_document(gate_result, commit_sha="deadbeef",
                                                   repo_root=repo_root)
            self.assertEqual(
                doc["providers"]["codex"]["fixture_unit_set"],
                "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P1.4/fixture-unit-set.json")


if __name__ == "__main__":
    unittest.main()
