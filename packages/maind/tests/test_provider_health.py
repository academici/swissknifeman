import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from maind.provider_health import (
    EVIDENCE_SET_VERSION,
    evaluate,
    load_evidence_set,
    seal_evidence_set,
)
from tests.fixtures import make_repo


NOW = "2026-08-16T05:00:00Z"
FRESH = "2026-08-17T05:00:00Z"


def _requirement(provider, axis, producer, *, selected=True, required=True):
    return {
        "provider_id": provider, "axis_id": axis, "selected": selected,
        "required": required, "producer": producer,
    }


def _evidence(provider, axis, state="pass", source="owner.status"):
    return {
        "provider_id": provider, "axis_id": axis, "state": state,
        "evidence_id": f"ev:{provider}:{axis}", "source_id": source,
        "observed_at": NOW, "expires_at": FRESH,
    }


def _write_set(root, requirements, evidence=(), project_id="alpha"):
    payload = {
        "schema_version": EVIDENCE_SET_VERSION,
        "contract_version": "1.0.0",
        "evidence_set_id": "set:alpha",
        "projects": [{
            "project_id": project_id,
            "requirements": sorted(requirements,
                                   key=lambda row: (row["provider_id"], row["axis_id"])),
            "evidence": sorted(evidence,
                               key=lambda row: (row["provider_id"], row["axis_id"])),
        }],
    }
    path = root / "health-input.json"
    path.write_text(json.dumps(seal_evidence_set(payload)), encoding="utf-8")
    return load_evidence_set(path)


def _measurement(provider):
    return {
        "provider": provider, "model_family": "unknown", "surface": "listing",
        "value": 42, "unit": "characters", "method": "skiller:list-v1",
        "uncertainty": "estimate", "measurement_class": "estimate",
        "observed_at": NOW, "expires_at": FRESH,
        "source_id": "skiller.budget.listing", "status": "pass", "threshold": 100,
    }


