"""Executor/reviewer separation and failure branches, with real isolated git trees."""
import hashlib
import json
import shutil
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

try:
    from .fixtures import write_valid_plan
except ImportError:
    from fixtures import write_valid_plan
from task import review_packet as review, terminal_policy, plan_bundle, plan_lint, journal, task_contract


class ReviewPacketTests(unittest.TestCase):
    def test_free_reviewer_selector_context_effort_and_trailing_slash(self):
        for selector in ("grok/grok-4.7/500k/", "grok/grok-4.7/500K", "grok/grok-4.7/500000"):
            self.assertEqual(review.reviewer(selector)["context_tokens"], 500000)
            self.assertEqual(review.canonical_selector(selector), "grok/grok-4.7/500000")
        for selector in ("grok/grok-4.7/high/", "grok/grok-4.7/hight/", "grok/grok-4.7/HIGH"):
            self.assertEqual(review.selected_effort(selector, None), "high")
            self.assertEqual(review.canonical_selector(selector), "grok/grok-4.7")
        self.assertEqual(review.selected_effort("grok/grok-4.7/500k/xhigh/", None), "xhigh")
        self.assertEqual(review.reviewer("grok/grok-4.7/high/1m/")["context_tokens"], 1000000)
        self.assertEqual(review.invocation_selection("task:review REVIEW P1.1 --reviewer grok/grok-4.7/hight/")["effort"], "high")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_ROUTE_MISMATCH"):
            review.selected_effort("grok/grok-4.7/low", "high")
        for selector in ("grok/grok-4.7/unknown", "grok/grok-4.7/0k", "grok/grok-4.7/500k/1m", "grok/grok-4.7/high/low", "grok//high"):
            with self.assertRaises(review.ReviewError):
                review.reviewer(selector)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.plan = write_valid_plan(self.root, "REVIEW")
        self.spec = self.plan / "phases/P1/P1.1.md"
        self.product = self.plan / "lib/pkg/config.py"
        self.product.parent.mkdir(parents=True, exist_ok=True)
        self.product.write_text("value = 1\n")
        for args in (("init", "-q"), ("add", "."),
                     ("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-qm", "baseline")):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)
        self.spec.write_text(self.spec.read_text().replace(
            "**Validation:**", "**Validation:** owner-review: grok/grok-4.7;"))
        transport = patch("task.review_grok_acp.run", side_effect=AssertionError(
            "unit tests must supply an explicit fake native transport"))
        transport.start()
        self.addCleanup(transport.stop)

    def packet(self, **kwargs):
        return review.packet(self.plan, "P1.1", selector="grok/grok-4.7",
                             executor_session="executor", **kwargs)

    def manifest(self, packet):
        return json.loads(Path(packet["manifest"]).read_text())

    def verdict(self, manifest, findings=None):
        return {"schema_version": "review-verdict/v1", "candidate_sha256": manifest["candidate_sha256"],
                "reviewer": manifest["reviewer"], "verdict": "FINDINGS" if findings else "GREEN",
                "findings": findings or []}

    def native_result(self, manifest, *, findings=None, complete=True, detail="ACP end_turn"):
        return {"session": "independent-native", "raw": b"native test transcript\n", "stderr": b"",
                "output": json.dumps(self.verdict(manifest, findings)).encode(), "complete": complete,
                "detail": detail, "observed_context": None,
                "provider_route": {"model": "grok-4.7", "effort": "high"}}

    def finding(self, *, file="lib/pkg/config.py", risk="concurrency", area="tree-lock"):
        return {"severity": "major", "risk_class": risk, "area": area, "file": file, "line": 1,
                "scenario": "op A takes x then y; op B takes y then x", "evidence": "reproduced lock schedule"}

    def receive(self, packet, *, findings=None, session="reviewer", selector="grok/grok-4.7", complete=True):
        manifest = self.manifest(packet)
        directory = review._location(self.plan, "P1.1")
        with review._lock(directory):
            return review._record(self.plan, directory, manifest,
                                  output=json.dumps(self.verdict(manifest, findings)).encode(), session=session,
                                  observed_selector=selector, complete=complete, detail="test-provider")

    def systemic(self):
        artifact = self.plan / "artifacts/P1.1"
        artifact.mkdir(parents=True, exist_ok=True)
        model = artifact / "invariant-model.md"
        model.write_text("# Model\nAll writers acquire tree before node on PG and MySQL; pairwise schedules checked.\n")
        check = artifact / "self-check.json"
        check.write_text(json.dumps({"schema_version": "self-check/v1",
                                    "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
                                    "checks": [{"invariant": "acyclic acquisition order", "evidence": "all operation pairs on both drivers"}],
                                    "risks": []}))
        self.spec.write_text(self.spec.read_text().replace(
            "**Implementation Rules:**", "**Implementation Rules:** risk-class: concurrency; invariant-model: artifacts/P1.1/invariant-model.md;")
            .replace("**Validation:**", "**Validation:** self-check: artifacts/P1.1/self-check.json;"))
        return model, check

    def test_pending_close_green_close_and_stale_product(self):
        validation = [{"carrier": "tests", "status": "green", "evidence_ids": ["affected-tests"]}]
        with self.assertRaisesRegex(terminal_policy.TerminalPolicyError, "OWNER_REVIEW_PENDING"):
            terminal_policy.build_decision(self.plan, "P1.1", result="closed-green", validation=validation)
        packet = self.packet()
        receipt = self.receive(packet)
        self.assertEqual(receipt["action"], "accept-candidate")
        terminal_policy.build_decision(self.plan, "P1.1", result="closed-green", validation=validation)
        self.product.write_text("value = 2\n")
        with self.assertRaisesRegex(terminal_policy.TerminalPolicyError, "REVIEW_CANDIDATE_STALE"):
            terminal_policy.build_decision(self.plan, "P1.1", result="closed-green", validation=validation)

    def test_foreign_dirty_and_bookkeeping_do_not_invalidate_review(self):
        self.receive(self.packet())
        (self.root / "foreign.py").write_text("foreign = 1\n")
        (self.plan / "journal.jsonl").write_text("bookkeeping-only")
        review.require_green(self.plan, "P1.1", "grok/grok-4.7")

    def test_reviewed_untracked_file_commit_keeps_original_green_and_receipt(self):
        new = self.root / "new.py"
        new.write_text("reviewed = True\n")
        packet = self.packet(paths=["new.py"])
        self.receive(packet)
        manifest = self.manifest(packet)
        receipt = review._location(self.plan, "P1.1") / "attempt-0001/receipt.json"
        original_manifest, original_receipt = Path(packet["manifest"]).read_bytes(), receipt.read_bytes()
        subprocess.run(["git", "-C", str(self.root), "add", "new.py"], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "-c", "user.name=Test", "-c", "user.email=test@example.test",
                        "commit", "-qm", "track reviewed file"], check=True, capture_output=True)
        fresh = review._snapshot(self.plan, "P1.1", manifest["paths"], manifest["supporting"], manifest["base"])
        self.assertEqual(fresh["product"], manifest["snapshot"]["product"])
        self.assertEqual(fresh["inputs"], manifest["snapshot"]["inputs"])
        self.assertNotEqual(fresh["diff_sha256"], manifest["snapshot"]["diff_sha256"])
        green = review.require_green(self.plan, "P1.1", "grok/grok-4.7")
        self.assertEqual(green["candidate_sha256"], manifest["candidate_sha256"])
        self.assertEqual(Path(packet["manifest"]).read_bytes(), original_manifest)
        self.assertEqual(receipt.read_bytes(), original_receipt)
        new.write_text("reviewed = False\n")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_CANDIDATE_STALE"):
            review.require_green(self.plan, "P1.1", "grok/grok-4.7")

    def test_freshness_refuses_changed_modes_missing_files_and_directory_inventory(self):
        directory = self.root / "owned"
        directory.mkdir()
        member = directory / "member.py"
        member.write_text("bound = True\n")
        original_mode = member.stat().st_mode & 0o777
        self.receive(self.packet(paths=["owned"]))
        member.chmod(original_mode ^ 0o100)
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_CANDIDATE_STALE"):
            review.require_green(self.plan, "P1.1", "grok/grok-4.7")
        member.chmod(original_mode)
        review.require_green(self.plan, "P1.1", "grok/grok-4.7")
        member.unlink()
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_CANDIDATE_STALE"):
            review.require_green(self.plan, "P1.1", "grok/grok-4.7")
        member.write_text("bound = True\n")
        (directory / "unreviewed.py").write_text("added = True\n")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_CANDIDATE_STALE"):
            review.require_green(self.plan, "P1.1", "grok/grok-4.7")

    def test_freshness_binds_symlink_text_and_target_bytes(self):
        target = self.root / "target.py"
        other = self.root / "other.py"
        target.write_text("value = 1\n")
        other.write_text(target.read_text())
        link = self.root / "alias.py"
        link.symlink_to("target.py")
        self.receive(self.packet(paths=["alias.py"], exclusions={"other.py": "independent fixture target"}))
        link.unlink()
        link.symlink_to("other.py")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_CANDIDATE_STALE"):
            review.require_green(self.plan, "P1.1", "grok/grok-4.7")
        link.unlink()
        link.symlink_to("target.py")
        review.require_green(self.plan, "P1.1", "grok/grok-4.7")
        target.write_text("value = 2\n")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_CANDIDATE_STALE"):
            review.require_green(self.plan, "P1.1", "grok/grok-4.7")

    def test_original_snapshot_must_still_match_original_candidate_digest(self):
        packet = self.packet()
        manifest = self.manifest(packet)
        manifest["snapshot"]["diff_sha256"] = "0" * 64
        with self.assertRaisesRegex(review.ReviewError, "original candidate snapshot"):
            review.current(manifest, self.plan)

    def closed_native_review(self, *, paths=(), evidence=(), legacy_sources=False):
        packet = review.packet(self.plan, "P1.1", selector="grok/grok-4.7/500k",
                               executor_session="executor", paths=paths, evidence=evidence)
        manifest = self.manifest(packet)
        if legacy_sources:
            manifest.pop("external_sources", None)
            manifest["supporting"] = [path for path in manifest["supporting"] if path != "composer.lock"]
            manifest["snapshot"]["inputs"] = [row for row in manifest["snapshot"]["inputs"] if row["path"] != "composer.lock"]
            manifest["candidate_sha256"] = review._sha(review._json(manifest["snapshot"]))
            Path(packet["manifest"]).write_bytes(review._json(manifest))
        output = json.dumps(self.verdict(manifest)).encode()
        directory = review._location(self.plan, "P1.1")
        with review._lock(directory):
            review._record(self.plan, directory, manifest, output=output, session="independent-native",
                           observed_selector=manifest["reviewer"], complete=True, detail="ACP end_turn",
                           observed_context=500000)
        attempt = directory / "attempt-0001"
        route = {"session_id": "independent-native", "model": "grok-4.7", "effort": "high", "context_tokens": 500000}
        (attempt / "provider-route.json").write_text(json.dumps(route))
        usage = {"inputTokens": 10, "outputTokens": 5, "cachedReadTokens": 0,
                 "cacheCreationTokens": 0, "numTurns": 1}
        events = [{"method": "session/update", "params": {"sessionId": "independent-native",
                      "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": output.decode()}}}},
                  {"method": "_x.ai/session_notification", "params": {"sessionId": "independent-native",
                      "update": {"sessionUpdate": "response_completed"}}},
                  {"id": 4, "result": {"stopReason": "end_turn", "_meta": {
                      "sessionId": "independent-native", "modelId": "grok-4.7", "usage": usage}}}]
        (attempt / "provider-output.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n")
        from task import review_grok_acp
        (attempt / "transport.json").write_text(json.dumps({"argv": review_grok_acp.argv(manifest, max_turns=20)}))
        decision = terminal_policy.build_decision(self.plan, "P1.1", result="closed-green",
            validation=[{"carrier": "tests", "status": "green", "evidence_ids": ["affected-tests"]}])
        journal.append(self.plan, journal.new_entry(plan_id=self.plan.name, item_id="P1.1", command="plan-run",
            actor="implementation/high", result="closed-green", session_id="executor", run_id="close-run", decision=decision))
        return packet, attempt, decision

    def commit_tree(self):
        for args in (("add", "."), ("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-qm", "closure proof")):
            subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True)

    def test_committed_predecessor_survives_consumer_edits_but_new_close_stays_live(self):
        support = self.root / "validation.log"
        support.write_text("reviewed supporting evidence\n")
        target = self.root / "target.py"
        target.write_text("target = True\n")
        link = self.root / "alias.py"
        link.symlink_to("target.py")
        for name in ("phantoma.py", "phantomb.py"):
            (self.root / name).write_text("bound = True\n")
        _packet, _attempt, decision = self.closed_native_review(paths=["alias.py", "phantom{a,b}.py"], evidence=["validation.log"])
        self.commit_tree()
        self.product.write_text("authorized_consumer_change = True\n")
        support.write_text("consumer supporting evidence\n")
        link.unlink()
        link.symlink_to("validation.log")
        self.assertEqual(task_contract._derived_completed_prefix(self.plan, ["P1.1"]), ("P1.1",))
        with self.assertRaisesRegex(terminal_policy.TerminalPolicyError, "REVIEW_CANDIDATE_STALE"):
            terminal_policy.validate(decision, result="closed-green", plan_dir=self.plan, item_id="P1.1")
        with self.assertRaisesRegex(terminal_policy.TerminalPolicyError, "REVIEW_CANDIDATE_STALE"):
            terminal_policy.build_decision(self.plan, "P1.1", result="closed-green",
                validation=[{"carrier": "tests", "status": "green", "evidence_ids": ["new-tests"]}])
        with self.assertRaisesRegex(ValueError, "REVIEW_CANDIDATE_STALE"):
            journal.append(self.plan, journal.new_entry(plan_id=self.plan.name, item_id="P1.1", command="plan-run",
                actor="implementation/high", result="closed-green", decision=decision))

    def test_uncommitted_close_cannot_supply_historical_predecessor(self):
        self.closed_native_review()
        with self.assertRaisesRegex(ValueError, "REVIEW_CLOSURE_UNCOMMITTED"):
            task_contract._derived_completed_prefix(self.plan, ["P1.1"])

    def journal_lint_errors(self):
        from task.plan_lint_checks import parsing
        diagnostics = plan_lint.Diagnostics()
        parsing._lint_plan_journal_20(self.plan, self.plan.name, diagnostics)
        return diagnostics.errors + diagnostics.warnings

    def test_journal_lint_accepts_committed_close_after_consumer_product_edits(self):
        self.closed_native_review()
        self.commit_tree()
        self.product.write_text("consumer_change = True\n")
        self.assertEqual(self.journal_lint_errors(), [])

    def test_journal_lint_uncommitted_close_still_requires_live_review(self):
        self.closed_native_review()
        self.assertEqual(self.journal_lint_errors(), [])
        self.product.write_text("unreviewed_change = True\n")
        self.assertTrue(any("REVIEW_CANDIDATE_STALE" in error
                            for error in self.journal_lint_errors()))

    def test_journal_lint_invalid_committed_proof_cannot_fall_back_to_live_green(self):
        _packet, attempt, _decision = self.closed_native_review()
        route_path = attempt / "provider-route.json"
        original_route = route_path.read_bytes()
        route = json.loads(original_route)
        route["effort"] = "low"
        route_path.write_text(json.dumps(route))
        self.commit_tree()
        route_path.write_bytes(original_route)
        review.require_green(self.plan, "P1.1", "grok/grok-4.7/500k")
        self.assertTrue(any("REVIEW_CLOSURE_INVALID" in error
                            for error in self.journal_lint_errors()))

    def test_closure_tree_must_contain_exact_reviewed_product_and_inputs(self):
        self.closed_native_review()
        self.product.write_text("changed_before_closure_commit = True\n")
        self.commit_tree()
        with self.assertRaisesRegex(ValueError, "closure commit changed reviewed product"):
            task_contract._derived_completed_prefix(self.plan, ["P1.1"])

    def test_malformed_committed_receipt_manifest_output_route_and_stream_are_refused(self):
        cases = ("self-review", "snapshot", "schema", "packet-manifest", "output", "route", "stream")
        for case in cases:
            with self.subTest(case=case):
                other = ReviewPacketTests("test_pending_close_green_close_and_stale_product")
                other.setUp()
                try:
                    packet, attempt, _decision = other.closed_native_review()
                    if case in {"self-review", "snapshot", "schema"}:
                        path = attempt / "receipt.json"
                        receipt = json.loads(path.read_text())
                        if case == "self-review":
                            receipt["reviewer_session"] = "executor"
                        elif case == "schema":
                            receipt["schema_version"] = "unverified/v1"
                        else:
                            receipt["manifest"]["snapshot"]["diff_sha256"] = "0" * 64
                        path.write_text(json.dumps(receipt))
                    elif case == "packet-manifest":
                        path = Path(packet["manifest"])
                        manifest = json.loads(path.read_text()); manifest["effort"] = "low"
                        path.write_text(json.dumps(manifest))
                    elif case == "output":
                        (attempt / "output.json").write_text('{"forged":"GREEN"}')
                    elif case == "route":
                        path = attempt / "provider-route.json"
                        route = json.loads(path.read_text()); route["effort"] = "low"
                        path.write_text(json.dumps(route))
                    else:
                        path = attempt / "provider-output.jsonl"
                        events = [json.loads(row) for row in path.read_text().splitlines()]
                        events[0]["params"]["update"]["content"]["text"] = '{"actual":"FINDINGS"}'
                        path.write_text("\n".join(json.dumps(row) for row in events) + "\n")
                    other.commit_tree()
                    with self.assertRaises(ValueError):
                        task_contract._derived_completed_prefix(other.plan, ["P1.1"])
                finally:
                    other.doCleanups()

    def test_historical_proof_uses_frozen_artifacts_after_later_receipt_mutation(self):
        _packet, attempt, _decision = self.closed_native_review()
        self.commit_tree()
        path = attempt / "receipt.json"
        receipt = json.loads(path.read_text()); receipt["reviewer_session"] = "executor"
        path.write_text(json.dumps(receipt))
        self.commit_tree()
        self.assertEqual(task_contract._derived_completed_prefix(self.plan, ["P1.1"]), ("P1.1",))
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_NOT_INDEPENDENT"):
            review.require_green(self.plan, "P1.1", "grok/grok-4.7")

    def test_later_commits_cannot_retroactively_supply_missing_closure_proof(self):
        _packet, attempt, _decision = self.closed_native_review()
        output = (attempt / "output.json").read_bytes()
        (attempt / "output.json").unlink()
        self.commit_tree()
        (attempt / "output.json").write_bytes(output)
        self.commit_tree()
        with self.assertRaisesRegex(ValueError, "missing immutable review artifact"):
            task_contract._derived_completed_prefix(self.plan, ["P1.1"])

    def test_uncommitted_terminal_run_identity_mutation_is_refused(self):
        self.closed_native_review()
        self.commit_tree()
        path = self.plan / "journal.jsonl"
        events = [json.loads(row) for row in path.read_text().splitlines() if row.strip()]
        events[-1]["run_id"] = "forged-run"
        path.write_text("\n".join(json.dumps(row) for row in events) + "\n")
        with self.assertRaisesRegex(ValueError, "REVIEW_CLOSURE_UNCOMMITTED"):
            task_contract._derived_completed_prefix(self.plan, ["P1.1"])

    def test_evidence_and_new_files_are_digest_bound(self):
        evidence = self.root / "affected.log"
        evidence.write_text("green\n")
        new = self.root / "lib/pkg/new.py"
        new.parent.mkdir(parents=True, exist_ok=True)
        new.write_text("new = 1\n")
        packet = self.packet(paths=["lib/pkg/new.py"], evidence=["affected.log"])
        self.assertIn("new = 1", Path(packet["packet"]).read_text())
        self.receive(packet)
        evidence.write_text("red\n")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_CANDIDATE_STALE"):
            review.require_green(self.plan, "P1.1", "grok/grok-4.7")

    def test_self_review_and_wrong_model_are_refused(self):
        packet = self.packet()
        for session, selector in (("executor", "grok/grok-4.7"), ("reviewer", "grok/grok-4.6")):
            with self.assertRaisesRegex(review.ReviewError, "REVIEW_NOT_INDEPENDENT"):
                self.receive(packet, session=session, selector=selector)

    def test_same_systemic_class_in_new_file_changes_tactics_and_caps_rounds(self):
        self.systemic()
        first = self.receive(self.packet(), findings=[self.finding()])
        self.assertEqual(first["action"], "return-owning-continuation")
        self.product.write_text("value = 2\n")
        second = self.receive(self.packet(), findings=[self.finding(file="lib/pkg/other.py")])
        self.assertEqual(second["action"], "design-required")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_SYSTEMIC_MODEL_REQUIRED"):
            review.execution_boundary(self.plan, "P1.1", plan_bundle._fields(self.plan, "P1.1"))
        model = self.plan / "artifacts/P1.1/invariant-model.md"
        model.write_text(model.read_text() + "\nRevised all interfering operation pairs.\n")
        review.execution_boundary(self.plan, "P1.1", plan_bundle._fields(self.plan, "P1.1"))
        value_path = self.plan / "artifacts/P1.1/self-check.json"
        value = json.loads(value_path.read_text())
        value["model_sha256"] = hashlib.sha256(model.read_bytes()).hexdigest()
        value_path.write_text(json.dumps(value))
        self.product.write_text("value = 3\n")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_BUDGET_EXHAUSTED"):
            self.packet()
        with self.assertRaisesRegex(review.ReviewError, "OWNER_REVIEW_NOT_GREEN"):
            review.require_green(self.plan, "P1.1", "grok/grok-4.7")

    def test_incomplete_attempts_never_consume_review_round_or_block_repaired_transport(self):
        packet = self.packet()
        first = self.receive(packet, complete=False)
        second = self.receive(packet, complete=False)
        self.assertEqual(first["action"], "retry-transport")
        self.assertEqual(second["action"], "retry-transport")
        self.assertEqual(self.packet()["completed_rounds"], 0)
        with patch("task.session_context.current_id", return_value="review-stream"), \
                patch("task.review_grok_acp.run", side_effect=OSError("simulated transport failure")):
            third = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")
        self.assertEqual(third["action"], "retry-transport")
        self.assertEqual(self.packet()["completed_rounds"], 0)
        self.receive(packet)
        self.assertEqual(self.packet()["action"], "reuse-verdict")

    def test_green_verdict_is_reused_without_another_model_call(self):
        packet = self.packet()
        self.receive(packet)
        self.assertEqual(self.packet()["action"], "reuse-verdict")
        original = subprocess.run
        def git_only(argv, **kwargs):
            self.assertEqual(argv[0], "git")
            return original(argv, **kwargs)
        with patch("task.session_context.current_id", return_value="review-stream"), patch("subprocess.run", side_effect=git_only):
            result = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")
            self.assertEqual(result["action"], "reuse-verdict")

    def test_oversized_code_is_referenced_and_required_context_never_clipped(self):
        self.product.write_text("é" * 60_000)
        packet = self.packet()
        self.assertLessEqual(packet["packet_bytes"], review.PACKET_BYTES_MAX)
        self.assertIn("No code is truncated", Path(packet["packet"]).read_text())
        self.spec.write_text(self.spec.read_text() + "\n" + "é" * 45_000)
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_PACKET_TOO_LARGE"):
            self.packet()

    def test_design_requires_model_and_deferred_risk_requires_owner(self):
        self.spec.write_text(self.spec.read_text().replace("**Implementation Rules:**", "**Implementation Rules:** risk-class: concurrency;"))
        fields = plan_bundle._fields(self.plan, "P1.1")
        with self.assertRaisesRegex(review.ReviewError, "INVARIANT_MODEL_REQUIRED"):
            review.validate_design(self.plan, fields)
        self.spec.write_text(self.spec.read_text().replace("risk-class: concurrency;", ""))
        model, check = self.systemic()
        value = json.loads(check.read_text())
        value["risks"] = [{"risk": "race", "status": "deferred", "evidence": "trace"}]
        check.write_text(json.dumps(value))
        with self.assertRaisesRegex(review.ReviewError, "SELF_CHECK_INVALID"):
            self.packet()
        value["risks"][0].update(owner="P1.1", reason="owning correction")
        check.write_text(json.dumps(value))
        self.packet()
        model.write_text("changed model")
        with self.assertRaisesRegex(review.ReviewError, "SELF_CHECK_INVALID"):
            self.packet()

    def test_grok_argv_closes_mcp_write_shell_and_subagent_paths(self):
        packet = self.packet()
        args = review.grok_argv(self.manifest(packet), Path(packet["packet"]), self.root, session="test", max_turns=20)
        self.assertNotIn("-p", args)
        self.assertIn("read_file,grep,list_dir", args)
        self.assertIn("MCPTool", args)
        self.assertIn("--no-subagents", args)
        for flag in ("Bash", "Edit", "Write"):
            self.assertIn(flag, args)

    def test_context_requirement_verified_without_token_spend_budget_or_retry(self):
        for context, expected in ((250000, "review-context-undershoot"),
                                  (None, "review-context-unverifiable"), (500000, "accept-candidate")):
            self.product.write_text(f"context_case = {context!r}\n")
            packet = review.packet(self.plan, "P1.1", selector="grok/grok-4.7/500k/high/", executor_session="executor")
            manifest = self.manifest(packet)
            self.assertEqual(manifest["reviewer"], "grok/grok-4.7/500000")
            def provider_call(selected, packet_bytes, **kwargs):
                self.assertEqual(selected["route"]["model"], "grok-4.7")
                self.assertEqual(selected["effort"], "high")
                self.assertEqual(packet_bytes, Path(packet["packet"]).read_bytes())
                return {"session": "independent-native-session", "raw": b"native ACP transcript\n",
                        "stderr": b"", "output": json.dumps(self.verdict(manifest)).encode(),
                        "detail": "ACP end_turn", "complete": True, "observed_context": context,
                        "provider_route": {"context_tokens": context}}
            with patch("task.session_context.current_id", return_value="review-stream"), \
                    patch("task.review_grok_acp.run", side_effect=provider_call):
                receipt = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7/500k/")
            self.assertEqual(receipt["action"], expected)
            if context == 500000:
                review.require_green(self.plan, "P1.1", "grok/grok-4.7/500K/hight/")
                review.require_green(self.plan, "P1.1", "grok/grok-4.7")
            else:
                self.assertEqual(receipt["status"], "incomplete")

    def test_incomplete_error_is_not_hidden_by_missing_context(self):
        packet = review.packet(self.plan, "P1.1", selector="grok/grok-4.7/500k", executor_session="executor")
        manifest = self.manifest(packet)
        directory = review._location(self.plan, "P1.1")
        with review._lock(directory):
            receipt = review._record(self.plan, directory, manifest, output=b"partial",
                                     session="independent", observed_selector=manifest["reviewer"],
                                     complete=False, detail="exit=1; error_max_turns", observed_context=None)
        self.assertEqual(receipt["detail"], "exit=1; error_max_turns")
        self.assertEqual(receipt["action"], "retry-transport")

    def test_initial_packet_has_no_previous_findings_lookup(self):
        packet = self.packet()
        self.assertIn("there are no previous findings to locate", Path(packet["packet"]).read_text())

    def test_native_capacity_refusal_has_typed_action_and_archived_witness(self):
        packet = review.packet(self.plan, "P1.1", selector="grok/grok-4.7/500k", executor_session="executor")
        result = {"session": "independent", "raw": b"ACP evidence\n", "stderr": b"provider stderr",
                  "output": b"", "complete": False, "observed_context": 256000,
                  "provider_route": {"context_tokens": 256000},
                  "detail": "REVIEW_CONTEXT_UNDERSHOOT: native context is smaller than requested"}
        with patch("task.session_context.current_id", return_value="review-stream"), \
                patch("task.review_grok_acp.run", return_value=result):
            receipt = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7/500k")
        self.assertEqual(receipt["action"], "review-context-undershoot")
        self.assertEqual(receipt["detail"], result["detail"])
        attempt = review._location(self.plan, "P1.1") / "attempt-0001"
        self.assertEqual((attempt / "provider-output.jsonl").read_bytes(), result["raw"])
        self.assertEqual((attempt / "stderr.log").read_bytes(), result["stderr"])
        self.assertEqual(json.loads((attempt / "provider-route.json").read_text()), result["provider_route"])

    def test_no_context_route_uses_native_acp_attestation(self):
        for witnessed in (False, True):
            self.product.write_text(f"witnessed = {witnessed}\n")
            packet = self.packet()
            manifest = self.manifest(packet)
            with patch("task.session_context.current_id", return_value="review-stream"), \
                    patch("task.review_grok_acp.run", return_value=self.native_result(manifest, complete=witnessed)) as invoke:
                receipt = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")
            self.assertEqual(invoke.call_args.kwargs["max_turns"], 0)
            self.assertNotIn("context_tokens", invoke.call_args.args[0]["route"])
            self.assertEqual(receipt["status"], "complete" if witnessed else "incomplete")

    def test_grok_provider_envelope_must_be_complete_and_exact(self):
        packet = self.packet()
        manifest = self.manifest(packet)
        with patch("task.session_context.current_id", return_value="review-stream"), \
                patch("task.review_grok_acp.run", return_value=self.native_result(manifest)):
            result = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")
            self.assertEqual(result["action"], "accept-candidate")
        attempt = self.plan / "artifacts/P1.1/owner-review/attempt-0001"
        self.assertTrue((attempt / "provider-output.jsonl").is_file())

    def test_executor_cannot_launch_review_transport(self):
        packet = self.packet()
        with patch("task.session_context.current_id", return_value="executor"):
            with self.assertRaisesRegex(review.ReviewError, "REVIEW_EXECUTOR_COUPLING"):
                review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")

    def test_authorized_executor_launches_independent_transport_and_reuses_green(self):
        self.spec.write_text(self.spec.read_text().replace("owner-review: grok/grok-4.7;", ""))
        review.register_request(self.plan, "P1.1", selector="grok/grok-4.7", effort="high",
                                executor_session="executor", invocation="task:plan-run REVIEW P1.1 --reviewer grok/grok-4.7")
        validation = [{"carrier": "tests", "status": "green", "evidence_ids": ["affected-tests"]}]
        with self.assertRaisesRegex(terminal_policy.TerminalPolicyError, "OWNER_REVIEW_PENDING"):
            terminal_policy.build_decision(self.plan, "P1.1", result="closed-green", validation=validation)
        packet = self.packet()
        manifest = self.manifest(packet)
        sessions = []
        def provider_call(manifest, packet_bytes, **kwargs):
            session = "independent-native"
            sessions.append(session)
            self.assertNotEqual(session, "executor")
            return self.native_result(manifest)
        with patch("task.session_context.current_id", return_value="executor"), patch("task.review_grok_acp.run", side_effect=provider_call):
            self.assertEqual(review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")["action"], "accept-candidate")
            self.assertEqual(review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")["action"], "reuse-verdict")
        self.assertEqual(len(sessions), 1)
        terminal_policy.build_decision(self.plan, "P1.1", result="closed-green", validation=validation)
        # Resuming orchestration in another executor is bookkeeping, not changed product.
        review.register_request(self.plan, "P1.1", selector="grok/grok-4.7", effort="high",
                                executor_session="resumed-executor", invocation="task:plan-run REVIEW P1.1")
        resumed = review.packet(self.plan, "P1.1", selector="grok/grok-4.7", executor_session="resumed-executor")
        self.assertEqual(resumed["action"], "reuse-verdict")
        terminal_policy.build_decision(self.plan, "P1.1", result="closed-green", validation=validation)
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_ROUTE_MISMATCH"):
            review.register_request(self.plan, "P1.1", selector="grok/grok-4.6", effort="high",
                                    executor_session="executor", invocation="task:plan-run REVIEW P1.1")

    def test_automatic_review_fix_once_then_second_green_or_stop(self):
        review.register_request(self.plan, "P1.1", selector="grok/grok-4.7", effort="high",
                                executor_session="executor", invocation="task:plan-run REVIEW P1.1 --reviewer grok/grok-4.7")
        calls = []
        def provider_call(manifest, packet_bytes, **kwargs):
            calls.append(manifest["candidate_sha256"])
            findings = [self.finding(risk="local")] if len(calls) == 1 else None
            return self.native_result(manifest, findings=findings)
        with patch("task.session_context.current_id", return_value="executor"), patch("task.review_grok_acp.run", side_effect=provider_call):
            first = self.packet()
            self.assertEqual(review.run(self.plan, first["manifest"], selector="grok/grok-4.7")["action"], "return-owning-continuation")
            self.product.write_text("value = 2\n")
            second = self.packet()
            self.assertEqual(review.run(self.plan, second["manifest"], selector="grok/grok-4.7")["action"], "accept-candidate")
            self.product.write_text("value = 3\n")
            with self.assertRaisesRegex(review.ReviewError, "REVIEW_BUDGET_EXHAUSTED"):
                self.packet()
        self.assertEqual(len(calls), 2)

    def test_one_owner_extra_round_is_candidate_bound_and_consumed(self):
        first = self.packet()
        self.receive(first, findings=[self.finding(risk="local")])
        self.product.write_text("value = 2\n")
        second = self.packet()
        self.receive(second, findings=[self.finding(risk="local")])
        self.product.write_text("value = 3\n")
        manifest = self.manifest(second)
        snapshot = review._snapshot(self.plan, "P1.1", manifest["paths"], manifest["supporting"], manifest["base"])
        digest = review._sha(review._json(snapshot))
        grant = SimpleNamespace(identifier="D9", status="accepted", superseded_by=None, item="P1.1",
                                body=f"Owner permits [REVIEW-EXTRA-ROUND:P1.1:{digest}:3]")
        with patch("task.plan_decisions.load_decisions", return_value=(grant,)):
            third = self.packet(budget_decision="D9")
            self.assertEqual(self.receive(third)["action"], "accept-candidate")
            self.product.write_text("value = 4\n")
            with self.assertRaisesRegex(review.ReviewError, "REVIEW_BUDGET_EXHAUSTED"):
                self.packet(budget_decision="D9")

    def test_record_captures_actual_route_and_rejects_an_executor(self):
        packet = self.packet()
        manifest = self.manifest(packet)
        output = self.root / "verdict.json"
        output.write_text(json.dumps(self.verdict(manifest)))
        actual = {"model": "grok-4.7", "effort": "high", "thread_id": "executor"}
        with patch("task.route_evidence.capture_launch", return_value=actual), patch("task.session_context.resolve", return_value=SimpleNamespace(provider="grok")):
            with self.assertRaisesRegex(review.ReviewError, "REVIEW_NOT_INDEPENDENT"):
                review.record(self.plan, packet["manifest"], output, invocation="task:review REVIEW P1.1 --reviewer grok/grok-4.7")
            actual["thread_id"] = "reviewer"
            self.assertEqual(review.record(self.plan, packet["manifest"], output,
                                          invocation="task:review REVIEW P1.1 --reviewer grok/grok-4.7")["action"], "accept-candidate")

    def test_cancelled_wrong_model_timeout_and_malformed_output_never_green(self):
        for kind in ("cancelled", "wrong-model", "timeout", "malformed"):
            self.product.write_text(f"candidate = '{kind}'\n")
            packet = self.packet()
            manifest = self.manifest(packet)
            def invoke(manifest, packet_bytes, **kwargs):
                if kind == "timeout":
                    raise subprocess.TimeoutExpired(["grok"], 1, output=b"partial", stderr=b"tool denied")
                if kind == "malformed":
                    return {**self.native_result(manifest), "output": b"not json"}
                return self.native_result(manifest, complete=False, detail=kind)
            with patch("task.session_context.current_id", return_value="review-stream"), patch("task.review_grok_acp.run", side_effect=invoke):
                receipt = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7", timeout=1)
            self.assertEqual(receipt["status"], "incomplete", kind)
            with self.assertRaisesRegex(review.ReviewError, "OWNER_REVIEW_PENDING"):
                review.require_green(self.plan, "P1.1", "grok/grok-4.7")

    def test_candidate_changed_during_review_archives_incomplete_output(self):
        packet = self.packet()
        manifest = self.manifest(packet)
        def invoke(manifest, packet_bytes, **kwargs):
            self.product.write_text("changed = True\n")
            return self.native_result(manifest)
        with patch("task.session_context.current_id", return_value="review-stream"), patch("task.review_grok_acp.run", side_effect=invoke):
            receipt = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")
        self.assertEqual(receipt["status"], "incomplete")
        self.assertIn("REVIEW_CANDIDATE_STALE", receipt["detail"])
        self.assertTrue((self.plan / "artifacts/P1.1/owner-review/attempt-0001/provider-output.jsonl").is_file())

    def test_path_escape_and_self_invalidating_candidate_are_refused(self):
        for relative in ("../outside", "plans/REVIEW/artifacts/P1.1/owner-review"):
            with self.assertRaises(review.ReviewError):
                self.packet(paths=[relative])

    def test_review_invocation_inherits_route_and_rejects_duplicate_selection(self):
        for invocation in ("task:review diff", "task:plan-audit REVIEW design"):
            self.assertIsNone(review.invocation_selection(invocation))
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_INVOCATION_INVALID"):
            review.invocation_selection("task:review diff --reviewer grok/grok-4.7 --reviewer codex/gpt-6")
        value = review.invocation_selection("task:plan-audit REVIEW design --reviewer=codex/gpt-6")
        self.assertEqual(value, {"provider": "codex", "model": "gpt-6", "effort": "xhigh"})

    def test_launch_capture_enforces_selected_provider_and_model(self):
        from task import route_evidence
        invocation = "task:plan-audit REVIEW design --reviewer grok/grok-4.7"
        with self.assertRaisesRegex(route_evidence.RouteEvidenceError, "REVIEW_ROUTE_MISMATCH"):
            route_evidence.capture_launch(expected_invocation=invocation, expected_cwd=self.root, provider="codex")
        with patch("task.route_evidence_grok.capture_current", return_value={"model": "grok-4.6", "effort": "xhigh"}):
            with self.assertRaisesRegex(route_evidence.RouteEvidenceError, "REVIEW_ROUTE_MISMATCH"):
                route_evidence.capture_launch(expected_invocation=invocation, expected_cwd=self.root, provider="grok")

    def test_concrete_brace_glob_inventory_includes_untracked_and_rejects_missing(self):
        folder = self.root / "tests/Folder"
        folder.mkdir(parents=True)
        (folder / "Automatic.php").write_text("<?php // tracked\n")
        self.commit_tree()
        (folder / "Granted.php").write_text("<?php // untracked\n")
        self.spec.write_text(self.spec.read_text().replace("**Files:** lib/pkg/config.py",
            "**Files:** `lib/pkg/config.py`; `tests/Folder/{Automatic,Granted}.php` (`RootRole`, `catalog:cache`, `#[GrantedToAll]`)"))
        packet = self.packet(paths=["tests/Folder/*.php"])
        manifest = self.manifest(packet)
        self.assertEqual([row["path"] for row in manifest["snapshot"]["product"] if row["path"].startswith("tests/")],
                         ["tests/Folder/Automatic.php", "tests/Folder/Granted.php"])
        self.assertTrue(all(row["sha256"] is not None for row in manifest["snapshot"]["product"]))
        (folder / "Added.php").write_text("<?php // later\n")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_CANDIDATE_STALE"):
            review.current(manifest, self.plan)
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_COVERAGE_MISSING"):
            self.packet(paths=["tests/Folder/{Automatic,Missing}.php"])

    def test_changed_file_needs_coverage_or_explicit_foreign_exclusion(self):
        path = self.root / "foreign.py"
        path.write_text("owner_change = True\n")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_CHANGED_PATH_UNCOVERED"):
            self.packet()
        packet = self.packet(exclusions={"foreign.py": "pre-existing owner work outside this item"})
        self.assertEqual(self.manifest(packet)["exclusions"], {"foreign.py": "pre-existing owner work outside this item"})
        self.assertEqual(path.read_text(), "owner_change = True\n")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_EXCLUSION_INVALID"):
            self.packet(exclusions={"foreign.py": ""})

    def test_deleted_product_is_an_authenticated_tombstone(self):
        deleted = self.root / "removed.py"
        deleted.write_text("old = True\n")
        self.commit_tree()
        deleted.unlink()
        self.spec.write_text(self.spec.read_text().replace("**Files:** lib/pkg/config.py", "**Files:** removed.py"))
        packet = self.packet()
        self.assertEqual(self.manifest(packet)["snapshot"]["product"],
                         [{"path": "removed.py", "sha256": None, "mode": None}])
        self.receive(packet)
        review.require_green(self.plan, "P1.1", "grok/grok-4.7")
        deleted.write_text("old = True\n")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_CANDIDATE_STALE"):
            review.require_green(self.plan, "P1.1", "grok/grok-4.7")

    def external_fixture(self):
        (self.root / ".gitignore").write_text("vendor/\n")
        (self.root / "composer.lock").write_text(json.dumps({"packages": [{"name": "laravel/framework",
            "version": "v12.0.0", "source": {"reference": "immutable-source-reference"}}]}))
        self.commit_tree()
        source = self.root / "vendor/laravel/framework/src/Gate.php"
        source.parent.mkdir(parents=True)
        source.write_text("<?php // locked framework source\n")
        return source

    def test_external_source_proof_survives_removed_vendor_and_rejects_blob_lock_reference(self):
        source = self.external_fixture()
        packet, _attempt, decision = self.closed_native_review(evidence=[source.relative_to(self.root).as_posix()])
        manifest = self.manifest(packet)
        self.assertEqual(len(manifest["external_sources"]), 1)
        self.commit_tree()
        source.unlink()
        original = Path(packet["manifest"]).read_bytes()
        review.require_committed_green(self.plan, "P1.1", manifest["reviewer"], effort="high",
                                       decision=decision, result="closed-green")
        self.assertEqual(Path(packet["manifest"]).read_bytes(), original)
        from task import review_sources
        source_record = manifest["external_sources"][0]
        read = lambda path: (self.root / path).read_bytes()
        for kind in ("blob", "lock", "reference"):
            record = json.loads(json.dumps(source_record))
            def corrupted(path):
                payload = read(path)
                return payload + b"changed" if path == record["blob_path"] and kind == "blob" or path == "composer.lock" and kind == "lock" else payload
            if kind == "reference":
                record["identity"]["reference"] = "wrong-reference"
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                review_sources.frozen_members([record], read=corrupted, tree={})

    def test_consulted_dependency_staleness_blocks_reuse_and_close(self):
        from task import review_sources
        dependency = self.root / "dependency.py"
        dependency.write_text("dependency = 1\n")
        self.commit_tree()
        packet = self.packet()
        manifest = self.manifest(packet)
        ledger = review_sources.ReadLedger(self.root)
        ledger.observe({"sessionUpdate": "tool_call", "toolCallId": "read-1", "title": "read_file",
                        "rawInput": {"target_file": str(dependency), "offset": 1, "limit": 20}})
        value = {**self.native_result(manifest), "read_ledger": ledger.result()}
        with patch("task.review_grok_acp.run", return_value=value), patch("task.session_context.current_id", return_value="reviewer"):
            review.run(self.plan, packet["manifest"], selector=manifest["reviewer"])
        review.require_green(self.plan, "P1.1", manifest["reviewer"])
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True, capture_output=True)
        review.require_green(self.plan, "P1.1", manifest["reviewer"])
        dependency.write_text("dependency = 2\n")
        for action in (lambda: review.require_green(self.plan, "P1.1", manifest["reviewer"]),
                       lambda: review.run(self.plan, packet["manifest"], selector=manifest["reviewer"])):
            with self.assertRaisesRegex(review.ReviewError, "REVIEW_DEPENDENCY_STALE"):
                action()

    def test_ignored_composer_lock_is_immutable_source_identity_not_live_dependency(self):
        source = self.external_fixture()
        subprocess.run(["git", "-C", str(self.root), "rm", "--cached", "composer.lock"], check=True, capture_output=True)
        ignore = self.root / ".gitignore"
        ignore.write_text(ignore.read_text() + "composer.lock\n")
        self.commit_tree()
        packet, _attempt, decision = self.closed_native_review(evidence=[source.relative_to(self.root).as_posix()])
        manifest = self.manifest(packet)
        self.assertEqual({row["member"]["path"] for row in manifest["external_sources"]},
                         {"composer.lock", source.relative_to(self.root).as_posix()})
        self.commit_tree()
        source.unlink()
        (self.root / "composer.lock").unlink()
        review.require_committed_green(self.plan, "P1.1", manifest["reviewer"], effort="high",
                                       decision=decision, result="closed-green")

    def test_native_read_ledger_proof_is_portable_to_another_checkout(self):
        from task import review_sources
        packet, attempt, decision = self.closed_native_review()
        manifest = self.manifest(packet)
        update = {"sessionUpdate": "tool_call", "title": "read_file", "toolCallId": "read-product",
                  "rawInput": {"target_file": str(self.product)}}
        ledger = review_sources.ReadLedger(self.root)
        ledger.observe(update)
        payload = review._json(ledger.result())
        (attempt / "read-ledger.json").write_bytes(payload)
        receipt = json.loads((attempt / "receipt.json").read_text())
        receipt["read_ledger_sha256"] = review._sha(payload)
        (attempt / "receipt.json").write_bytes(review._json(receipt))
        witness = json.loads((attempt / "provider-route.json").read_text())
        witness["cwd"] = str(self.root)
        (attempt / "provider-route.json").write_bytes(review._json(witness))
        stream = attempt / "provider-output.jsonl"
        event = {"method": "session/update", "params": {"sessionId": "independent-native", "update": update}}
        stream.write_text(json.dumps(event) + "\n" + stream.read_text())
        self.commit_tree()
        with tempfile.TemporaryDirectory() as temporary:
            copied = Path(temporary) / "checkout"
            shutil.copytree(self.root, copied)
            review.require_committed_green(copied / self.plan.relative_to(self.root), "P1.1", manifest["reviewer"],
                                           effort="high", decision=decision, result="closed-green")

    def test_ignored_product_lock_is_archived_and_verified_without_live_bytes(self):
        self.external_fixture()
        subprocess.run(["git", "-C", str(self.root), "rm", "--cached", "composer.lock"], check=True, capture_output=True)
        ignore = self.root / ".gitignore"
        ignore.write_text(ignore.read_text() + "composer.lock\n")
        self.commit_tree()
        packet, _attempt, decision = self.closed_native_review(paths=[self.product.relative_to(self.root).as_posix(), "composer.lock"])
        manifest = self.manifest(packet)
        self.assertIn("composer.lock", {row["member"]["path"] for row in manifest["external_sources"]})
        self.commit_tree()
        (self.root / "composer.lock").unlink()
        review.require_committed_green(self.plan, "P1.1", manifest["reviewer"], effort="high",
                                       decision=decision, result="closed-green")

    def test_legacy_product_recovery_is_additive_authenticated_and_committed(self):
        from task import review_sources
        source = self.external_fixture()
        subprocess.run(["git", "-C", str(self.root), "rm", "--cached", "composer.lock"], check=True, capture_output=True)
        ignore = self.root / ".gitignore"
        ignore.write_text(ignore.read_text() + "composer.lock\n")
        self.commit_tree()
        packet, attempt, decision = self.closed_native_review(paths=[self.product.relative_to(self.root).as_posix(), "composer.lock"],
            evidence=[source.relative_to(self.root).as_posix()], legacy_sources=True)
        self.commit_tree()
        receipt_bytes = (attempt / "receipt.json").read_bytes()
        manifest = self.manifest(packet)
        def historical():
            review.require_committed_green(self.plan, "P1.1", manifest["reviewer"], effort="high",
                                           decision=decision, result="closed-green")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_EXTERNAL_SOURCE_UNARCHIVED"):
            historical()
        lock = self.root / "composer.lock"
        lock_bytes = lock.read_bytes()
        lock.write_bytes(lock_bytes + b"changed")
        with self.assertRaisesRegex(ValueError, "differs from original reviewed bytes"):
            review_sources.recover(self.plan, "P1.1")
        lock.write_bytes(lock_bytes)
        result = review_sources.recover(self.plan, "P1.1")
        old = Path(result["witness"])
        value = json.loads(old.read_text())
        value["sources"] = [row for row in value["sources"] if row["member"]["path"] != "composer.lock"]
        old.write_bytes(review._json(value))  # Earlier vendor-only recovery remains immutable.
        old_bytes = old.read_bytes()
        self.commit_tree()
        result = review_sources.recover(self.plan, "P1.1")
        self.assertNotEqual(Path(result["witness"]), old)
        self.assertEqual(old.read_bytes(), old_bytes)
        with self.assertRaisesRegex(review.ReviewError, "source recovery differs"):
            historical()
        self.commit_tree()
        lock.unlink()
        source.unlink()
        historical()
        self.assertEqual((attempt / "receipt.json").read_bytes(), receipt_bytes)
        witness = json.loads(Path(result["witness"]).read_text())
        blob = self.root / next(row['blob_path'] for row in witness['sources'] if row['member']['path'] == 'composer.lock')
        blob.write_bytes(b"substituted")
        self.commit_tree()
        with self.assertRaisesRegex(review.ReviewError, "source blob changed"):
            historical()

    def test_legacy_vendor_recovery_never_invents_lock_identity_or_rewrites_receipt(self):
        from task import review_sources
        source = self.external_fixture()
        packet, attempt, decision = self.closed_native_review(
            evidence=[source.relative_to(self.root).as_posix()], legacy_sources=True)
        (self.root / "composer.lock").unlink()
        self.commit_tree()
        before = (attempt / "receipt.json").read_bytes()
        manifest = self.manifest(packet)
        def historical():
            return review.require_committed_green(self.plan, "P1.1", manifest["reviewer"], effort="high",
                                                 decision=decision, result="closed-green")
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_EXTERNAL_SOURCE_UNARCHIVED"):
            historical()
        result = review_sources.recover(self.plan, "P1.1")
        self.assertEqual(result["identity_limit"], "original-lock-not-bound")
        self.assertNotIn("version", json.loads(Path(result["witness"]).read_text())["sources"][0]["identity"])
        with self.assertRaisesRegex(review.ReviewError, "REVIEW_EXTERNAL_SOURCE_UNARCHIVED"):
            historical()
        self.commit_tree()
        source.unlink()
        historical()
        self.assertEqual((attempt / "receipt.json").read_bytes(), before)

    def test_unset_risk_runtime_preflight_and_bounded_summary(self):
        packet = self.packet()
        manifest = self.manifest(packet)
        self.assertEqual(manifest["risk_class"], "unset")
        with patch.object(review, "runtime_provenance", return_value={"schema_version": "wrong"}), \
                self.assertRaisesRegex(review.ReviewError, "REVIEW_RUNTIME_MISMATCH"):
            review.run(self.plan, packet["manifest"], selector=manifest["reviewer"])
        receipt = self.receive(packet)
        summary = review.summary(receipt, review._location(self.plan, "P1.1"))
        self.assertLess(len(json.dumps(summary)), 2000)
        self.assertNotIn("manifest", summary)

    def test_omitted_reviewer_captures_actual_native_route(self):
        self.spec.write_text(self.spec.read_text().replace("owner-review: grok/grok-4.7;", ""))
        actual = {"model": "gpt-6", "effort": "high", "thread_id": "review-session"}
        with patch("task.route_evidence.capture_launch", return_value=actual), \
                patch("task.session_context.resolve", return_value=SimpleNamespace(provider="codex")):
            packet = review.packet(self.plan, "P1.1", executor_session="executor")
        self.assertEqual(self.manifest(packet)["reviewer"], "codex/gpt-6")
        self.assertEqual(self.manifest(packet)["effort"], "high")


if __name__ == "__main__":
    unittest.main()
