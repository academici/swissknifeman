"""The isolation profiles of the providers (P6.1, knowledge/p6-design#p6-1-isolation): the profiles file and its schema,
the plan of an isolated role (arguments, environment, homes, guarantee), ``instructions.isolation`` (off, prefer,
require), the flag probe with the help command of the profile, the init event of the stream (ISOLATION_DRIFT), the
CODEX_HOME of a Codex role and the probe script. Fake CLIs and a temporary HOME only; no real provider is started."""
from __future__ import annotations

import contextlib
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from aicore.state import locations

from orch.conductor import agents, contract, engine, options as opts, process, records
from orch.conductor.application import review_plan, route_service
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import cli_probe, launch_plan
from orch.conductor.policies import isolation
from tests.test_conductor import FIXTURES, GREEN, ROLES, ROOT, ConductorCase, executor_ok, report

SHIPPED = ROOT / "fixtures" / "conductor" / "v1" / "valid" / "isolation-profiles" / "shipped.json"
GROK_STREAM = ROOT / "tests" / "fixtures" / "grok" / "streaming-messages-json.jsonl"
PROBE = ROOT / "scripts" / "isolation-probe.py"
# A provider CLI stand-in: ``--version`` and ``... --help`` answer from the environment of the test; ``debug
# prompt-input`` renders ``FAKE_CLI_RENDER`` (``ok``: a message with the prompt, ``agents``: also the AGENTS.md of the
# cwd, anything else is printed as it is); ``inspect`` prints ``FAKE_CLI_INSPECT``. Any other call plays the role with
# fake_role.py. Every call is logged, and the role and inspect calls log their environment.
FAKE_CLI = """#!{python}
import json, os, sys
args, name = sys.argv[1:], os.path.basename(sys.argv[0])
with open(os.environ["FAKE_CLI_LOG"], "a") as out:
    out.write(json.dumps([name, *args]) + "\\n")
if args == ["--version"]:
    print(os.environ.get("FAKE_CLI_VERSION", name + " 9.9.9"))
    sys.exit(0)
if args and args[-1] == "--help":
    print(os.environ.get("FAKE_CLI_HELP_" + name.upper(), ""))
    sys.exit(0)
if args[:2] == ["debug", "prompt-input"]:
    mode = os.environ.get("FAKE_CLI_RENDER", "ok")
    if mode in ("ok", "agents"):
        text = args[-1] + ("\\n" + open("AGENTS.md").read() if mode == "agents" else "")
        print(json.dumps([{{"type": "message", "role": "user", "content": [{{"type": "input_text", "text": text}}]}}]))
    else:
        print(mode)
    sys.exit(0)
with open(os.environ["FAKE_CLI_ENV"], "a") as out:
    out.write(json.dumps({{key: os.environ.get(key) for key in ("HOME", "CODEX_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME",
                                                             "GROK_HOME", "CLAUDE_CODE_DISABLE_CLAUDE_MDS")}}) + "\\n")
if args[:1] == ["inspect"]:
    print(os.environ.get("FAKE_CLI_INSPECT", '{{"rules": [], "skills": []}}'))
    sys.exit(0)
os.execv(sys.executable, [sys.executable, {fake_role!r}, *args])
"""


def profiles() -> dict:
    return copy.deepcopy(isolation.load_profiles())


def route(provider: str, argv=None) -> dict:
    return {"provider": provider, "argv": argv or [sys.executable, "fake_role.py"]}


class ProfilesFileTests(unittest.TestCase):
    def test_the_shipped_profiles_are_valid_and_the_fixture_is_the_shipped_file(self):
        doc = json.loads(isolation.PROFILES_PATH.read_text(encoding="utf-8"))
        self.assertEqual(contract.problems(doc, "isolation-profiles"), [])
        self.assertEqual(isolation.profile_problems(doc), [])
        self.assertEqual(json.loads(SHIPPED.read_text(encoding="utf-8")), doc)
        self.assertEqual(sorted(isolation.load_profiles()), ["claude-code", "codex", "grok"])

    def test_i_a_damaged_profiles_file_is_a_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "isolation-profiles.json"
            for text, said in (("{", "Expecting property name"),
                               (json.dumps({**json.loads(SHIPPED.read_text()), "profiles_version": "one"}),
                                "/profiles_version")):
                path.write_text(text, encoding="utf-8")
                with self.subTest(said), self.assertRaises(Stop) as stop:
                    isolation.load_profiles(path)
                self.assertEqual(stop.exception.code, "ISOLATION_PROFILES_INVALID")
                self.assertTrue(stop.exception.message.startswith(f"{path}: "), stop.exception.message)
                self.assertIn(said, stop.exception.message)

    def test_a_declared_guarantee_must_agree_with_the_surfaces(self):
        doc = json.loads(SHIPPED.read_text(encoding="utf-8"))
        doc["providers"]["claude-code"]["surfaces"]["hooks"] = "on"
        doc["providers"]["codex"]["surfaces"].update(repository_instructions="off", user_skills="off")
        self.assertEqual(isolation.profile_problems(doc), [
            "/providers/claude-code/guarantee: full, but hooks is not off",
            "/providers/codex/guarantee: partial, but every required surface is off"])