class ProviderHealthTests(unittest.TestCase):
    def _case(self, tmp):
        root, env = make_repo(tmp)
        target = Path(tmp) / "project"
        target.mkdir()
        for package in ("skiller", "harness"):
            binary = root / "packages" / package / "bin" / package
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_text("#!/bin/sh\n", encoding="utf-8")
        project = {"id": "alpha", "local_path": str(target)}
        return root, env, target, project

    def test_public_owner_rows_compose_green_without_raw_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env, target, project = self._case(tmp)
            requirements = [
                _requirement("claude-code", "provider.readback", "sealed"),
                _requirement("codex", "provider.readback", "sealed"),
                _requirement("claude-code", "harness.settings", "harness"),
                _requirement("codex", "harness.settings", "harness"),
                _requirement("claude-code", "skill.measurement.listing", "skiller"),
                _requirement("codex", "skill.measurement.listing", "skiller"),
                _requirement("shared", "skill.dependency", "skiller"),
            ]
            declared = _write_set(root, requirements, [
                _evidence("claude-code", "provider.readback"),
                _evidence("codex", "provider.readback"),
            ])

            def runner(argv, **_kwargs):
                if "skiller" in argv[0]:
                    payload = {
                        "dependency_closure": {"status": "green", "diagnostics": []},
                        "measurements": {"status": "green", "rows": [
                            _measurement("claude-code"), _measurement("codex"),
                        ]},
                    }
                else:
                    provider = argv[argv.index("--provider") + 1]
                    payload = {"provider": provider, "target": str(target), "profile": None,
                               "status": "clean", "counts": {"error": 0, "warn": 0,
                                                                 "info": 0},
                               "findings": [], "exit": 0}
                return subprocess.CompletedProcess(argv, 0, json.dumps(payload), "")

            result = evaluate(env, {"projects": [project]}, [project], declared,
                              evaluated_at=NOW, runner=runner)
            self.assertEqual("green", result["aggregate"])
            self.assertEqual(7, len(result["projects"][0]["rows"]))
            self.assertNotIn(str(target), json.dumps(result))

    def test_timeout_becomes_non_green_rows_not_a_skipped_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env, _target, project = self._case(tmp)
            declared = _write_set(root, [
                _requirement("claude-code", "skill.measurement.listing", "skiller"),
                _requirement("codex", "skill.measurement.listing", "skiller"),
            ])

            def timeout(argv, **_kwargs):
                raise subprocess.TimeoutExpired(argv, 20)

            result = evaluate(env, {"projects": [project]}, [project], declared,
                              evaluated_at=NOW, runner=timeout)
            rows = result["projects"][0]["rows"]
            self.assertEqual("non-green", result["aggregate"])
            self.assertEqual({"unavailable"}, {row["status"] for row in rows})
            self.assertEqual({"claude-code", "codex"},
                             {row["provider_id"] for row in rows})

    def test_malformed_skiller_schema_becomes_error_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env, _target, project = self._case(tmp)
            declared = _write_set(root, [
                _requirement("claude-code", "skill.measurement.listing", "skiller"),
                _requirement("codex", "skill.measurement.listing", "skiller"),
            ])
            runner = lambda argv, **kwargs: subprocess.CompletedProcess(
                argv, 0, '{"measurements": []}', "")
            result = evaluate(env, {"projects": [project]}, [project], declared,
                              evaluated_at=NOW, runner=runner)
            self.assertEqual({"error"},
                             {row["status"] for row in result["projects"][0]["rows"]})

    def test_nonzero_skiller_exit_cannot_be_green_even_with_valid_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env, _target, project = self._case(tmp)
            declared = _write_set(root, [
                _requirement("claude-code", "skill.measurement.listing", "skiller"),
                _requirement("codex", "skill.measurement.listing", "skiller"),
            ])
            payload = {
                "dependency_closure": {"status": "green", "diagnostics": []},
                "measurements": {"status": "green", "rows": [
                    _measurement("claude-code"), _measurement("codex"),
                ]},
            }
            runner = lambda argv, **kwargs: subprocess.CompletedProcess(
                argv, 2, json.dumps(payload), "failed")
            result = evaluate(env, {"projects": [project]}, [project], declared,
                              evaluated_at=NOW, runner=runner)
            self.assertEqual({"error"},
                             {row["status"] for row in result["projects"][0]["rows"]})

    def test_missing_codex_evidence_cannot_be_masked_by_claude(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env, _target, project = self._case(tmp)
            declared = _write_set(root, [
                _requirement("claude-code", "provider.readback", "sealed"),
                _requirement("codex", "provider.readback", "sealed"),
            ], [_evidence("claude-code", "provider.readback")])
            result = evaluate(env, {"projects": [project]}, [project], declared,
                              evaluated_at=NOW)
            self.assertEqual("non-green", result["aggregate"])
            self.assertIn("PH_EVIDENCE_MISSING",
                          {item["code"] for item in result["projects"][0]["diagnostics"]})

    def test_evidence_set_seal_and_project_set_are_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, env, _target, project = self._case(tmp)
            declared = _write_set(root, [
                _requirement("claude-code", "provider.readback", "sealed"),
                _requirement("codex", "provider.readback", "sealed"),
            ])
            with self.assertRaisesRegex(ValueError, "PH_PROJECT_SET_MISMATCH"):
                evaluate(env, {}, [project, {"id": "extra"}], declared, evaluated_at=NOW)
            path = root / "health-input.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["evidence_set_id"] = "set:tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "PH_EVIDENCE_SET_SEAL_INVALID"):
                load_evidence_set(path)

    def test_secret_like_evidence_identity_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, _env = make_repo(tmp)
            with self.assertRaisesRegex(ValueError, "PH_REDACTION_REQUIRED"):
                _write_set(root, [
                    _requirement("claude-code", "provider.readback", "sealed"),
                    _requirement("codex", "provider.readback", "sealed"),
                ], [_evidence("claude-code", "provider.readback",
                              source="secret.token")])


if __name__ == "__main__":
    unittest.main()
