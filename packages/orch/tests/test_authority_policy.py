"""P6.3 authority regressions: fake probes/providers and synthetic streams; no live provider calls."""
from __future__ import annotations

import json
import importlib.util
import fnmatch
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from orch import launch
from orch.conductor import observer, process, records
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import launch_plan, results, sessions
from orch.conductor.policies import authority, routing
from orch.settings import ORCH_ROOT
from tests.test_authority_envelope import DOWN, UP, Matrix, probed_flags
from tests.test_conductor import ConductorCase, GREEN, executor_ok


class AuthorityPolicyTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.matrix = Matrix(Path(tmp.name))
        self.flags = probed_flags()
        self.flags.__enter__()
        self.addCleanup(self.flags.close)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.matrix.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.catalog = launch.load_catalog()

    def planned(self, role="executor", access="open", probe=UP, project=None):
        owner, item = self.matrix.owner(access), self.matrix.item()
        if project is not None:
            owner.project = Path(project)
        scratch = self.matrix.base / "agent" / "tmp"
        scratch.mkdir(parents=True, exist_ok=True)
        owner._local = types.SimpleNamespace(agent={"directory": scratch.parent})
        route = self.matrix.route(self.catalog, role, "claude-code", access)
        route["argv"] = [arg.replace(str(self.matrix.project), str(owner.project)) for arg in route["argv"]]
        with mock.patch("orch.sandbox.probe", return_value=probe):
            doc = launch_plan.authority(owner, item, role, route)
            argv = owner._role_argv(item, role, route, envelope=doc)
            env = launch_plan.role_env(owner, item, role, route)
        return owner, item, route, doc, argv, env

    def test_a_open_writer_keeps_landlock_with_network_and_docker(self):
        _, _, _, doc, argv, env = self.planned()
        self.assertEqual(doc["guard"], "landlock-rw")
        self.assertEqual((doc["network"]["effective"], doc["docker"]), ("open", "open"))
        self.assertNotIn("sandbox", json.loads(argv[argv.index("--settings") + 1]))
        self.assertIn("Bash(git push*)", json.loads(argv[-1])["permissions"]["deny"])
        self.assertIn(env["TMPDIR"], argv[:argv.index("--")])
        self.assertIn(["--add-dir", env["TMPDIR"]], [argv[i:i+2] for i in range(len(argv)-1)])
        self.assertIn({"path": env["TMPDIR"], "why": "tmpdir"}, doc["write_roots"])

    def test_b_confined_writer_keeps_the_provider_sandbox(self):
        _, _, _, doc, argv, env = self.planned(access="confined")
        self.assertEqual(doc["guard"], "claude-sandbox")
        self.assertFalse(any(arg.endswith("ro-run.py") for arg in argv[:2]))
        settings = json.loads(argv[argv.index("--settings") + 1])
        self.assertTrue(settings["sandbox"]["enabled"])
        self.assertIn(env["TMPDIR"], settings["sandbox"]["filesystem"]["allowWrite"])
        self.assertEqual((doc["network"]["effective"], doc["docker"]), ("none", "blocked"))

    def test_open_writer_does_not_require_an_unavailable_provider_sandbox(self):
        owner, item, route, _, _, _ = self.planned(probe=DOWN)
        item.options["instructions"]["sandbox"] = "require"
        with mock.patch("orch.sandbox.probe", side_effect=AssertionError("open must not probe bwrap")):
            self.assertIsNone(owner._claude_sandbox_problem(item, route))
            doc = owner._authority(item, "executor", route)
        self.assertEqual(doc["guard"], "landlock-rw")
        self.assertNotIn("SANDBOX_UNAVAILABLE", [entry["code"] for entry in doc["degraded"]])

    def test_open_authority_refuses_the_exact_secret_read_probe_but_allows_normal_reads(self):
        _, _, _, doc, _, _ = self.planned()
        patterns = [rule[5:-1] for rule in doc["permission_rules"]["deny"] if rule.startswith("Bash(")]
        self.assertTrue(any(fnmatch.fnmatchcase("cat .env", pattern) for pattern in patterns))
        self.assertTrue(any(fnmatch.fnmatchcase("cat .env.local", pattern) for pattern in patterns))
        self.assertFalse(any(fnmatch.fnmatchcase("cat README.md", pattern) for pattern in patterns))

    def test_c_read_only_guard_does_not_depend_on_the_provider_sandbox(self):
        for role in ("reviewer", "triager", "researcher", "advisor", "context-scout"):
            for probe in (UP, DOWN):
                with self.subTest(role=role, probe=probe):
                    catalog_role = "scout" if role == "context-scout" else role
                    # The route role and the manifest role differ only for context-scout.
                    if catalog_role == "scout":
                        self.catalog["launch"][role] = self.catalog["launch"][catalog_role]
                    _, _, _, doc, argv, _ = self.planned(role, probe=probe)
                    self.assertEqual(doc["guard"], "landlock-protect")
                    self.assertIn("--protect", argv)
                    self.assertIn("--no-default-rw", argv)
                    self.assertNotIn("sandbox", json.loads(argv[argv.index("--settings") + 1]))
                    if role == "reviewer":
                        self.assertEqual(argv[argv.index("--permission-mode")+1], "acceptEdits")
                        self.assertEqual(argv[argv.index("--allowedTools")+1], "Bash")

    def test_c_real_children_cannot_write_checkout_but_can_write_agent_tmpdir(self):
        if launch_plan.landlock_abi() < 3:
            self.skipTest("requires Landlock ABI >= 3")
        from tests.test_ro_run import work_base
        normal = tempfile.TemporaryDirectory(dir=work_base())
        self.addCleanup(normal.cleanup)
        for project in (Path(normal.name), self.matrix.project):
            for probe in (UP, DOWN):
                for role in ("reviewer", "triager"):
                    with self.subTest(project=project, probe=probe, role=role):
                        _, _, _, doc, argv, env = self.planned(role, probe=probe, project=project)
                        code = ("from pathlib import Path; "
                                f"Path({str(project / 'probe')!r}).touch()")
                        prefix = argv[:argv.index("--")+1]
                        denied = subprocess.run(prefix + [sys.executable, "-I", "-c", code], env=env,
                                                capture_output=True, text=True)
                        self.assertNotEqual(denied.returncode, 0, denied.stderr)
                        self.assertIn("PermissionError", denied.stderr)
                        self.assertFalse((project / "probe").exists())
                        code = "from pathlib import Path; import os; Path(os.environ['TMPDIR'], 'ok').touch()"
                        allowed = subprocess.run(prefix + [sys.executable, "-I", "-c", code], env=env,
                                                 capture_output=True, text=True)
                        self.assertEqual(allowed.returncode, 0, allowed.stderr)
                        self.assertTrue(Path(env["TMPDIR"], "ok").exists())
                        if project == self.matrix.project:
                            sibling = self.matrix.base / "sibling"
                            denied = subprocess.run(prefix + [sys.executable, "-I", "-c",
                                                    f"from pathlib import Path; Path({str(sibling)!r}).touch()"],
                                                    capture_output=True, text=True)
                            self.assertNotEqual(denied.returncode, 0)
                            self.assertFalse(sibling.exists())
                            self.assertEqual([root["path"] for root in doc["write_roots"]],
                                             ["/dev", env["TMPDIR"]])

    def test_c_protection_unavailable_stops_before_the_process(self):
        for abi in (-1, 2):
            with mock.patch.object(launch_plan, "landlock_abi", return_value=abi), \
                    mock.patch.object(process, "run_role") as ran, self.assertRaises(Stop) as raised:
                self.planned("reviewer")
            self.assertEqual(raised.exception.code, "PROTECT_UNAVAILABLE")
            ran.assert_not_called()
        with mock.patch.object(launch_plan, "ORCH_ROOT", self.matrix.base / "missing"), \
                mock.patch.object(launch_plan, "writes", return_value=False), self.assertRaises(Stop) as raised:
            self.planned("triager")
        self.assertEqual(raised.exception.code, "PROTECT_UNAVAILABLE")

    def test_d_transcripts_are_narrow_and_previews_create_nothing(self):
        home = self.matrix.home
        project = "/srv/checkouts/team-alph/packages/swissknifeman"
        folder = launch_plan.transcripts_folder(project, home, persist=False)
        self.assertEqual(len(launch_plan.transcript_folder_name(project)), 47)
        self.assertFalse((home / ".claude").exists())
        self.assertEqual(launch_plan.transcripts_folder(project, home, persist=True), folder)
        self.assertTrue(Path(folder).is_dir())
        long = "/" + "d"*250
        self.assertIsNone(launch_plan.transcripts_folder(long, home))
        root = home / ".claude" / "projects"
        prefix = launch_plan.transcript_folder_name(long)[:200]
        candidate = root / (prefix + "-hash")
        candidate.mkdir()
        self.assertEqual(launch_plan.transcripts_folder(long, home), str(candidate))
        (root / (prefix + "-other")).mkdir()
        self.assertIsNone(launch_plan.transcripts_folder(long, home))
        owner, item = self.matrix.owner("open"), self.matrix.item()
        owner.project = Path(long)
        route = self.matrix.route(self.catalog, "executor", "claude-code", "open")
        self.assertFalse(sessions.shared_session(owner, item, "executor", route))
        argv = owner.role_argv(item, "executor", route)
        self.assertIn("--no-session-persistence", argv)
        self.assertNotIn(str(root), argv)
        self.assertEqual([call.kwargs["reason_code"] for call in owner.progress.emit.call_args_list],
                         ["SESSION_NOT_PERSISTABLE"])

    def test_e_agent_scratch_changes_do_not_discard_a_resumable_conversation(self):
        owner, item, route, first, _, _ = self.planned()
        identity = sessions.identity_inputs(owner, item, route)
        owner._local.agent = {"directory": self.matrix.base / "other-agent"}
        second = owner._authority(item, "executor", route)
        self.assertNotEqual(first["digest"], second["digest"])
        self.assertEqual(identity, sessions.identity_inputs(owner, item, route))

    def test_f_grok_homes_are_explicit_and_offline_roles_disable_web_search(self):
        for role, providers in self.catalog["launch"].items():
            if "grok" in providers:
                argv = providers["grok"]["argv"]
                self.assertIn(["--rw", "~/.grok"], [argv[i:i+2] for i in range(len(argv)-1)])
                if role in ("reviewer", "triager", "report-fixer", "scout"):
                    self.assertIn("--disable-web-search", argv)
        self.assertNotIn("~/.grok", authority.GUARD_DEFAULT_WRITABLE)

    def test_h_registrar_routes_fail_before_launch_when_the_workspace_is_unwritable(self):
        for provider, access in (("claude-code", "open"), ("claude-code", "confined"), ("codex", "confined")):
            route = {"role": "registrar", "provider": provider}
            self.assertTrue(routing.registrar_problem(route, project="/checkout", access=access).startswith(
                f"LAUNCH_REFUSED: registrar/{provider}: writes the plan workspace outside /checkout;"))
        self.assertIsNone(routing.registrar_problem({"role":"registrar", "provider":"codex"},
                                                    project="/checkout", access="open"))
        with self.assertRaises(Stop) as raised:
            self.planned("registrar")
        self.assertEqual(raised.exception.code, "LAUNCH_REFUSED")