class PlanTests(unittest.TestCase):
    """The pure plan: what an isolated role gets, and what require refuses."""
    LISTED = {"listed": {"--safe-mode": True, "--strict-mcp-config": True, "--ignore-user-config": True}}

    def plan(self, provider: str, mode: str = "prefer", isolated: bool = True, probe=None, **extra) -> dict:
        return isolation.plan("executor", route(provider), isolated=isolated, mode=mode,
                              profile=profiles().get(provider), probe=self.LISTED if probe is None else probe, **extra)

    def test_a_claude_code_role_is_isolated_fully_and_a_role_not_isolated_gets_nothing(self):
        found = self.plan("claude-code")
        self.assertEqual((found["guarantee"], found["args"], found["home"]),
                         ("full", ["--safe-mode", "--strict-mcp-config"], None))
        self.assertEqual(found["env"], {"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1", "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"})
        self.assertIsNone(isolation.problem(self.plan("claude-code", "require")))
        for off in (self.plan("claude-code", isolated=False), self.plan("claude-code", "off")):
            self.assertEqual((off["guarantee"], off["args"], off["env"], off["home"]), ("none", [], {}, None))
            self.assertIsNone(isolation.problem(off))

    def test_a_flag_the_cli_does_not_list_is_left_out_and_lowers_the_guarantee(self):
        found = self.plan("claude-code", probe={"listed": {"--strict-mcp-config": True}})
        self.assertEqual((found["guarantee"], found["args"], found["missing"]),
                         ("partial", ["--strict-mcp-config"], ["--safe-mode"]))
        self.assertEqual(isolation.problem(dict(found, mode="require")),
                         "ISOLATION_UNAVAILABLE: executor/claude-code: partial isolation (the CLI does not list "
                         "--safe-mode); set instructions.isolation = prefer in a trusted layer or remove the role "
                         "from isolate_roles")
        self.assertEqual(isolation.partial_notes(found), [])  # the flag probe says the missing flag itself

    def test_e_codex_is_partial_until_a_live_probe_of_its_version_confirms_the_canaries(self):
        found = self.plan("codex", "require")
        self.assertEqual((found["guarantee"], found["unconfirmed"]), ("partial", ["repository_instructions", "user_skills"]))
        self.assertEqual(found["args"], ["--ignore-user-config", "-c", "project_doc_max_bytes=0"])
        self.assertEqual(found["home"]["vars"], {"CODEX_HOME": "codex-home", "HOME": "codex-user-home"})
        self.assertIn("repository_instructions canary, user_skills unknown", isolation.problem(found))
        probes = [{"provider": "codex", "version": "codex-cli 1.0", "claims": {"repository_instructions": False,
                                                                                "user_skills": False}}]
        for version, guarantee in (("codex-cli 1.0", "full"), ("codex-cli 1.1", "partial"), (None, "partial")):
            confirmed = isolation.confirmed(probes, "codex", version)
            with self.subTest(version):
                self.assertEqual(self.plan("codex", "require", probe={**self.LISTED, "confirmed": confirmed})["guarantee"],
                                 guarantee)
        loaded = [{**probes[0], "claims": {"repository_instructions": True, "user_skills": False}}]
        self.assertEqual(isolation.confirmed(loaded, "codex", "codex-cli 1.0"), ["user_skills"])

    def test_f_grok_under_require_is_refused_with_the_way_out(self):
        problem = isolation.problem(self.plan("grok", "require"))
        self.assertTrue(problem.startswith("ISOLATION_UNAVAILABLE: executor/grok: partial isolation ("), problem)
        self.assertTrue(problem.endswith("set instructions.isolation = prefer in a trusted layer or remove the role from "
                                         "isolate_roles"), problem)
        self.assertEqual([code for code, _ in isolation.partial_notes(self.plan("grok"))], ["SURFACES_UNCONFIRMED"])

    def test_a_drift_or_an_unreadable_help_lowers_a_full_guarantee(self):
        self.assertEqual(self.plan("claude-code", probe={**self.LISTED, "drift": True})["guarantee"], "partial")
        failed = self.plan("claude-code", probe={"listed": {}, "failed": True})
        self.assertEqual([entry["code"] for entry in failed["degraded"]], ["PROBE_FAILED", "FLAG_MISSING"])
        self.assertIn("PROFILE_MISSING", json.dumps(isolation.plan("executor", route("other"), isolated=True,
                                                                   mode="require", profile=None)))

    def test_a_route_whose_command_cannot_be_probed_is_never_full(self):
        """F3: a wrapper (/opt/claude-wrapper) gets the flags as asked, but they are not confirmed."""
        found = self.plan("claude-code", probe={**self.LISTED, "unprobed": True})
        self.assertEqual((found["guarantee"], found["args"]), ("partial", ["--safe-mode", "--strict-mcp-config"]))
        self.assertEqual([entry["code"] for entry in found["degraded"]], ["PROBE_UNAVAILABLE"])
        self.assertIn("the command of the route is not a provider CLI the profile can probe",
                      isolation.problem(dict(found, mode="require")))
        self.assertEqual([code for code, _ in isolation.partial_notes(found)], ["PROBE_UNAVAILABLE"])

    def test_the_auth_mode_of_the_configuration_replaces_the_one_of_the_profile(self):
        self.assertEqual(self.plan("codex")["home"]["mode"], "link")
        self.assertEqual(self.plan("codex", auth="copy")["home"]["mode"], "copy")

    def test_drift_names_the_fields_the_profile_wants_empty(self):
        init = {"tools": ["read_file"], "mcp_servers": ["kb-server"], "skills": [], "plugins": ["p"], "slash_commands": []}
        self.assertEqual(isolation.drift(profiles()["grok"], init), [("mcp_servers", ["kb-server"])])
        self.assertEqual(isolation.drift(profiles()["claude-code"], init), [("mcp_servers", ["kb-server"]), ("plugins", ["p"])])
        self.assertEqual(isolation.drift(profiles()["codex"], init), [])  # codex has no init event to watch

    def test_the_home_of_the_provider_is_the_first_variable_of_the_profile(self):
        self.assertEqual(isolation.home_dir(self.plan("codex"), Path("/run")), "/run/isolation/codex-home")
        self.assertEqual(isolation.home_dir(self.plan("claude-code"), Path("/run")), "")


