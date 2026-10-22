"""The test transport preserves CLI results and process isolation; real source processes remain covered."""
import json
import os
import sys
from types import SimpleNamespace
from unittest import mock

from orch import cli as source_cli
from orch.conductor.infrastructure import work_source
from tests.test_conductor import ConductorCase, GREEN, executor_ok


class WorkSourceTransportTests(ConductorCase):
    def client(self):
        return SimpleNamespace(project=self.project, project_resolution=None, config_file=None, env=dict(os.environ))

    def test_claim_and_brief_match_the_subprocess_transport(self):
        client = self.client()
        claim = ("source", "claim", "--plan", "T", "--item", "W1", "--actor",
                 "claude-code/claude-sonnet-5-5/high", "--submission-id", "sub-transport-equivalence")
        first = work_source.run_orch(client, *claim)
        self.assertEqual(first[0], 0, first)
        with mock.patch.object(work_source, "ORCH_TRANSPORT", None):
            second = work_source.run_orch(client, *claim)
        self.assertEqual(first, second)
        run = first[1]["run_id"]
        brief = ("source", "brief", "--run", run)
        self.assertEqual(work_source.run_orch(client, *brief)[0], 0)
        first = work_source.run_orch(client, *brief)  # both transports observe the same cached brief
        with mock.patch.object(work_source, "ORCH_TRANSPORT", None):
            second = work_source.run_orch(client, *brief)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 0, first)

    def test_process_state_is_restored_on_success_exit_and_exception(self):
        before = dict(os.environ), os.getcwd(), sys.stdout, sys.stderr, work_source.ORCH_TRANSPORT
        for outcome in (None, SystemExit(7), RuntimeError("test failure")):
            with self.subTest(outcome=outcome):
                def main(argv, outcome=outcome):
                    self.assertEqual(argv, ["source", "claim"])
                    self.assertEqual(dict(os.environ), {"TRANSPORT_ONLY": "yes"})
                    self.assertEqual(os.getcwd(), str(self.home))
                    print('{"ok": true}')
                    print("diagnostic", file=sys.stderr)
                    os.environ["LEAK"] = "bad"
                    work_source.ORCH_TRANSPORT = None
                    if outcome:
                        raise outcome
                    return 0
                self.home.mkdir(exist_ok=True)
                with mock.patch.object(source_cli, "main", main):
                    call = lambda: work_source.inprocess_transport(["python", "orch.py", "source", "claim"],
                                                                  self.home, {"TRANSPORT_ONLY": "yes"})
                    if isinstance(outcome, RuntimeError):
                        with self.assertRaisesRegex(RuntimeError, "test failure"):
                            call()
                    else:
                        self.assertEqual(call(), (7 if outcome else 0, '{"ok": true}\n', 'diagnostic\n'))
                self.assertEqual((dict(os.environ), os.getcwd(), sys.stdout, sys.stderr, work_source.ORCH_TRANSPORT), before)

    def test_run_orch_preserves_invalid_json_and_strips_stderr(self):
        with mock.patch.object(work_source, "ORCH_TRANSPORT", return_value=(2, "not json", " error \n")):
            self.assertEqual(work_source.run_orch(self.client(), "source", "claim"), (2, None, "error"))

    def test_default_transport_keeps_subprocess_timeout_and_result_contract(self):
        completed = SimpleNamespace(returncode=0, stdout='{"op":"claim"}', stderr=" diagnostic\n")
        with mock.patch.object(work_source, "ORCH_TRANSPORT", None), \
                mock.patch.object(work_source, "run_with_timeout", return_value=completed) as run:
            client = self.client()
            self.assertEqual(work_source.run_orch(client, "source", "claim"), (0, {"op": "claim"}, "diagnostic"))
        self.assertEqual(run.call_args.kwargs["timeout"], 600)
        self.assertEqual(run.call_args.kwargs["cwd"], str(self.project))


class WorkSourceSubprocessTests(ConductorCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(work_source, "ORCH_TRANSPORT", None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_green_item_claims_briefs_registers_and_commits(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.source()["items"]["W1"]["status"], "done")
        self.assertEqual([c["ref"] for c in self.source()["commits"]], ["W1"])
        self.assertTrue({"claim", "brief", "register", "commit"} <= {c["op"] for c in self.source()["calls"]})

    def test_claim_refusal_stops_before_any_role_runs(self):
        self.set_items({"W1": {"depends_on": ["W2"]}, "W2": {}})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "CLAIM_BLOCKED")), err)
        self.assertEqual(self.calls("executor"), 0)

    def test_registration_replayed_after_interrupted_commit_is_a_no_op(self):
        self.set_items({"W1": {}}, refuse=["commit"])
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "COMMIT_REFUSED")), err)
        run_dir = self.run_dir(err)
        state_file = run_dir / "state.json"
        state = json.loads(state_file.read_text())
        del state["items"]["W1"]["steps"]["register"]
        state_file.write_text(json.dumps(state))
        code, _, err = self.conduct("resume", "--run", run_dir.name, "--json-lines")
        self.assertEqual(code, 0, err)
        self.assertEqual(len([c for c in self.source()["calls"] if c["op"] == "register"]), 2)
        self.assertIn("no-op", err)
        self.assertEqual(len(self.source()["commits"]), 1)