class DenialTests(unittest.TestCase):
    def test_nested_repairs_emit_only_one_beacon_per_role_and_step(self):
        parent = {"role":"executor", "step":"executor.1", "env_denials":{"erofs":1}, "previous":None}
        for count in (1, 2):
            child = {"role":"report-fixer", "step":"executor.1", "previous":parent, "env_denials":{"network":count}}
            self.assertEqual(results.denial_beacons(child), [])
        self.assertEqual(results.denial_beacons(parent), [
            ("executor", "executor.1", {"erofs":1}), ("report-fixer", "executor.1", {"network":3})])
        self.assertEqual(parent["env_denials"], {"erofs":1})  # child results are counted separately by the observer

    def test_optional_record_fields_have_valid_and_negative_examples(self):
        for kind in ("agent-result", "observer-report"):
            for group, name in (("valid", "env-denials.json"), ("invalid", "minimum-env-denials.json")):
                path = ORCH_ROOT / "schemas/records/v1/examples" / group / kind / name
                doc = json.loads(path.read_text())
                if group == "valid":
                    records.check(doc, kind, path)
                else:
                    with self.assertRaises(Stop) as raised:
                        records.check(doc, kind, path)
                    self.assertEqual(raised.exception.code, "RECORD_INVALID")

    def test_i_synthetic_error_fixtures_and_successful_code_output(self):
        for path in (ORCH_ROOT / "tests" / "fixtures" / "denials").glob("*.jsonl"):
            with self.subTest(path=path):
                found = process.parse_stream("jsonl", path.read_text())["env_denials"]
                self.assertEqual(found, {} if path.stem == "negative" else {path.stem:1})

    def test_i_other_error_shapes_and_guard_context(self):
        for text, guard, expected in (("EACCES", "", "eacces"), ("LANDLOCK_FAILED: denied", "", "landlock"),
                                       ("Operation not permitted", "landlock-protect", "landlock"),
                                       ("src/module.py: Permission denied", "", "eacces"),
                                       (".env: Permission denied", "", "read_mask"),
                                       ("skills.json: Permission denied", "", "read_mask")):
            event = {"type":"tool_result", "is_error":True, "content":text}
            self.assertEqual(process.parse_stream("jsonl", json.dumps(event), guard=guard)["env_denials"], {expected:1})
            event["is_error"] = False
            self.assertEqual(process.parse_stream("jsonl", json.dumps(event), guard=guard)["env_denials"], {})
        self.assertEqual(process.parse_stream("text", "EACCES")["env_denials"], {})
        for event in ({"type":"assistant", "message":{"content":[{"type":"text", "text":"EACCES"}]}},
                      {"type":"assistant", "message":{"content":[{"type":"tool_result", "is_error":True,
                                                                       "content":"EACCES"}]}},
                      {"type":"result", "is_error":True, "result":"Read-only file system"},
                      {"type":"tool_result", "is_error":True, "content":"Operation not permitted"}):
            self.assertEqual(process.parse_stream("jsonl", json.dumps(event))["env_denials"], {})