class InitEventTests(unittest.TestCase):
    def test_h_the_names_of_the_first_init_event_are_kept(self):
        parsed = process.parse_stream("jsonl", GROK_STREAM.read_text(encoding="utf-8"))
        self.assertEqual(sorted(parsed["init"]), ["mcp_servers", "plugins", "skills", "slash_commands", "tools"])
        self.assertIn("read_file", parsed["init"]["tools"])
        stream = "\n".join(json.dumps(doc) for doc in (
            {"type": "system", "subtype": "init", "session_id": "s", "mcp_servers": [{"name": "kb-server", "status": "ok"}],
             "plugins": [{"name": "p", "path": "/x"}], "tools": ["Read"]},
            {"type": "system", "subtype": "init", "mcp_servers": ["other"]},
            {"type": "result", "result": "ok", "usage": {"input_tokens": 1, "output_tokens": 1}}))
        parsed = process.parse_stream("jsonl", stream)
        self.assertEqual((parsed["init"]["mcp_servers"], parsed["init"]["plugins"], parsed["init"]["skills"]),
                         (["kb-server"], ["p"], []))
        self.assertNotIn("init", process.parse_stream("jsonl", '{"type":"result","result":"ok","usage":{}}'))
        self.assertNotIn("init", process.parse_stream("text", "ok"))


class ProbeTests(unittest.TestCase):
    """infrastructure.cli_probe: the help command of the profile, a cache by CLI, version, help and flags, one retry."""

    def setUp(self):
        for cache in (cli_probe._KNOWN, cli_probe._HELP, cli_probe._VERSION):
            patcher = mock.patch.dict(cache, clear=True)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_d_the_flags_of_codex_exec_are_asked_of_codex_exec_help(self):
        answers = {("/opt/codex", "--version"): "codex-cli 0.163.0\nmore",
                   ("/opt/codex", "exec", "--help"): "  --ignore-user-config\n", ("/opt/codex", "--help"): "exec  Run"}
        with mock.patch.object(cli_probe.subprocess, "run",
                               side_effect=lambda args, **kw: mock.Mock(stdout=answers[tuple(args)])) as ran:
            self.assertTrue(cli_probe.knows(["/opt/codex", "-a", "never", "exec"], ["--ignore-user-config"],
                                            help_argv=["codex", "exec", "--help"]))
            self.assertFalse(cli_probe.knows(["/opt/codex", "exec"], ["--ignore-user-config"]))  # codex --help lacks it
            self.assertEqual(cli_probe.version(["/opt/codex"]), "codex-cli 0.163.0")
        self.assertEqual([tuple(call.args[0]) for call in ran.call_args_list],
                         [("/opt/codex", "--version"), ("/opt/codex", "exec", "--help"), ("/opt/codex", "--help")])
        self.assertTrue(cli_probe.knows([sys.executable, "fake_role.py"], ["--anything"]))  # a stand-in passes

    def test_a_timeout_is_tried_once_more_then_the_help_counts_as_unread(self):
        timeout = subprocess.TimeoutExpired("claude", 20)
        with mock.patch.object(cli_probe.subprocess, "run", side_effect=[mock.Mock(stdout="2.1"), timeout,
                                                                          mock.Mock(stdout="--safe-mode")]):
            self.assertTrue(cli_probe.knows(["/opt/claude"], ["--safe-mode"]))
        cli_probe._HELP.clear()
        cli_probe._KNOWN.clear()
        with mock.patch.object(cli_probe.subprocess, "run", side_effect=[timeout, timeout]) as ran:
            self.assertFalse(cli_probe.knows(["/opt/claude"], ["--safe-mode"]))
            self.assertTrue(cli_probe.failed(["/opt/claude"]))
        self.assertEqual(ran.call_count, 2)

    def test_a_cli_replaced_at_the_same_path_is_asked_again(self):
        """F6: an update of the CLI in place changes its version and flags; a live probe of the old version no longer
        confirms the new one."""
        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(tmp) / "codex"

            def install(version: str, flags: str, mtime: int) -> None:
                cli.write_text(f'#!/bin/sh\ncase "$*" in --version) echo "{version}";; *) echo "{flags}";; esac\n',
                               encoding="utf-8")
                cli.chmod(0o755)
                os.utime(cli, ns=(mtime, mtime))
            help_argv = ["codex", "exec", "--help"]
            install("codex v1", "--ignore-user-config", 1_000_000_000)
            self.assertEqual(cli_probe.version([str(cli)]), "codex v1")
            self.assertTrue(cli_probe.knows([str(cli)], ["--ignore-user-config"], help_argv=help_argv))
            probes = [{"provider": "codex", "version": "codex v1",
                       "claims": {"repository_instructions": False, "user_skills": False}}]
            self.assertEqual(isolation.confirmed(probes, "codex", cli_probe.version([str(cli)])),
                             ["repository_instructions", "user_skills"])
            install("codex v2 (new)", "--other-flag", 2_000_000_000)
            self.assertEqual(cli_probe.version([str(cli)]), "codex v2 (new)")
            self.assertFalse(cli_probe.knows([str(cli)], ["--ignore-user-config"], help_argv=help_argv))
            self.assertEqual(isolation.confirmed(probes, "codex", cli_probe.version([str(cli)])), [])

    def test_k_the_facade_knows_is_the_route_service_wrapper_and_the_launch_path_uses_it(self):
        self.assertIs(engine.Conductor._knows, route_service.knows)
        bare = engine.Conductor.__new__(engine.Conductor)
        self.assertEqual(bare.role_ports.knows.__func__, route_service.knows)
        self.assertEqual(bare.role_ports.note_isolation.__func__, route_service.note_plan)


