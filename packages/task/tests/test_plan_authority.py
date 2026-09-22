"""Negative-space and positive tests for the P5 fail-closed authority resolver."""
import copy
import hashlib
import json
import multiprocessing
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

try:
    from . import fixtures  # noqa: F401,E402
except ImportError:  # direct discovery from tests/
    import fixtures  # noqa: F401,E402
from task.plan_authority import (  # noqa: E402
    AuthorityFrameError, CommitmentStore, DurableAuthorityStore, ObservedAction,
    ResponseStore, apply_response,
    auto_answer_clarification, authorize, canonical_action, default_frame_path, evaluate, load_frame,
)


ROOT = Path(__file__).resolve().parents[3]
FRAME_PATH = ROOT / "packages/task/configs/authority-frame.json"


def _frame():
    return load_frame(FRAME_PATH)


def _request(**overrides):
    frame = _frame()
    request = {
        "decision_id": "D-test", "action_version": 1, "kind": "authorization",
        "decision_class": "constructive",
        "subject": {"plan_id": "X", "phase_id": "P5", "item_id": "P5.3"},
        "action": {"affected_surfaces": ["packages/task/lib/task/example.py"],
                   "declared_scope": ["packages/task/lib/task/example.py"],
                   "frozen_contract_change": False, "closed_set_extension": False,
                   "reversible": True, "decision_recorded": True},
        "options": [{"id": "apply", "outcome": "apply", "action_ref": "x", "evidence_refs": []},
                    {"id": "keep", "outcome": "park", "action_ref": "x", "evidence_refs": []}],
        "default_option": None,
        "continuation": {"target": {"plan_id": "X", "item_id": "P5.3", "resume_command": "resume"},
                         "capabilities": {"snapshot_id": "s", "digest": "0" * 64, "available": []}},
        "policy_digest": frame["_policy_digest"],
    }
    request.update(overrides)
    try:
        request["canonical_action"] = canonical_action(request, frame)
        request["action_digest"] = hashlib.sha256(json.dumps(
            request["canonical_action"], ensure_ascii=False, sort_keys=True,
            separators=(",", ":")).encode("utf-8")).hexdigest()
    except Exception:
        request["canonical_action"] = {}
        request["action_digest"] = "0" * 64
    return request


def _observed(request=None, **overrides):
    action = (request or _request())["action"]
    values = {
        "affected_surfaces": tuple(action["affected_surfaces"]),
        "declared_scope": tuple(action["declared_scope"]),
        "frozen_contract_change": action["frozen_contract_change"],
        "closed_set_extension": action["closed_set_extension"],
        "reversible": action["reversible"],
        "decision_recorded": action["decision_recorded"],
        "provenance": "repository-diff:v1", "verified": True,
    }
    values.update(overrides)
    return ObservedAction(**values)


def _consume_response_process(path, request, response, queue):
    result = apply_response(request, response, store=DurableAuthorityStore(path))
    queue.put(result["verdict"] if isinstance(result, dict) else result.reason_code)


