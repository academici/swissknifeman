"""Executor/reviewer separation and failure branches, with real isolated git trees."""
import hashlib
import json
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

    def packet(self, **kwargs):
        return review.packet(self.plan, "P1.1", selector="grok/grok-4.7",
                             executor_session="executor", **kwargs)

    def manifest(self, packet):
        return json.loads(Path(packet["manifest"]).read_text())

    def verdict(self, manifest, findings=None):
        return {"schema_version": "review-verdict/v1", "candidate_sha256": manifest["candidate_sha256"],
                "reviewer": manifest["reviewer"], "verdict": "FINDINGS" if findings else "GREEN",
                "findings": findings or []}

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
        self.receive(self.packet(paths=["alias.py"]))
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

    def closed_native_review(self, *, paths=(), evidence=()):
        packet = review.packet(self.plan, "P1.1", selector="grok/grok-4.7/500k",
                               executor_session="executor", paths=paths, evidence=evidence)
        manifest = self.manifest(packet)
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
                patch.object(review, "_invoke", side_effect=OSError("simulated transport failure")):
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

    def test_headless_accounting_alias_requires_native_route_corroboration(self):
        for witnessed in (False, True):
            self.product.write_text(f"witnessed = {witnessed}\n")
            packet = self.packet()
            manifest = self.manifest(packet)
            def invoke(argv, **kwargs):
                envelope = {"text": json.dumps(self.verdict(manifest)),
                            "sessionId": argv[argv.index("--session-id") + 1], "stopReason": "end_turn",
                            "modelUsage": {"grok-4.7-build": {"inputTokens": 10}}}
                return SimpleNamespace(stdout=json.dumps(envelope).encode(), stderr=b"", returncode=0)
            witness = {"model": "grok-4.7", "effort": "high"} if witnessed else {}
            with patch("task.session_context.current_id", return_value="review-stream"), \
                    patch.object(review, "_invoke", side_effect=invoke), \
                    patch("task.review_grok_acp.provider_route", return_value=witness):
                receipt = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")
            self.assertEqual(receipt["status"], "complete" if witnessed else "incomplete")

    def test_grok_provider_envelope_must_be_complete_and_exact(self):
        packet = self.packet()
        manifest = self.manifest(packet)
        def provider_call(argv, **kwargs):
            session = argv[argv.index("--session-id") + 1]
            envelope = {"text": json.dumps(self.verdict(manifest)), "sessionId": session,
                        "stopReason": "end_turn", "modelUsage": {"grok-4.7": {"inputTokens": 10}}}
            return SimpleNamespace(stdout=json.dumps(envelope).encode(), stderr=b"", returncode=0)
        with patch("task.session_context.current_id", return_value="review-stream"), patch.object(review, "_invoke", side_effect=provider_call):
            result = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")
            self.assertEqual(result["action"], "accept-candidate")
        attempt = self.plan / "artifacts/P1.1/owner-review/attempt-0001"
        self.assertTrue((attempt / "provider-output.json").is_file())

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
        def provider_call(argv, **kwargs):
            session = argv[argv.index("--session-id") + 1]
            sessions.append(session)
            self.assertNotEqual(session, "executor")
            envelope = {"text": json.dumps(self.verdict(manifest)), "sessionId": session,
                        "stopReason": "end_turn", "modelUsage": {"grok-4.7": {}}}
            return SimpleNamespace(stdout=json.dumps(envelope).encode(), stderr=b"", returncode=0)
        with patch("task.session_context.current_id", return_value="executor"), patch.object(review, "_invoke", side_effect=provider_call):
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
        def provider_call(argv, **kwargs):
            manifest = json.loads(Path(argv[argv.index("--prompt-file") + 1]).with_name("review-route.json").read_text())
            calls.append(manifest["candidate_sha256"])
            findings = [self.finding(risk="local")] if len(calls) == 1 else None
            envelope = {"text": json.dumps(self.verdict(manifest, findings)),
                        "sessionId": argv[argv.index("--session-id") + 1],
                        "stopReason": "end_turn", "modelUsage": {"grok-4.7": {}}}
            return SimpleNamespace(stdout=json.dumps(envelope).encode(), stderr=b"", returncode=0)
        with patch("task.session_context.current_id", return_value="executor"), patch.object(review, "_invoke", side_effect=provider_call):
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
            def invoke(argv, **kwargs):
                if kind == "timeout":
                    raise subprocess.TimeoutExpired(argv, 1, output=b"partial", stderr=b"tool denied")
                if kind == "malformed":
                    return SimpleNamespace(stdout=b"not json", stderr=b"", returncode=0)
                session = argv[argv.index("--session-id") + 1]
                envelope = {"text": json.dumps(self.verdict(manifest)), "sessionId": session,
                            "stopReason": "cancelled" if kind == "cancelled" else "end_turn",
                            "modelUsage": {"grok-4.6" if kind == "wrong-model" else "grok-4.7": {}}}
                return SimpleNamespace(stdout=json.dumps(envelope).encode(), stderr=b"", returncode=0)
            with patch("task.session_context.current_id", return_value="review-stream"), patch.object(review, "_invoke", side_effect=invoke):
                receipt = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7", timeout=1)
            self.assertEqual(receipt["status"], "incomplete", kind)
            with self.assertRaisesRegex(review.ReviewError, "OWNER_REVIEW_PENDING"):
                review.require_green(self.plan, "P1.1", "grok/grok-4.7")

    def test_candidate_changed_during_review_archives_incomplete_output(self):
        packet = self.packet()
        manifest = self.manifest(packet)
        def invoke(argv, **kwargs):
            session = argv[argv.index("--session-id") + 1]
            self.product.write_text("changed = True\n")
            return SimpleNamespace(stdout=json.dumps({"text": json.dumps(self.verdict(manifest)),
                                   "sessionId": session, "stopReason": "end_turn",
                                   "modelUsage": {"grok-4.7": {"inputTokens": 10}}}).encode(), stderr=b"", returncode=0)
        with patch("task.session_context.current_id", return_value="review-stream"), patch.object(review, "_invoke", side_effect=invoke):
            receipt = review.run(self.plan, packet["manifest"], selector="grok/grok-4.7")
        self.assertEqual(receipt["status"], "incomplete")
        self.assertIn("REVIEW_CANDIDATE_STALE", receipt["detail"])
        self.assertTrue((self.plan / "artifacts/P1.1/owner-review/attempt-0001/provider-output.json").is_file())

    def test_path_escape_and_self_invalidating_candidate_are_refused(self):
        for relative in ("../outside", "plans/REVIEW/artifacts/P1.1/owner-review"):
            with self.assertRaises(review.ReviewError):
                self.packet(paths=[relative])

    def test_review_invocation_requires_one_explicit_selection(self):
        for invocation in ("task:review diff", "task:plan-audit REVIEW design", "task:review diff --reviewer grok/grok-4.7 --reviewer codex/gpt-6"):
            with self.assertRaisesRegex(review.ReviewError, "REVIEWER_REQUIRED"):
                review.invocation_selection(invocation)
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


if __name__ == "__main__":
    unittest.main()