class LaunchPathTests(unittest.TestCase):
    """Every launch of a role process goes through the isolation of its profile: the batch roles of review_plan
    (group reviewer, review strategist) are observed and refused like the roles of a piece; a wrapper stays partial."""
    CLAUDE = {"provider": "claude-code", "argv": ["/opt/claude", "-p"], "transport": "jsonl"}

    def setUp(self):
        for cache in (cli_probe._KNOWN, cli_probe._HELP, cli_probe._VERSION):
            patcher = mock.patch.dict(cache, clear=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        patcher = mock.patch.object(cli_probe, "_run", side_effect=lambda args: "2.1.310" if args[-1] == "--version"
                                    else "--safe-mode --strict-mcp-config --settings")
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)

    def owner(self):
        owner = engine.Conductor.__new__(engine.Conductor)
        owner.project = owner.directory = self.base
        owner.env, owner.settings, owner.run_id, owner.state, owner.progress = None, None, "", {}, mock.Mock()
        owner.store = mock.Mock()
        owner.store.mutating.side_effect = contextlib.nullcontext
        owner._save, owner._admit_budget, owner._tokens = mock.Mock(), mock.Mock(), mock.Mock()
        owner.handles = []

        def start(item, key, role, route, prompt_file, attempt):
            handle = {"directory": self.base / "agents" / key, "usage": {"input": 0, "cached": 0, "output": 0}}
            handle["directory"].mkdir(parents=True)
            owner.handles.append(handle)
            return handle

        def end(handle, error=None, succeeded=False):
            agents.finish(handle, exit_code=0, error=error, decisions=[], duration_s=0.1, stream=None, lingered=False,
                          isolation=handle.get("isolation"))
        owner._agent_start, owner._agent_end = start, end
        return owner

    def item(self, *roles, mode="require"):
        return mock.Mock(ref="W1", directory=self.base / "W1", options={
            "instructions": {"isolate_roles": list(roles), "isolation": mode}, "scope": {}})

    def test_f2_a_batch_role_is_observed_and_its_drift_refuses_the_next_launch(self):
        for key, role in (("group-review-1", "reviewer"), ("review-strategist", "triager")):
            with self.subTest(role=role):
                owner, item = self.owner(), self.item(role)
                run = process.RoleRun(exit=0, text="ok", init={"tools": ["Read"], "mcp_servers": ["kb-server"],
                                                               "skills": [], "plugins": [], "slash_commands": []})
                raw = self.base / "streams" / f"{key}.jsonl"
                with mock.patch.object(process, "run_role", return_value=run) as ran:
                    review_plan._run_agent(owner, item, key, role, self.CLAUDE, "prompt", raw, 60)
                    drift = [call for call in owner.progress.emit.call_args_list
                             if call.kwargs.get("reason_code") == "ISOLATION_DRIFT"]
                    self.assertEqual([call.kwargs["message"] for call in drift],
                                     [f"{role}/claude-code loaded mcp_servers [kb-server] although isolated"])
                    result = records.read(owner.handles[0]["directory"] / "result.json", "agent-result")
                    self.assertEqual(result["isolation"]["observed"]["mcp_servers"], ["kb-server"])
                    self.assertIn("claude-code:ISOLATION_DRIFT", owner.state["isolation_noted"])
                    with self.assertRaises(Stop) as stop:
                        review_plan._run_agent(owner, item, f"{key}-again", role, self.CLAUDE, "prompt", raw, 60)
                    self.assertEqual(stop.exception.code, "ISOLATION_UNAVAILABLE")
                    self.assertEqual(ran.call_count, 1)  # the second process is never started

    def test_f3_a_wrapper_is_partial_refused_under_require_and_said_under_prefer(self):
        wrapper = {"provider": "claude-code", "argv": ["/opt/claude-wrapper", "-p"], "transport": "jsonl"}
        owner = self.owner()
        found = launch_plan.isolation_plan(owner, self.item("executor"), "executor", wrapper)
        self.assertEqual((found["guarantee"], found["args"]), ("partial", ["--safe-mode", "--strict-mcp-config"]))
        self.assertEqual([entry["code"] for entry in found["degraded"]], ["PROBE_UNAVAILABLE"])
        with self.assertRaises(Stop) as stop:
            launch_plan.role_argv(owner, self.item("executor"), "executor", wrapper)
        self.assertEqual(stop.exception.code, "ISOLATION_UNAVAILABLE")
        self.assertIn("the command of the route is not a provider CLI the profile can probe", stop.exception.message)
        self.assertEqual(launch_plan.role_argv(owner, self.item("executor", mode="prefer"), "executor", wrapper)[-2:],
                         ["--safe-mode", "--strict-mcp-config"])
        said = [call.kwargs["message"] for call in owner.progress.emit.call_args_list
                if call.kwargs.get("reason_code") == "ISOLATION_PARTIAL"]
        self.assertEqual(said, ["executor/claude-code: partial isolation (the command of the route is not a provider CLI "
                                "the profile can probe)"])
        self.assertEqual(cli_probe._run.call_count, 0)  # nothing was asked of a command it cannot name
        probed = launch_plan.isolation_plan(owner, self.item("executor"), "executor", self.CLAUDE)
        self.assertEqual(probed["guarantee"], "full")