class AuthorityProbeTests(unittest.TestCase):
    def test_live_probe_requires_tool_evidence_and_counts_permission_denials(self):
        spec = importlib.util.spec_from_file_location("isolation_probe", ORCH_ROOT / "scripts/isolation-probe.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        commands = {"env_read":"cat .env", "git_diff_stat":"git diff --stat"}
        events = [{"type":"assistant", "message":{"content":[
            {"type":"tool_use", "id":"r", "name":"Bash", "input":{"command":"cat .env"}},
            {"type":"tool_use", "id":"b", "name":"Bash", "input":{"command":"git diff --stat"}}]}},
                  {"type":"user", "message":{"content":[{"type":"tool_result", "tool_use_id":"b",
                                                              "is_error":False,"content":""}]}},
                  {"type":"result", "permission_denials":[{"tool_use_id":"r","tool_name":"Bash"}]}]
        self.assertEqual(module.authority_results("\n".join(map(json.dumps, events)), commands),
                         {"git_diff_stat":True,"env_read":False})
        with self.assertRaises(RuntimeError):
            module.authority_results(json.dumps({"type":"result","result":"all checks passed"}), commands)


class DenialRunTests(ConductorCase):
    def test_i_records_beacon_observer_and_old_new_resume(self):
        answer = executor_ok("W1")
        first = {"exit":3, "stream":[json.dumps({"type":"user", "message":{"content":[
            {"type":"tool_result", "is_error":True, "content":"Read-only file system"}]}})]}
        answer["stream"] = [json.dumps({"type":"user", "message":{"content":[
            {"type":"tool_result", "is_error":True, "content":"Could not resolve host"}]}})]
        self.script({"executor":[first, answer], "reviewer":[GREEN]})
        with mock.patch.object(process, "run_role", wraps=process.run_role) as launched:
            code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        agents = {}
        for call in launched.call_args_list:
            folder = Path(call.kwargs["agent_directory"])
            scratch = folder / "tmp"
            self.assertFalse(scratch.exists())
            self.assertEqual(call.kwargs["env"]["TMPDIR"], str(scratch))
            agents[folder] = scratch
            doc = json.loads(next((folder / "authority").glob("a*.json")).read_text())
            self.assertIn({"path":authority.tilde(str(scratch), str(self.home)), "why":"tmpdir"}, doc["write_roots"])
        self.assertEqual(len(agents), len(set(agents.values())))
        folder = self.run_dir(err)
        beacon = [row for row in self.lines(err) if row.get("reason_code") == "RESULT_ENV_DENIAL"]
        self.assertEqual(len(beacon), 1)
        self.assertIn("executor executor.1: erofs×1, network×1", beacon[0]["message"])
        found = observer.build(folder, self.project)
        self.assertEqual(found["refusals_by_source"], {"by_kind":{"erofs":1,"network":1},
                                                      "by_role":{"executor":{"erofs":1,"network":1}}})
        self.assertIn("## Refusals by source", observer.markdown(found))
        target = self.project.parent / "observer"
        observer.write_report(folder, self.project, target)
        self.assertEqual(records.read(target / "observer.json", "observer-report")["refusals_by_source"],
                         found["refusals_by_source"])
        self.assertEqual(self.conduct("resume", "--run", folder.name)[0], 0)
        for path in folder.glob("*/agents/*/result.json"):
            old = records.read(path, "agent-result")
            old.pop("env_denials", None)
            records.write(path, old, "agent-result")
        self.assertEqual(observer.build(folder, self.project)["refusals_by_source"]["by_kind"], {})
        self.assertEqual(self.conduct("resume", "--run", folder.name)[0], 0)