class AuthorityEvaluationTests(unittest.TestCase):
    def test_contract_metadata_is_package_owned(self):
        frame = json.loads(FRAME_PATH.read_text(encoding="utf-8"))
        contract = ROOT / frame["contract"]
        self.assertTrue(contract.is_file())
        self.assertNotIn("plans", Path(frame["contract"]).parts)

    def test_default_frame_is_package_relative(self):
        self.assertEqual(default_frame_path(), FRAME_PATH)

    def test_installed_package_resolves_its_bundled_frame_without_monorepo(self):
        package_root = ROOT / "packages/task"
        with tempfile.TemporaryDirectory() as tmp:
            installed_root = Path(tmp) / "plugins/task/0.12.0"
            shutil.copytree(package_root, installed_root)
            environment = os.environ | {"PYTHONPATH": str(installed_root / "lib")}
            environment.pop("TASK_AUTHORITY_FRAME", None)
            result = subprocess.run(
                args=[sys.executable, "-c", (
                    "from task.plan_authority import default_frame_path, load_frame; "
                    "path = default_frame_path(); "
                    "assert path == path.parents[1] / 'configs/authority-frame.json'; "
                    "load_frame(); print(path)"
                )],
                cwd=tmp,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_constructive_is_delegated(self):
        request = _request()
        result = evaluate(request, observed=_observed(request))
        self.assertEqual(result.verdict, "delegated")
        self.assertEqual(result.reason_code, "P5_DECISION_POLICY_APPROVED")

    def test_reserved_class_requires_approval(self):
        self.assertEqual(evaluate(_request(decision_class="scope_change")).verdict,
                         "approval_required")

    def test_unknown_class_is_never_delegated(self):
        result = evaluate(_request(decision_class="__unknown__"))
        self.assertEqual(result.verdict, "denied")

    def test_unknown_kind_is_never_delegated(self):
        self.assertEqual(evaluate(_request(kind="guess")).verdict, "denied")

    def test_raw_clarification_is_never_delegated(self):
        self.assertEqual(evaluate(_request(kind="clarification")).verdict, "approval_required")

    def test_missing_frame_fails_closed_with_clear_error(self):
        with self.assertRaisesRegex(AuthorityFrameError, "authority-frame.*не найден"):
            load_frame("/nonexistent.json")

    def test_invalid_frame_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authority-frame.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaises(AuthorityFrameError):
                load_frame(path)

    def test_stale_policy_digest_is_denied(self):
        self.assertEqual(evaluate(_request(policy_digest="f" * 64)).verdict, "denied")

    def test_any_constructive_predicate_false_requires_approval(self):
        request = _request()
        request["action"]["reversible"] = False
        self.assertEqual(evaluate(request).verdict, "approval_required")

    def test_aggregation_cannot_widen_first_item_scope(self):
        store = CommitmentStore()
        first = _request()
        self.assertEqual(authorize(first, store=store, observed=_observed(first),
                                   mode="diagnostic").verdict, "delegated")
        second = _request(decision_id="D-test-2")
        second["action"]["affected_surfaces"] = ["packages/task/lib/task/other.py"]
        second["action"]["declared_scope"] = ["packages/task/lib/task/other.py"]
        self.assertEqual(authorize(second, store=store, observed=_observed(second),
                                   mode="diagnostic").verdict, "approval_required")

    def test_shadow_never_records_commitment(self):
        store = CommitmentStore()
        request = _request()
        result = authorize(request, store=store, observed=_observed(request), shadow=True)
        self.assertEqual(result["would_verdict"], "delegated")
        self.assertEqual(store.for_request(_request()), [])

    def test_claimed_safe_cannot_override_observed_risky(self):
        request = _request()
        observed = _observed(request, reversible=False)
        self.assertEqual(evaluate(request, observed=observed).verdict, "approval_required")

    def test_missing_observation_never_delegates(self):
        self.assertEqual(evaluate(_request()).verdict, "approval_required")

    def test_enforced_authorize_requires_durable_store(self):
        request = _request()
        result = authorize(request, observed=_observed(request))
        self.assertEqual(result.reason_code, "P5_DECISION_STORE_REQUIRED")

    def test_enforced_commitments_fail_closed_without_trusted_analyzer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authority.json"
            first = _request()
            self.assertEqual(authorize(
                first, store=DurableAuthorityStore(path),
                observed=_observed(first)).reason_code,
                "P5_DECISION_OBSERVATION_UNVERIFIED")
            second = _request(decision_id="D-test-2")
            second["action"]["affected_surfaces"] = ["packages/task/lib/task/other.py"]
            second["action"]["declared_scope"] = ["packages/task/lib/task/other.py"]
            self.assertEqual(authorize(
                second, store=DurableAuthorityStore(path),
                observed=_observed(second)).reason_code,
                "P5_DECISION_OBSERVATION_UNVERIFIED")

    def test_enforced_authorize_rejects_caller_fabricated_observation(self):
        request = _request()
        with tempfile.TemporaryDirectory() as tmp:
            result = authorize(
                request, store=DurableAuthorityStore(Path(tmp) / "authority.json"),
                observed=_observed(request, provenance="caller-says-so"))
        self.assertEqual(result.reason_code, "P5_DECISION_OBSERVATION_UNVERIFIED")


class ClarificationAndResponseTests(unittest.TestCase):
    def _clarification(self):
        request = _request(kind="clarification")
        request["missing_fields"] = ["environment"]
        return request

    def test_allowlisted_answer_has_provenance_and_reclassification(self):
        result = auto_answer_clarification(
            self._clarification(), question_class="repository_config", field="environment",
            sources={"repository_config": {"value": "test", "record_id": "cfg:1", "record_version": "v1"}})
        self.assertEqual(result["response"]["reclassified_to"], "clarification")
        self.assertTrue(result["response"]["provenance"]["verified"])

    def test_answer_that_changes_intent_reclassifies_to_authorization(self):
        request = self._clarification()
        request["action"]["requires_authorization_when"] = {"environment": "prod"}
        result = auto_answer_clarification(
            request, question_class="repository_config", field="environment",
            sources={"repository_config": {"value": "prod", "record_id": "cfg:1", "record_version": "v1"}})
        self.assertEqual(result["response"]["reclassified_to"], "authorization")

    def test_unallowlisted_or_unprovenanced_answer_requires_approval(self):
        for question_class, sources in (("chat_memory", {}), ("repository_config", {"repository_config": {}})):
            with self.subTest(question_class=question_class):
                self.assertEqual(auto_answer_clarification(
                    self._clarification(), question_class=question_class, field="environment", sources=sources
                ).verdict, "approval_required")

    def test_digest_mismatch_creates_next_action_version(self):
        request = self._clarification()
        response = {"selected_option": "apply", "policy_digest": _frame()["_policy_digest"], "action_digest": "0" * 64,
                    "reclassified_to": "clarification", "provenance": {"verified": True}}
        result = apply_response(request, response)
        self.assertEqual(result["verdict"].reason_code, "P5_DECISION_DIGEST_MISMATCH")
        self.assertEqual(result["new_request"]["action_version"], 2)

    def test_clarification_without_reclassification_is_rejected(self):
        request = self._clarification()
        response = {"selected_option": "apply", "policy_digest": _frame()["_policy_digest"], "action_digest": request["action_digest"],
                    "provenance": {"verified": True}}
        self.assertEqual(apply_response(request, response).reason_code,
                         "P5_DECISION_RECLASSIFICATION_REQUIRED")

    def test_response_is_single_use(self):
        request = _request()
        response = {"selected_option": "apply", "policy_digest": _frame()["_policy_digest"], "action_digest": request["action_digest"]}
        store = ResponseStore()
        self.assertEqual(apply_response(request, response, store=store,
                                        mode="diagnostic")["verdict"], "applied")
        self.assertEqual(apply_response(request, response, store=store,
                                        mode="diagnostic").reason_code,
                         "P5_DECISION_RESPONSE_REUSED")

    def test_durable_response_is_single_use_after_reopen(self):
        request = _request()
        response = {"selected_option": "apply", "policy_digest": _frame()["_policy_digest"],
                    "action_digest": request["action_digest"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authority.json"
            self.assertEqual(apply_response(
                request, response, store=DurableAuthorityStore(path))["verdict"], "applied")
            self.assertEqual(apply_response(
                request, response, store=DurableAuthorityStore(path)).reason_code,
                "P5_DECISION_RESPONSE_REUSED")

    def test_concurrent_processes_consume_response_exactly_once(self):
        request = _request()
        response = {"selected_option": "apply", "policy_digest": _frame()["_policy_digest"],
                    "action_digest": request["action_digest"]}
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "authority.json")
            context = multiprocessing.get_context("fork")
            queue = context.Queue()
            processes = [context.Process(
                target=_consume_response_process,
                args=(path, request, response, queue)) for _ in range(2)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(5)
                self.assertEqual(process.exitcode, 0)
            self.assertCountEqual(
                [queue.get(timeout=1), queue.get(timeout=1)],
                ["applied", "P5_DECISION_RESPONSE_REUSED"])

    def test_unknown_response_option_is_rejected(self):
        request = _request()
        response = {"selected_option": "invented", "policy_digest": _frame()["_policy_digest"],
                    "action_digest": request["action_digest"]}
        self.assertEqual(apply_response(request, response).reason_code,
                         "P5_DECISION_UNKNOWN_OPTION")


class StaticBoundaryTests(unittest.TestCase):
    def test_evaluate_and_authorize_do_not_return_bool_annotation(self):
        import ast
        path = ROOT / "packages/task/lib/task/plan_authority.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        bad = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
               and node.name in ("evaluate", "authorize")
               and isinstance(node.returns, ast.Name) and node.returns.id == "bool"]
        self.assertEqual(bad, [])

    def test_no_model_or_network_client_imports(self):
        import ast
        path = ROOT / "packages/task/lib/task/plan_authority.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = {alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import)
                   for alias in node.names}
        imports |= {node.module.split(".")[0] for node in ast.walk(tree)
                    if isinstance(node, ast.ImportFrom) and node.module}
        self.assertFalse(imports & {"anthropic", "openai", "httpx", "requests", "urllib"})