class IsolationRunCase(ConductorCase):
    """Runs with fake provider CLIs named claude and codex, first in the argv of their roles."""

    def setUp(self):
        super().setUp()
        for cache in (cli_probe._KNOWN, cli_probe._HELP, cli_probe._VERSION):
            patcher = mock.patch.dict(cache, clear=True)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.bin = self.project.parent / "bin"
        self.bin.mkdir()
        self.cli_log, self.cli_env = self.project.parent / "cli.log", self.project.parent / "cli-env.jsonl"
        for name in ("claude", "codex"):
            fake = self.bin / name
            fake.write_text(FAKE_CLI.format(python=sys.executable, fake_role=str(FIXTURES / "fake_role.py")),
                            encoding="utf-8")
            fake.chmod(0o755)
        patcher = mock.patch.dict(os.environ, {"FAKE_CLI_LOG": str(self.cli_log), "FAKE_CLI_ENV": str(self.cli_env),
                                               "FAKE_CLI_HELP_CLAUDE": "--safe-mode --strict-mcp-config --settings",
                                               "FAKE_CLI_HELP_CODEX": "--ignore-user-config"})
        patcher.start()
        self.addCleanup(patcher.stop)
        for key in profiles()["claude-code"]["env"]:  # a test run inside an isolated Claude Code role inherits them
            os.environ.pop(key, None)

    def use_cli(self, **clis) -> None:
        """``role=name``: the role runs the fake CLI ``name``; the others the plain fake role."""
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        argv.update({role.replace("_", "-"): [str(self.bin / name), role.replace("_", "-")]
                     for role, name in clis.items()})
        self.write_config(argv)

    def options(self, **layer) -> tuple:
        path = self.project.parent / "options.json"
        path.write_text(json.dumps(layer), encoding="utf-8")
        return ("--options", str(path))

    def argv(self, role: str, number: int = 1) -> list:
        return json.loads((self.fake / f"{role}-{number}.argv").read_text(encoding="utf-8"))

    def said(self, err: str, code: str) -> list:
        return [line for line in self.lines(err) if line.get("reason_code") == code]

    def asked(self) -> list:
        return [json.loads(line) for line in self.cli_log.read_text(encoding="utf-8").splitlines()] \
            if self.cli_log.exists() else []


