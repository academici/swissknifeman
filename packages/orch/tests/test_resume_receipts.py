"""L11 receipt recovery, including SIGKILL at source-effect/receipt/done boundaries; no providers."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
from types import SimpleNamespace
from unittest import mock

from orch import adhoc, cli, journal, settings
from orch.conductor import engine, progress
from orch.conductor.domain.item import Item
from orch.conductor.infrastructure import work_source
from orch.conductor.infrastructure.files import read_json, write_json
from orch.worksource_file import FileWorkSource
from tests.test_conductor import ConductorCase, ROOT

BOOT = "import sys; sys.path[:0] = " + repr([str(ROOT), str(ROOT / "lib"), str(ROOT.parent / "aicore/lib")]) + "; "


def source(project, *args):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(["--project", str(project), *args])
    return code, json.loads(out.getvalue()) if out.getvalue().strip() else None, err.getvalue()


def opened(project, claim, directory=None):
    run = engine.Conductor(project=project, settings=settings.load(project=project), mode="quiet")
    if directory is None:
        run._open("cnd-receipts", {"items": [claim["ref"]]},
                  {"items": {claim["ref"]: {"steps": {}, "orch_run": claim["run_id"]}}, "claims": {}})
        run.store.create(run.run_doc)
    else:
        run._open(directory.name, read_json(directory / "run.json"), read_json(directory / "state.json"))
    run._orch = lambda *args: source(project, *args)
    item = Item(claim["ref"], claim["run_id"], run.state["items"][claim["ref"]], run.directory / "piece", claim)
    return run, item


def counted_register(original, source_, request):
    answer = original(source_, request)
    if answer["outcome"] == "recorded":
        counter = source_.project.parent / "register-effects"
        counter.write_text(str(int(counter.read_text()) + 1 if counter.exists() else 1))
    return answer


def crash_worker(config):
    config = json.loads(Path(config).read_text())
    project = Path(config["project"])
    run, item = opened(project, config["claim"])
    original_write, original_save = journal.write_doc, run._save
    kind, point = config["kind"], config["point"]
    if point == "started":
        item.state.update(outcome="blocked", steps={"executor.1": {"status": "done", "ended": "2026-10-19T00:00:00Z",
                          "result": {"report": {"status": "blocked"}}}})
        run._retry(item.ref)  # owner retry removes closing steps, retaining the work-source run and attempt

    def pause():
        os.write(1, b"ready\n")  # bypass the source CLI's captured stdout
        signal.pause()  # the parent kills only this conductor after reading the pipe

    def write(directory, name, doc):
        if point == "effect" and name == f"receipts/{'register' if kind == 'close' else kind}.json":
            pause()
        return original_write(directory, name, doc)

    def save():
        if point == "done" and item.state["steps"].get(kind, {}).get("status") == "done":
            pause()
        original_save()

    def action():
        if point == "started":
            pause()  # started is durable; the child source has not written a new request yet
        if kind == "commit":
            return work_source.commit(run, item, ["product.txt"])
        result = work_source.register(run, item, config["args"])
        return {"by": "closer", "answer": "registered"} if kind == "close" else result

    run._save = save
    original_register = FileWorkSource._register
    with mock.patch.object(journal, "write_doc", side_effect=write), \
            mock.patch.object(FileWorkSource, "_register", lambda s, r: counted_register(original_register, s, r)):
        run._step(item, kind, action)
    raise AssertionError("the worker missed its crash boundary")


def external_commit_worker(config, mode):
    """CLI fixture for bridge crash tests; the source is reached only through its stdio-json protocol."""
    config = json.loads(Path(config).read_text())
    project, fields = Path(config["project"]), config["fields"]
    run = engine.Conductor(project=project, settings=settings.load(project=project), mode="quiet")
    run_id = "cnd-split-receipts"
    directory = engine.runs_root(project) / run_id
    if mode != "crash":
        run._open(run_id, read_json(directory / "run.json"), read_json(directory / "state.json"))
    else:
        run._open(run_id, {}, {"items": {fields["ref"]: {"steps": {}, "orch_run": fields["run_id"]}}, "claims": {}})
        run.store.create(run.run_doc)
    item = Item(fields["ref"], fields["run_id"], run.state["items"][fields["ref"]], directory / "piece",
                {"attempt_id": fields["attempt_id"]})

    def invoke(**request):
        envelope = {"protocol": "1", "request_id": "receipt-test", "op": "invoke", "point": "orch:work-source",
                    "input": {"op": "commit", **request}}
        done = subprocess.run(config["source_argv"], input=json.dumps(envelope), capture_output=True, text=True,
                              cwd=project, check=True, timeout=30)
        answer = json.loads(done.stdout)
        assert answer["status"] == "ok", answer
        return answer["output"]

    def call(*args):
        answer = cli._source_effect(SimpleNamespace(commit=invoke), journal.run_dir(item.orch_run, project=project),
                                    "commit", **fields)
        if mode in ("crash", "resume-crash"):
            os.write(1, b"ready\n")
            signal.pause()  # kill only this conductor; the source processes have already exited
        return 0, answer, ""

    run._orch = call
    if mode == "crash":
        run._step(item, "commit", lambda: work_source.commit(run, item, fields["paths"]))
        raise AssertionError("the conductor missed its external receipt barrier")
    assert item.state["steps"]["commit"]["status"] == "started"
    run._reconcile_interrupted()
    message = [row["message"] for row in progress.read_lines(run.directory)
               if row.get("reason_code") == "STAGE_INTERRUPTED"][-1]
    with mock.patch.object(run, "_orch", wraps=run._orch) as call:
        result = run._step(item, "commit", lambda: work_source.commit(run, item, fields["paths"]))
    print(json.dumps({"message": message, "calls": call.call_count, "result": result}))


class ResumeReceiptTests(ConductorCase):
    def setUp(self):
        super().setUp()
        doc = adhoc.build_adhoc_input("Receipt recovery", ["product.txt"], checks=["V1=true"])
        self.input = self.project.parent / "input.json"
        self.input.write_text(json.dumps(doc))
        code, self.claim, err = source(self.project, "source", "claim", "--input", str(self.input), "--commit",
                                       "--actor", "orch/test", "--submission-id", "sub-receipts")
        self.assertEqual(0, code, err)
        self.receipts = journal.run_dir(self.claim["run_id"], project=self.project)
        self.report = self.project.parent / "report.json"
        self.report.write_text(json.dumps({"summary": "done", "open_issues": []}))
        evidence = self.project.parent / "evidence.json"
        evidence.write_text(json.dumps({"check_id": "V1", "exit": 0}))
        self.args = ["source", "register", "--run", self.claim["run_id"], "--report", str(self.report),
                     "--status", "done", "--actor", "orch/test", "--evidence", f"V1={evidence}"]
        (self.project / "product.txt").write_text("work\n")
        self.effects = self.project.parent / "register-effects"
        original = FileWorkSource._register
        patcher = mock.patch.object(FileWorkSource, "_register", lambda s, r: counted_register(original, s, r))
        patcher.start()
        self.addCleanup(patcher.stop)

    def interrupted(self, kind, point):
        config = self.project.parent / "crash.json"
        config.write_text(json.dumps({"project": str(self.project), "claim": self.claim,
                                      "args": self.args, "kind": kind, "point": point}))
        log = open(self.project.parent / "crash.log", "w+")
        self.addCleanup(log.close)
        child = subprocess.Popen([sys.executable, "-I", "-u", "-c", BOOT +
                                  "from tests.test_resume_receipts import crash_worker; crash_worker(sys.argv[1])",
                                  str(config)], cwd=self.project, env=os.environ.copy(), stdout=subprocess.PIPE, stderr=log,
                                 text=True)
        def cleanup():
            if child.poll() is None:
                child.kill()
            child.wait(timeout=15)
            child.stdout.close()
        self.addCleanup(cleanup)
        self.assertTrue(select.select([child.stdout], [], [], 30)[0], "conductor missed the receipt barrier")
        line = child.stdout.readline().strip()
        if line != "ready":
            log.seek(0)
            self.fail("worker exited before its barrier: " + log.read())
        child.kill()
        self.assertEqual(-signal.SIGKILL, child.wait(timeout=15))
        directory = engine.runs_root(self.project) / "cnd-receipts"
        run, item = opened(self.project, self.claim, directory)
        self.assertEqual("started", item.state["steps"][kind]["status"])
        run._reconcile_interrupted()
        return run, item

    def message(self, run):
        return [row["message"] for row in progress.read_lines(run.directory)
                if row.get("reason_code") == "STAGE_INTERRUPTED"][-1]

    def start(self, kind):
        run, item = opened(self.project, self.claim)
        run._start_step(item, kind)
        return run, item

    def publish(self, kind, answer):
        return cli._source_effect(SimpleNamespace(**{kind: lambda **fields: answer}), self.receipts, kind,
                                  run_id=self.claim["run_id"], ref=self.claim["ref"],
                                  attempt_id=self.claim["attempt_id"])

    def test_retry_crash_before_new_request_repeats_old_blocked_registration(self):
        args = list(self.args)
        args[args.index("--status") + 1] = "blocked"
        self.assertEqual(0, source(self.project, *args)[0])
        # Both attempts can start within one UTC second: freshness must include the state publication boundary.
        request_path = self.receipts / "receipts/register-request.json"
        request_before = request_path.read_bytes()
        for kind in ("register", "close"):
            with self.subTest(kind=kind):
                run, item = self.interrupted(kind, "started")
                self.assertEqual(request_before, request_path.read_bytes())
                self.assertEqual("repeated: receipt of another attempt", self.message(run))
                self.assertNotIn(kind, item.state["steps"])
        self.assertEqual("recorded", run._step(item, "register", lambda: work_source.register(run, item, self.args))["outcome"])
        self.assertEqual("2", self.effects.read_text())
        receipt = self.project / ".swissknifeman/orch-artifacts" / item.orch_run / item.ref / "register.json"
        self.assertEqual("done", json.loads(receipt.read_text())["status"])

    def test_split_commit_repeat_keeps_source_sha_in_live_and_recovered_results(self):
        run, item = self.start("commit")
        self.git("add", "product.txt")
        self.git("commit", "-q", "-m", "source part")
        source_sha = self.git("rev-parse", "HEAD").strip()
        workspace_sha = "b" * 40
        self.publish("commit", {"op": "commit", "outcome": "committed", "sha": source_sha,
                               "repo": "source", "attempt": item.claim["attempt_id"],
                               "workspace_commit": {"status": "failed"}})
        # Upgrade an existing request from before source_sha was retained; its receipt still proves that revision.
        request = journal.read_doc(self.receipts, "receipts/commit-request.json")
        request.pop("source_sha", None)
        journal.write_doc(self.receipts, "receipts/commit-request.json", request)
        run._reconcile_interrupted()
        self.assertEqual("repeated: workspace part incomplete", self.message(run))
        with mock.patch.object(cli, "_call", side_effect=RuntimeError("crash before repeated source answer")):
            with self.assertRaisesRegex(RuntimeError, "crash before repeated"):
                self.publish("commit", {})
        self.assertEqual(source_sha, journal.read_doc(self.receipts, "receipts/commit-request.json")["source_sha"])

        def repeat(*args):
            answer = self.publish("commit", {"op": "commit", "outcome": "committed", "sha": workspace_sha,
                                  "repo": "workspace", "attempt": item.claim["attempt_id"],
                                  "workspace_commit": {"status": "committed"}})
            return 0, answer, ""

        run._orch = repeat
        original_save = run._save

        def crash_before_done():
            if item.state["steps"]["commit"]["status"] == "done":
                self.assertEqual(source_sha, item.state["steps"]["commit"]["result"]["sha"])
                raise RuntimeError("crash after repeated commit receipt before done")
            original_save()

        run._save = crash_before_done
        with self.assertRaisesRegex(RuntimeError, "crash after repeated commit"):
            run._step(item, "commit", lambda: work_source.commit(run, item, ["product.txt"]))
        resumed, item = opened(self.project, self.claim, run.directory)
        resumed._reconcile_interrupted()
        self.assertEqual("closed from receipt", self.message(resumed))
        call = mock.Mock(side_effect=AssertionError("completed split commit repeated"))
        result = resumed._step(item, "commit", call)
        call.assert_not_called()
        self.assertEqual({"outcome": "committed", "sha": source_sha}, result)
        self.assertEqual("commit", self.git("cat-file", "-t", result["sha"]).strip())
        self.assertEqual(workspace_sha, journal.read_doc(self.receipts, "receipts/commit.json")["sha"])

    def test_workspace_only_commit_never_exposes_workspace_sha_as_product_sha(self):
        run, item = self.start("commit")
        answer = {"op": "commit", "outcome": "committed", "sha": "b" * 40, "repo": "workspace",
                  "attempt": item.claim["attempt_id"], "workspace_commit": {"status": "committed"}}
        self.publish("commit", answer)
        with mock.patch.object(run, "_orch", return_value=(0, answer, "")):
            result = work_source.commit(run, item, [])
        self.assertIsNone(result["sha"])
        self.assertIn(answer["sha"], result["message"])
        run._reconcile_interrupted()
        self.assertEqual(result, item.state["steps"]["commit"]["result"])

    def test_new_attempt_cannot_inherit_another_attempts_source_sha(self):
        run, item = self.start("commit")
        self.publish("commit", {"op": "commit", "outcome": "committed", "sha": "a" * 40,
                               "repo": "source", "attempt": item.claim["attempt_id"]})
        answer = {"op": "commit", "outcome": "committed", "sha": "b" * 40, "repo": "workspace",
                  "attempt": "att-new", "workspace_commit": {"status": "committed"}}
        cli._source_effect(SimpleNamespace(commit=lambda **fields: answer), self.receipts, "commit",
                           run_id=item.orch_run, ref=item.ref, attempt_id="att-new")
        self.assertNotIn("source_sha", journal.read_doc(self.receipts, "receipts/commit-request.json"))

    def test_crash_after_register_effect_before_receipt_repeats_without_second_registration(self):
        run, item = self.interrupted("register", "effect")
        self.assertEqual("repeated: receipt missing", self.message(run))
        result = run._step(item, "register", lambda: work_source.register(run, item, self.args))
        self.assertEqual({"outcome": "no-op", "gate": "pass"}, result)
        self.assertEqual("1", self.effects.read_text())

    def test_crash_after_register_receipt_before_done_closes_without_call(self):
        run, item = self.interrupted("register", "done")
        call = mock.Mock(side_effect=AssertionError("registration repeated"))
        self.assertEqual({"outcome": "recorded", "gate": "pass"}, run._step(item, "register", call))
        call.assert_not_called()
        self.assertEqual("closed from receipt", self.message(run))
        self.assertEqual("1", self.effects.read_text())

    def test_close_recovery_preserves_by_for_finish(self):
        run, item = self.interrupted("close", "done")
        call = mock.Mock(side_effect=AssertionError("registrar repeated"))
        self.assertEqual("closer", run._step(item, "close", call)["by"])
        call.assert_not_called()
        # finish still makes its idempotent register call after a successful closer.
        self.assertEqual("no-op", work_source.register(run, item, self.args)["outcome"])
        self.assertEqual("1", self.effects.read_text())

    def test_refused_receipt_repeats_instead_of_closing(self):
        run, item = self.start("register")
        source(self.project, *[arg for arg in self.args[:self.args.index("--evidence")]])
        self.assertEqual("refused", journal.read_doc(self.receipts, "receipts/register.json")["outcome"])
        run._reconcile_interrupted()
        self.assertEqual("repeated: receipt refused", self.message(run))
        self.assertNotIn("register", item.state["steps"])
        self.assertEqual("recorded", run._step(item, "register", lambda: work_source.register(run, item, self.args))["outcome"])

    def test_receipt_of_another_attempt_repeats(self):
        run, item = self.start("register")
        source(self.project, *self.args)
        item.state["steps"]["register"]["attempt"] = "att-another"
        run._reconcile_interrupted()
        self.assertEqual("repeated: receipt of another attempt", self.message(run))
        self.assertNotIn("register", item.state["steps"])
        self.assertEqual("no-op", run._step(item, "register", lambda: work_source.register(run, item, self.args))["outcome"])
        self.assertEqual("1", self.effects.read_text())

    def test_commit_crash_after_receipt_before_done_creates_one_commit(self):
        before = int(self.git("rev-list", "--count", "HEAD"))
        run, item = self.interrupted("commit", "done")
        call = mock.Mock(side_effect=AssertionError("commit repeated"))
        result = run._step(item, "commit", call)
        call.assert_not_called()
        self.assertEqual({"outcome": "committed", "sha": self.git("rev-parse", "HEAD").strip()}, result)
        self.assertEqual(before + 1, int(self.git("rev-list", "--count", "HEAD")))

    def test_commit_crash_before_receipt_repeats_without_second_commit(self):
        before = int(self.git("rev-list", "--count", "HEAD"))
        run, item = self.interrupted("commit", "effect")
        self.assertEqual("repeated: receipt missing", self.message(run))
        result = run._step(item, "commit", lambda: work_source.commit(run, item, ["product.txt"]))
        self.assertEqual("no-op", result["outcome"])
        self.assertEqual(before + 1, int(self.git("rev-list", "--count", "HEAD")))

    def test_file_commit_answers_bind_success_repeat_and_refusal_to_attempt(self):
        args = ["source", "commit", "--run", self.claim["run_id"], "--path", "product.txt"]
        before = int(self.git("rev-list", "--count", "HEAD"))
        for outcome in ("committed", "no-op"):
            code, answer, err = source(self.project, *args)
            self.assertEqual(0, code, err)
            self.assertEqual((outcome, self.claim["attempt_id"]), (answer["outcome"], answer["attempt"]))
        self.assertEqual(before + 1, int(self.git("rev-list", "--count", "HEAD")))
        (self.project / "product.txt").write_text("more work\n")
        hook = self.project / ".git/hooks/pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        code, answer, _ = source(self.project, *args)
        self.assertEqual(1, code)
        self.assertEqual(("refused", self.claim["attempt_id"]), (answer["outcome"], answer["attempt"]))
        self.assertEqual(before + 1, int(self.git("rev-list", "--count", "HEAD")))

    def test_malformed_canonical_result_fields_never_close(self):
        cases = [("commit", {"sha": value}) for value in (None, 7, "not-a-sha")]
        cases += [("commit", {"message": value}) for value in (7, {}, "")]
        cases += [("register", {"gate": {"verdict": "pass", "checks": {"V1": True}}})]
        for kind, fields in cases:
            with self.subTest(kind=kind, fields=fields):
                run, item = self.start(kind)
                answer = {"op": kind, "outcome": "committed" if kind == "commit" else "recorded",
                          "receipt": {"attempt_id": item.claim["attempt_id"]}, **fields}
                if kind == "commit":
                    answer.pop("receipt")
                    answer["attempt"] = item.claim["attempt_id"]
                journal.write_doc(self.receipts, f"receipts/{kind}.json", answer)
                run._reconcile_interrupted()
                self.assertEqual("repeated: receipt missing", self.message(run))
                self.assertNotIn(kind, item.state["steps"])

    def test_workspace_incomplete_including_nothing_repeats_and_keeps_result_shape(self):
        for status in ("failed", "locked", "nothing", None):
            with self.subTest(status=status):
                run, item = self.start("commit")
                answer = {"op": "commit", "outcome": "committed", "attempt": item.claim["attempt_id"],
                          "sha": "a" * 40, "repo": "source"}
                if status:
                    answer["workspace_commit"] = {"status": status}
                self.publish("commit", answer)
                run._reconcile_interrupted()
                self.assertEqual("repeated: workspace part incomplete", self.message(run))
                complete = dict(answer, workspace_commit={"status": "committed"}, message="workspace finished")
                with mock.patch.object(run, "_orch", return_value=(0, complete, "")) as call:
                    result = run._step(item, "commit", lambda: work_source.commit(run, item, ["product.txt"]))
                call.assert_called_once()
                self.assertEqual({"outcome": "committed", "sha": "a" * 40, "message": "workspace finished"}, result)

    def test_attempt_conflict_stops_registration_without_done(self):
        run, item = self.start("register")
        self.assertEqual(0, source(self.project, *self.args)[0])
        journal.write_doc(self.receipts, "receipts/register.json", {"op": "register", "outcome": "refused",
                          "gate": {"verdict": "none", "checks": {}}, "reason_code": "ATTEMPT_CONFLICT"})
        run._reconcile_interrupted()
        args = list(self.args)
        args[args.index("--status") + 1] = "blocked"
        with self.assertRaises(engine.Stop) as caught:
            run._step(item, "register", lambda: work_source.register(run, item, args))
        self.assertEqual("REGISTER_REFUSED", caught.exception.code)
        self.assertIn("ATTEMPT_CONFLICT", caught.exception.message)
        self.assertEqual("stopped", item.state["steps"]["register"]["status"])
        self.assertEqual("1", self.effects.read_text())

    def test_legacy_commit_receipt_needs_request_and_both_digests(self):
        run, item = self.start("commit")
        self.assertEqual(0, source(self.project, "source", "commit", "--run", item.orch_run, "--path", "product.txt")[0])
        answer = journal.read_doc(self.receipts, "receipts/commit.json")
        answer.pop("attempt")
        request = journal.read_doc(self.receipts, "receipts/commit-request.json")
        from aicore.util.digest import canonical_json_bytes, sha256_hex
        request["receipt_digest"] = sha256_hex(canonical_json_bytes(answer))
        journal.write_doc(self.receipts, "receipts/commit.json", answer)
        journal.write_doc(self.receipts, "receipts/commit-request.json", request)
        self.assertTrue(work_source.receipt_closes("commit", work_source.read_receipt(item, "commit", project=self.project), item)[0])
        for damaged in (dict(request, digest="bad"), dict(request, receipt_digest="bad"), {},
                        dict(request, attempt_id="att-stale")):
            journal.write_doc(self.receipts, "receipts/commit-request.json", damaged)
            self.assertFalse(work_source.receipt_closes("commit", work_source.read_receipt(item, "commit", project=self.project), item)[0])

    def test_missing_corrupt_receipts_and_item_folder_receipts_never_close(self):
        run, item = self.start("register")
        write_json(item.directory / "receipts/register.json", {"op": "register", "outcome": "recorded"})
        for content in (None, "{broken", "[]", '{"op":"register","outcome":"recorded","gate":null}',
                        json.dumps({"op": "register", "outcome": "recorded", "receipt": ["broken"],
                                    "gate": {"verdict": "pass", "checks": {}}})):
            with self.subTest(content=content):
                if content is not None:
                    path = self.receipts / "receipts/register.json"
                    path.parent.mkdir(exist_ok=True)
                    path.write_text(content)
                self.assertFalse(work_source.receipt_closes("register", work_source.read_receipt(item, "register", project=self.project), item)[0])

    def test_new_request_cannot_reuse_old_receipt_without_attempt(self):
        run, item = self.start("register")
        self.assertEqual(0, source(self.project, *self.args)[0])
        with mock.patch.object(cli, "_call", side_effect=RuntimeError("interrupted before source answer")):
            with self.assertRaises(RuntimeError):
                source(self.project, *self.args)
        run._reconcile_interrupted()
        self.assertEqual("repeated: receipt missing", self.message(run))
        self.assertEqual("no-op", run._step(item, "register", lambda: work_source.register(run, item, self.args))["outcome"])
        self.assertEqual("1", self.effects.read_text())

    def test_new_commit_request_cannot_reuse_old_receipt_with_explicit_attempt(self):
        run, item = self.start("commit")
        args = ["source", "commit", "--run", item.orch_run, "--path", "product.txt"]
        self.assertEqual(0, source(self.project, *args)[0])
        with mock.patch.object(cli, "_call", side_effect=RuntimeError("interrupted before source answer")):
            with self.assertRaises(RuntimeError):
                source(self.project, *args)
        run._reconcile_interrupted()
        self.assertEqual("repeated: receipt missing", self.message(run))
        self.assertNotIn("commit", item.state["steps"])

    def test_successful_workspace_receipts_close_and_wrong_commit_attempt_repeats(self):
        for status in ("committed", "no-op", "skipped-legacy", "skipped-no-git"):
            with self.subTest(status=status):
                run, item = self.start("commit")
                answer = {"op": "commit", "outcome": "no-op", "attempt": item.claim["attempt_id"],
                          "workspace_commit": {"status": status}}
                self.publish("commit", answer)
                run._reconcile_interrupted()
                call = mock.Mock(side_effect=AssertionError("completed workspace repeated"))
                self.assertEqual({"outcome": "no-op", "sha": None}, run._step(item, "commit", call))
                call.assert_not_called()
        run, item = self.start("commit")
        answer["attempt"] = "att-other"
        self.publish("commit", answer)
        run._reconcile_interrupted()
        self.assertEqual("repeated: receipt of another attempt", self.message(run))
        self.assertNotIn("commit", item.state["steps"])

    def test_workspace_plan_requires_completion_but_file_input_in_same_project_does_not(self):
        run, item = self.start("commit")
        marker = self.project / ".swissknifeman/project.json"
        marker.write_text(json.dumps({"$schema": "urn:swissknifeman:aicore:project-marker:v1", "workspace": "test",
                                      "project_id": "test", "plans_store": "workspace"}))
        answer = {"op": "commit", "outcome": "no-op", "attempt": item.claim["attempt_id"]}
        self.publish("commit", answer)
        # The actual file source does not have a plan in the workspace.
        self.assertTrue(work_source.receipt_closes("commit", work_source.read_receipt(item, "commit", project=self.project), item)[0])
        run_doc = journal.read_doc(self.receipts, "run.json")
        run_doc.pop("source")
        journal.write_doc(self.receipts, "run.json", run_doc)
        self.assertEqual((False, "repeated: workspace part incomplete"),
                         work_source.receipt_closes("commit", work_source.read_receipt(item, "commit", project=self.project), item))
        marker.write_text("{broken")
        self.assertIsNone(work_source.read_receipt(item, "commit", project=self.project))

    def test_live_incomplete_commit_stops_without_false_done(self):
        run, item = self.start("commit")
        with mock.patch.object(run, "_orch", return_value=(0, {"outcome": "committed", "sha": "a" * 40,
                               "workspace_commit": {"status": "failed"}}, "")):
            with self.assertRaises(engine.Stop) as caught:
                run._step(item, "commit", lambda: work_source.commit(run, item, ["product.txt"]))
        self.assertEqual("COMMIT_REFUSED", caught.exception.code)
        self.assertEqual("stopped", item.state["steps"]["commit"]["status"])