class ClaudeRunTests(IsolationRunCase):
    def test_a_an_isolated_claude_code_role_gets_the_profile_and_one_that_is_not_isolated_nothing(self):
        self.use_cli(context_scout="claude", executor="claude")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=self.options(instructions={"isolate_roles": ["executor"]}))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.argv("executor")[-2:], ["--safe-mode", "--strict-mcp-config"])
        self.assertNotIn("--safe-mode", self.argv("context-scout"))
        envs = [json.loads(line) for line in self.cli_env.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sorted(env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] or "-" for env in envs), ["-", "1"])

    def test_b_a_flag_the_cli_does_not_list_is_left_out_and_said_once_per_run(self):
        os.environ["FAKE_CLI_HELP_CLAUDE"] = "--strict-mcp-config --settings"
        self.use_cli(context_scout="claude", executor="claude")
        self.set_items({"W1": {}, "W2": {}})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")], "reviewer": [GREEN]})
        for number, ref in enumerate(("W1", "W2"), 1):  # two runs in one process: the probe is cached, the line is not
            code, _, err = self.run_items(ref)
            self.assertEqual(code, 0, err)
            partial = [line for line in self.said(err, "ISOLATION_PARTIAL") if "--safe-mode" in line["message"]]
            self.assertEqual([line["message"] for line in partial],
                             [f"{self.bin / 'claude'} does not list --safe-mode; roles are isolated by the environment only"],
                             err)
            self.assertNotIn("--safe-mode", self.argv("executor", number))
            self.assertIn("--strict-mcp-config", self.argv("executor", number))
            self.assertIn("claude-code:--safe-mode", self.state(err)["isolation_noted"])
        helps = [call for call in self.asked() if call[-1] == "--help"]
        self.assertEqual(helps, [["claude", "--help"]])  # one probe for the process

    def test_c_require_stops_before_any_role_when_a_flag_is_missing(self):
        os.environ["FAKE_CLI_HELP_CLAUDE"] = "--strict-mcp-config"
        self.use_cli(context_scout="claude", executor="claude")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=self.options(instructions={
            "isolation": "require", "isolate_roles": ["context-scout", "executor"]}))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ISOLATION_UNAVAILABLE")), err)
        self.assertEqual((self.calls("executor"), self.calls("context-scout"), self.calls("reviewer")), (0, 0, 0))
        steps = (self.state(err).get("items", {}).get("W1") or {}).get("steps") or {}
        self.assertFalse([key for key in steps if key.startswith(("scout", "executor", "review"))], steps)
        self.assertTrue(any("executor/claude-code: partial isolation (the CLI does not list --safe-mode)" in json.dumps(line)
                            for line in self.lines(err)), err)

    def test_i_a_damaged_profiles_file_stops_the_run_before_any_role(self):
        broken = self.project.parent / "isolation-profiles.json"
        broken.write_text('{"$schema": "urn:swissknifeman:orch:conductor:isolation-profiles:v1"}', encoding="utf-8")
        self.use_cli(executor="claude")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        with mock.patch.object(isolation, "PROFILES_PATH", broken):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ISOLATION_PROFILES_INVALID")), err)
        self.assertEqual((self.calls("executor"), self.calls("context-scout")), (0, 0))

    def test_f1_a_report_fixer_is_refused_after_a_drift_under_require(self):
        """F1: the repair of an executor that drifted would start a report-fixer of the same provider; the preflight
        does not see the optional report-fixer, its launch refuses it."""
        self.use_cli(executor="claude", report_fixer="claude")
        self.script({"executor": [{"init": {"mcp_servers": ["kb-server"]}, "text": "done, but no report block"}],
                     "report-fixer": [{"result": report("W1"), "tag": "stage-report"}], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=self.options(instructions={
            "isolation": "require", "isolate_roles": ["executor", "report-fixer"]}))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ISOLATION_UNAVAILABLE")), err)
        self.assertEqual((self.calls("executor"), self.calls("report-fixer")), (1, 0))
        self.assertTrue(self.said(err, "ISOLATION_DRIFT"), err)
        self.assertTrue(any("report-fixer/claude-code: partial isolation" in json.dumps(line) for line in self.lines(err)),
                        err)

    def test_a_drift_under_require_refuses_the_next_role_of_the_provider(self):
        self.use_cli(executor="claude", reviewer="claude")
        self.script({"executor": [{**executor_ok("W1"), "init": {"mcp_servers": ["kb-server"]}}], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=self.options(reviewer="claude-code/sonnet/high", instructions={
            "isolation": "require", "isolate_roles": ["executor", "reviewer"]}))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ISOLATION_UNAVAILABLE")), err)
        self.assertEqual([line["message"] for line in self.said(err, "ISOLATION_DRIFT")],
                         ["executor/claude-code loaded mcp_servers [kb-server] although isolated"])
        self.assertEqual((self.calls("executor"), self.calls("reviewer")), (1, 0))
        self.assertIn("claude-code:ISOLATION_DRIFT", self.state(err)["isolation_noted"])


class CodexRunTests(IsolationRunCase):
    def codex_run(self, ref: str = "W1", **instructions) -> tuple:
        self.use_cli(executor="codex")
        self.set_items({ref: {}})
        self.script({"executor": [executor_ok(ref)], "reviewer": [GREEN]})
        return self.run_items(ref, extra=self.options(stages=[{"role": "executor", "provider": "codex"}],
                                                      instructions={"isolate_roles": ["executor"], **instructions}))

    def test_d_l_a_codex_role_gets_its_own_homes_with_auth_linked_and_the_profile_arguments(self):
        (self.home / ".codex").mkdir(parents=True)
        (self.home / ".codex" / "auth.json").write_text("{}", encoding="utf-8")
        canary = self.home / ".agents" / "skills" / "canary" / "SKILL.md"
        canary.parent.mkdir(parents=True)
        canary.write_text("SKM-CANARY\n", encoding="utf-8")
        os.environ.pop("CODEX_HOME", None)
        os.environ["XDG_CACHE_HOME"] = str(self.home / "cache")
        code, _, err = self.codex_run()
        self.assertEqual(code, 0, err)
        self.assertIn(["codex", "exec", "--help"], self.asked())
        self.assertNotIn(["codex", "--help"], self.asked())
        self.assertEqual(self.argv("executor")[-3:], ["--ignore-user-config", "-c", "project_doc_max_bytes=0"])
        env = json.loads(self.cli_env.read_text(encoding="utf-8").splitlines()[0])
        run = self.run_dir(err)
        self.assertEqual((env["CODEX_HOME"], env["HOME"]), (str(run / "isolation" / "codex-home"),
                                                            str(run / "isolation" / "codex-user-home")))
        self.assertEqual(env["XDG_CACHE_HOME"], str(self.home / "cache"))
        auth = Path(env["CODEX_HOME"]) / "auth.json"
        self.assertTrue(auth.is_symlink())
        self.assertEqual(os.readlink(auth), str(self.home / ".codex" / "auth.json"))
        for folder in (run / "isolation", Path(env["CODEX_HOME"]), Path(env["HOME"])):
            self.assertEqual(oct(folder.stat().st_mode & 0o777), "0o700", folder)
        self.assertEqual(sorted(path.name for path in Path(env["HOME"]).rglob("*")), [])  # no skills, no config
        self.assertEqual([path.name for path in Path(env["CODEX_HOME"]).iterdir()], ["auth.json"])
        self.assertEqual([line["message"] for line in self.said(err, "ISOLATION_PARTIAL") if "codex" in line["message"]],
                         ["executor/codex: partial isolation (repository_instructions canary, user_skills unknown)"])

    def test_e_require_refuses_codex_without_a_live_probe_and_admits_it_with_one_of_its_version(self):
        code, _, err = self.codex_run(isolation="require")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ISOLATION_UNAVAILABLE")), err)
        self.assertEqual(self.calls("executor"), 0)
        probes = locations.state_dir("orch") / isolation.PROBES_FILE
        probes.parent.mkdir(parents=True, exist_ok=True)
        probes.write_text(json.dumps({"$schema": "urn:swissknifeman:orch:conductor:isolation-probes:v1", "probes": [
            {"provider": "codex", "version": "codex 9.9.9", "at": "2026-10-25T10:00:00Z",
             "claims": {"repository_instructions": False, "user_skills": False}}]}), encoding="utf-8")
        code, _, err = self.codex_run("W2", isolation="require")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertFalse([line for line in self.said(err, "ISOLATION_PARTIAL") if "codex" in line["message"]], err)


class GrokRunTests(IsolationRunCase):
    def test_f_grok_under_require_stops_with_the_way_out(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=self.options(instructions={
            "isolation": "require", "isolate_roles": ["reviewer"]}))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "ISOLATION_UNAVAILABLE")), err)
        self.assertEqual(self.calls("executor"), 0)
        text = json.dumps(self.lines(err))
        self.assertIn("reviewer/grok: partial isolation (", text)
        self.assertIn("set instructions.isolation = prefer in a trusted layer or remove the role from isolate_roles", text)

    def test_h_m_a_drift_is_said_kept_in_the_result_and_the_records_stay_valid(self):
        self.script({"executor": [executor_ok("W1")],
                     "reviewer": [{**GREEN, "init": {"mcp_servers": ["kb-server"], "skills": ["x"]}}]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertEqual([line["message"] for line in self.said(err, "ISOLATION_DRIFT")],
                         ["reviewer/grok loaded mcp_servers [kb-server] although isolated",
                          "reviewer/grok loaded skills [x] although isolated"])
        partial = [line["message"] for line in self.said(err, "ISOLATION_PARTIAL")]
        grok = [text for text in partial if text.startswith("reviewer/grok")]  # one line per reason, each said once
        self.assertEqual(sorted(grok), ["reviewer/grok: partial isolation (repository_instructions unknown, memory "
                                        "unknown, plugins unknown, hooks on, mcp observed, user_skills observed)",
                                        "reviewer/grok: partial isolation (the command of the route is not a provider "
                                        "CLI the profile can probe)"], partial)
        run = self.run_dir(err)
        state = records.read(run / engine.STATE_FILE, "state")  # validated when read
        self.assertEqual(sorted(state["isolation_noted"]),  # the stand-in roles of this run cannot be probed
                         ["claude-code:PROBE_UNAVAILABLE", "grok:ISOLATION_DRIFT", "grok:PROBE_UNAVAILABLE",
                          "grok:SURFACES_UNCONFIRMED"])
        results = {}
        for request in (run / "W1" / "agents").glob("*/request.json"):
            results[records.read(request, "agent-request")["role"]] = records.read(request.with_name("result.json"),
                                                                                   "agent-result")
        self.assertEqual(results["reviewer"]["isolation"]["observed"]["mcp_servers"], ["kb-server"])
        self.assertEqual(results["executor"]["isolation"]["observed"]["mcp_servers"], [])
        self.assertEqual(engine.RunStore(self.project, run.name).load()[1]["isolation_noted"], state["isolation_noted"])
        old = {key: value for key, value in state.items() if key != "isolation_noted"}  # a state from before P6.1
        self.assertEqual(records.problems(old, "state"), [])
        code, _, err = self.conduct("resume", "--run", run.name, "--json-lines")
        self.assertEqual(code, 0, err)
        self.assertFalse(self.said(err, "ISOLATION_PARTIAL"), err)  # said once per run, a resume included


class OptionsTests(unittest.TestCase):
    def test_g_a_work_source_layer_may_only_tighten_the_isolation(self):
        def layers(value: str, trusted: bool = False) -> list:
            return [{"source": "item:W1", "options": {"instructions": {"isolation": value}},
                     **({"trusted": True} if trusted else {})}]
        self.assertEqual(opts.DEFAULTS["instructions"]["isolation"], "prefer")
        with self.assertRaises(opts.OptionsError) as error:
            opts.effective({}, {}, layers("off"))
        self.assertEqual(error.exception.code, "OPTIONS_UNTRUSTED")
        self.assertIn("instructions.isolation off is weaker than prefer", error.exception.message)
        self.assertEqual(opts.effective({}, {}, layers("require"))[0]["instructions"]["isolation"], "require")
        self.assertEqual(opts.effective({}, {}, layers("off", trusted=True))[0]["instructions"]["isolation"], "off")


class ProbeScriptTests(unittest.TestCase):
    """scripts/isolation-probe.py with fake codex and grok CLIs first in PATH, a temporary HOME and SKM_HOME."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name)
        bin_dir, self.log, self.env_log = self.base / "bin", self.base / "cli.log", self.base / "cli-env.jsonl"
        bin_dir.mkdir()
        for name in ("codex", "grok"):
            fake = bin_dir / name
            fake.write_text(FAKE_CLI.format(python=sys.executable, fake_role=str(FIXTURES / "fake_role.py")),
                            encoding="utf-8")
            fake.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
                    "FAKE_CLI_LOG": str(self.log), "FAKE_CLI_ENV": str(self.env_log),
                    "FAKE_CLI_HELP_CODEX": "--ignore-user-config", "HOME": str(self.base),
                    "SKM_HOME": str(self.base / "skm")}

    def probe(self, *args, **env) -> tuple:
        done = subprocess.run([sys.executable, str(PROBE), "--json", *args], env={**self.env, **env},
                              capture_output=True, text=True, timeout=120)
        return done.returncode, json.loads(done.stdout) if done.stdout.strip() else None, done.stderr

    def records(self) -> list:
        path = locations.state_dir("orch", env={"SKM_HOME": str(self.base / "skm"), "HOME": str(self.base)}) \
            / isolation.PROBES_FILE
        return json.loads(path.read_text(encoding="utf-8"))["probes"] if path.exists() else []

    def test_j_without_live_the_script_only_reads_the_help_of_the_profile(self):
        code, report, err = self.probe("--provider", "codex")
        self.assertEqual(code, 0, err)
        self.assertEqual((report["flags_listed"], report["version"], report["guarantee"]),
                         (True, "codex 9.9.9", "partial"))
        calls = [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(calls, [["codex", "--version"], ["codex", "exec", "--help"]])
        self.assertFalse((self.base / "skm").exists())  # nothing written without --live
        code, report, _ = self.probe("--provider", "codex", FAKE_CLI_HELP_CODEX="--other")
        self.assertEqual((code, report["missing"]), (1, ["--ignore-user-config"]))

    def test_f4_a_render_that_cannot_be_checked_confirms_nothing(self):
        for render in ("", "[]", "not the model input", json.dumps([{"content": [{"text": "another prompt"}]}])):
            with self.subTest(render=render):
                code, report, err = self.probe("--provider", "codex", "--live", FAKE_CLI_RENDER=render)
                self.assertEqual((code, report), (2, None), err)
                self.assertIn("ISOLATION_PROBE_FAILED", err)
                self.assertEqual(self.records(), [])
        code, report, err = self.probe("--provider", "codex", "--live", FAKE_CLI_RENDER="agents")  # the canary is seen
        self.assertEqual((code, report["claims"]["repository_instructions"], report["guarantee"]), (1, True, "partial"))
        code, report, err = self.probe("--provider", "codex", "--live")  # a render with the prompt and no canary
        self.assertEqual((code, report["claims"], report["guarantee"]),
                         (0, {"repository_instructions": False, "user_skills": False}, "full"), err)
        self.assertEqual([(entry["version"], entry["claims"]) for entry in self.records()],
                         [("codex 9.9.9", {"repository_instructions": False, "user_skills": False})])
        renders = [call for call in map(json.loads, self.log.read_text(encoding="utf-8").splitlines())
                   if call[1:3] == ["debug", "prompt-input"] and call[-1] != "--help"]
        self.assertTrue(all("--ignore-user-config" in call and "project_doc_max_bytes=0" in call for call in renders))

    def test_f5_grok_inspect_runs_with_temporary_homes_only(self):
        sentinel = {"HOME": str(self.base / "owner-home"), "XDG_CONFIG_HOME": str(self.base / "owner-config"),
                    "GROK_HOME": str(self.base / "owner-grok")}
        code, report, err = self.probe("--provider", "grok", "--live", **sentinel)
        self.assertEqual(code, 0, err)
        self.assertEqual(report["claims"], {"repository_instructions": False, "user_skills": False})
        seen = [json.loads(line) for line in self.env_log.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(len(seen), 1)
        for key, owner in sentinel.items():
            self.assertNotEqual(seen[0][key], owner, key)
            self.assertIn("skm-isolation-", seen[0][key], key)
        code, report, err = self.probe("--provider", "grok", "--live", FAKE_CLI_INSPECT="")
        self.assertEqual((code, report), (2, None), err)


class LaunchPlanTests(unittest.TestCase):
    def test_project_instructions_are_kept_away_from_an_isolated_role_by_its_profile(self):
        """Moved from test_conductor (the Claude-only constants are gone): the profile gives the arguments and the
        environment; grok gets no arguments but its plan says partial."""
        eng = engine.Conductor.__new__(engine.Conductor)
        eng.env = {"PATH": "/bin"}
        item = type("I", (), {"options": {"instructions": {"isolate_roles": ["executor", "registrar"]}}})()
        env = eng._role_env(item, "executor", {"provider": "claude-code"})
        self.assertEqual((env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"], env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"]), ("1", "1"))
        self.assertEqual(env["PATH"], "/bin")
        self.assertEqual(eng._role_env(item, "reviewer", {"provider": "claude-code"}), {"PATH": "/bin"})
        self.assertEqual(eng._role_env(item, "executor", {"provider": "grok"}), {"PATH": "/bin"})
        listed = {("claude", "--version"): "2.1.310", ("claude", "--help"): "--safe-mode --strict-mcp-config",
                  ("grok", "--version"): "grok 1.0.50", ("grok", "--help"): "--rules"}
        with mock.patch.dict(cli_probe._KNOWN, clear=True), mock.patch.dict(cli_probe._HELP, clear=True), \
                mock.patch.dict(cli_probe._VERSION, clear=True), \
                mock.patch.object(cli_probe, "_run", side_effect=lambda args: listed[tuple(args)]):
            claude = {"provider": "claude-code", "argv": ["claude", "-p"]}
            self.assertEqual(eng._role_argv(item, "executor", claude), ["claude", "-p", "--safe-mode", "--strict-mcp-config"])
            self.assertEqual(eng._role_argv(item, "reviewer", claude), ["claude", "-p"])
            grok = {"provider": "grok", "argv": ["grok"]}
            self.assertEqual(eng._role_argv(item, "executor", grok), ["grok"])
            self.assertEqual(launch_plan.isolation_plan(eng, item, "executor", grok)["guarantee"], "partial")

    def test_copy_mode_copies_the_auth_and_a_missing_xdg_variable_keeps_its_place_under_the_original_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            home, run = Path(tmp) / "home", Path(tmp) / "run"
            (home / ".codex").mkdir(parents=True)
            (home / ".codex" / "auth.json").write_text("{}", encoding="utf-8")
            profile = dict(profiles()["codex"]["home"], mode="copy")
            found = launch_plan.prepare_home(run, "codex", profile, {"HOME": str(home)})
            self.assertEqual(found["XDG_CACHE_HOME"], str(home / ".cache"))
            placed = Path(found["CODEX_HOME"]) / "auth.json"
            self.assertFalse(placed.is_symlink())
            self.assertEqual(oct(placed.stat().st_mode & 0o777), "0o600")
            linked = launch_plan.prepare_home(run, "codex", profiles()["codex"]["home"],
                                              {"HOME": str(home), "CODEX_HOME": str(Path(tmp) / "own")})
            self.assertEqual(os.readlink(Path(linked["CODEX_HOME"]) / "auth.json"), str(Path(tmp) / "own" / "auth.json"))


if __name__ == "__main__":
    unittest.main()
