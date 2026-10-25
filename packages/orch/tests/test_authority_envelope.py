"""The authority envelope of a role launch (P6.2, knowledge/p6-design#p6-2-authority): (a) the command line of every role
and provider of the launch catalog, with the sandbox up and down and the access open and confined, is the reviewed
snapshot ``golden/authority-matrix.json``; (b) the document and its digest; (c) no project file of the provider is read;
(d) the permissions of orch come with ``--setting-sources user``; (e) a CLI without the flag; (f) the record before the
process; (g) AUTHORITY_CHANGED; (h) the dry run and ``roles matrix``; (i) the prompt; (j) a fallback; (k) a crash between
the record and the process; (l) the report-fixer and the batch roles; (m) the records. Fake probes, fake roles and a
temporary HOME only; no real provider is started."""
from __future__ import annotations

import builtins
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock

from aicore.ext import events as journal

from orch import launch
from orch.conductor import agents, contract, engine, process, prompts, records
from orch.conductor.application import review_plan
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import cli_probe, launch_plan, roles
from orch.conductor.policies import authority
from orch.settings import ORCH_ROOT
from tests.test_conductor import FIXTURES, GREEN, ROLES as RUN_ROLES, ConductorCase, executor_ok, quota_failure, report

GOLDEN = Path(__file__).resolve().parent / "golden" / "authority-matrix.json"
UPDATE = "SKM_UPDATE_GOLDEN"  # set to 1 to rewrite the snapshot, as the review of a change of a command line
UP = {"available": True, "reason": None, "checked": []}
DOWN = {"available": False, "reason": "bwrap: setting up uid map: Permission denied", "checked": []}
CONDUCTOR_ROLE = {"scout": "context-scout"}
ALL_FLAGS = "--safe-mode --strict-mcp-config --settings --setting-sources --ignore-user-config"
ROLES = ["context-scout", "executor", "bounded-implementer", "reviewer", "triager", "registrar", "report-fixer",
         "researcher", "advisor"]


def guard_of(argv: list) -> str:
    """The guard a command line shows: the Landlock prefix (``rw`` when it grants a folder and protects none), the
    settings of the Claude sandbox, the Codex sandbox."""
    if any(arg.endswith("ro-run.py") for arg in argv[:2]):
        prefix = argv[:argv.index("--")]
        return "landlock-rw" if "--rw" in prefix and "--protect" not in prefix else "landlock-protect"
    if "--settings" in argv and "sandbox" in json.loads(argv[argv.index("--settings") + 1]):
        return "claude-sandbox"
    mode = argv[argv.index("--sandbox") + 1] if "--sandbox" in argv[:-1] else None
    return "codex-sandbox" if mode in ("read-only", "workspace-write") else "none"


class Matrix:
    """A conductor without a run: the options of one piece, a project and a HOME of their own, fake probes."""

    def __init__(self, base: Path):
        self.base = base
        self.home, self.project = base / "home", base / "work" / "project"
        self.project.mkdir(parents=True)
        self.home.mkdir()

    def owner(self, access: str):
        owner = engine.Conductor.__new__(engine.Conductor)
        owner.project, owner.directory = self.project, self.base / "run"
        owner.env, owner.run_id, owner.state, owner.progress = None, "", {}, mock.Mock()
        owner.settings = types.SimpleNamespace(launch={"access": access}, resolved=None, aicore=None)
        owner.store = mock.Mock()
        owner.store.mutating.side_effect = contextlib.nullcontext
        owner._save = mock.Mock()
        return owner

    def item(self):
        return types.SimpleNamespace(
            ref="W1", state={}, claim={}, input_doc={}, directory=self.base / "run" / "W1",
            options={"instructions": {"isolate_roles": list(ROLES), "isolation": "prefer", "sandbox": "prefer",
                                      "sandbox_domains": []},
                     "scope": {"extra_paths": ["~/extra-out"]}, "session": {"executor": "handoff"}})

    def route(self, catalog: dict, launch_role: str, provider: str, access: str) -> dict:
        entry = catalog["launch"][launch_role][provider]
        argv = launch.build_argv(catalog, launch_role, provider, model="m", effort=entry["effort"], cwd=self.project,
                                 access=access)
        found = {"role": CONDUCTOR_ROLE.get(launch_role, launch_role), "provider": provider, "model": "m",
                 "effort": entry["effort"], "model_class": entry["model_class"], "transport": entry["transport"],
                 "timeout_s": 0, "idle_timeout_s": 0, "argv": argv}
        resume = launch.build_resume_argv(catalog, launch_role, provider, model="m", effort=entry["effort"],
                                          cwd=self.project, access=access)
        if resume:
            found["resume_argv"] = resume
        return found

    def normal(self, text: str) -> str:
        folder = launch_plan.transcript_folder_name(self.project)
        return (text.replace(folder, "<project-folder>").replace(str(self.project), "<project>")
                .replace(str(self.home), "<home>").replace(str(ORCH_ROOT), "<orch>"))

    def cases(self) -> list:
        catalog = launch.load_catalog()
        rows = []
        for launch_role, providers in catalog["launch"].items():
            role = CONDUCTOR_ROLE.get(launch_role, launch_role)
            for provider in providers:
                for sandbox, probed in (("up", UP), ("down", DOWN)):
                    for access in ("open", "confined"):
                        owner, item = self.owner(access), self.item()
                        route = self.route(catalog, launch_role, provider, access)
                        with mock.patch.object(engine.sandbox, "probe", return_value=probed):
                            envelope = launch_plan.authority(owner, item, role, route, admit=False)
                            argv = owner.role_argv(item, role, route)
                        if envelope["guard"] != guard_of(argv):
                            raise AssertionError(f"{role}/{provider}: the envelope says {envelope['guard']}, the "
                                                 f"command line {guard_of(argv)}")
                        rows.append({"role": role, "provider": provider, "sandbox": sandbox, "access": access,
                                     "guard": envelope["guard"], "argv": [self.normal(arg) for arg in argv]})
        return rows


def probed_flags():
    """Every flag listed by every CLI the matrix names (the caches of the probe are its own)."""
    stack = contextlib.ExitStack()
    for cache in (cli_probe._KNOWN, cli_probe._HELP, cli_probe._VERSION):
        stack.enter_context(mock.patch.dict(cache, clear=True))
    stack.enter_context(mock.patch.object(cli_probe, "_run", side_effect=lambda args: "9.9.9" if args[-1] == "--version"
                                          else ALL_FLAGS))
    return stack


class MatrixTests(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        self.matrix = Matrix(base)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.matrix.home)})
        patcher.start()
        self.addCleanup(patcher.stop)
        stack = probed_flags()
        stack.__enter__()
        self.addCleanup(stack.close)

    def test_a_the_command_line_of_every_role_and_provider_is_the_reviewed_snapshot(self):
        """Any change of a command line or a guard of a launch shows up here. Update the snapshot only as the review of
        that change (``SKM_UPDATE_GOLDEN=1``)."""
        found = {"cases": self.matrix.cases()}
        if os.environ.get(UPDATE) == "1":
            GOLDEN.write_text(json.dumps(found, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        self.assertEqual(found, json.loads(GOLDEN.read_text(encoding="utf-8")))

    def envelope(self, role: str = "executor", provider: str = "claude-code", probed=UP, mode: str = "prefer",
                 extra=("~/extra-out",)) -> dict:
        owner, item = self.matrix.owner("open"), self.matrix.item()
        item.options["instructions"]["isolation"] = mode
        item.options["scope"]["extra_paths"] = list(extra)
        route = self.matrix.route(launch.load_catalog(), role, provider, "open")
        with mock.patch.object(engine.sandbox, "probe", return_value=probed):
            return launch_plan.authority(owner, item, role, route, admit=False)

    def test_b_the_document_passes_its_schema_and_its_digest_does_not_depend_on_the_home(self):
        first = self.envelope()
        self.assertEqual(contract.problems(first, "authority-envelope"), [])
        self.assertEqual(first["digest"], authority.digest(first))
        self.assertEqual([root["path"] for root in first["write_roots"]], [".", "~/extra-out"])
        other = self.matrix.base / "other-home"
        other.mkdir()
        with mock.patch.dict(os.environ, {"HOME": str(other)}):
            second = self.envelope()
        self.assertEqual(second, first)
        self.assertNotIn(str(self.matrix.home), json.dumps(first))
        self.assertNotIn(str(self.matrix.project), json.dumps(first))
        broken = dict(first, isolation=dict(first["isolation"], env={"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"}))
        self.assertTrue(contract.problems(broken, "authority-envelope"))  # names of variables only, never their values

    def test_c_a_project_settings_file_of_the_provider_changes_nothing_and_is_not_read(self):
        before = self.envelope()
        settings = self.matrix.project / ".claude" / "settings.local.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"permissions": {"allow": ["Edit(/**)"], "defaultMode": "bypassPermissions"}}),
                            encoding="utf-8")
        opened, real = [], builtins.open

        def spy(path, *args, **kwargs):
            opened.append(str(path))
            return real(path, *args, **kwargs)
        with mock.patch.object(builtins, "open", spy), mock.patch.object(Path, "read_text", autospec=True,
                                                                          side_effect=lambda self, *a, **k: (
                                                                              opened.append(str(self)),
                                                                              real(self, *a, **k).read())[1]):
            after = self.envelope()
        self.assertEqual(after, before)
        self.assertFalse([path for path in opened if "/.claude/" in path or "/.codex/" in path or "/.grok/" in path],
                         opened)

    def test_d_an_isolated_claude_executor_gets_the_sandbox_and_the_deny_rules_in_one_settings_object(self):
        owner, item = self.matrix.owner("open"), self.matrix.item()
        route = self.matrix.route(launch.load_catalog(), "executor", "claude-code", "open")
        with mock.patch.object(engine.sandbox, "probe", return_value=UP):
            argv = owner.role_argv(item, "executor", route)
        settings = json.loads(argv[argv.index("--settings") + 1])
        self.assertEqual(sorted(settings), ["permissions", "sandbox"])
        self.assertIn("Bash(git push*)", settings["permissions"]["deny"])
        self.assertEqual(settings["permissions"]["deny"], authority.ORCH_PERMISSION_RULES["deny"])
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "user")
        self.assertEqual(argv.count("--setting-sources"), 1)  # the catalog value user,project is replaced, not repeated
        self.assertEqual(argv.count("--settings"), 1)

    def test_d_a_claude_role_never_gets_user_sources_without_the_deny_rules(self):
        for row in self.matrix.cases():
            argv = row["argv"]
            if "--setting-sources" in argv and argv[argv.index("--setting-sources") + 1] == "user":
                with self.subTest(role=row["role"], sandbox=row["sandbox"]):
                    self.assertIn("Bash(git push*)", json.loads(argv[argv.index("--settings") + 1])["permissions"]["deny"])

    def test_e_a_cli_without_setting_sources_keeps_the_project_settings_and_require_refuses_it(self):
        with mock.patch.dict(cli_probe._KNOWN, clear=True), mock.patch.dict(cli_probe._HELP, clear=True), \
                mock.patch.object(cli_probe, "_run", side_effect=lambda args: "9.9.9" if args[-1] == "--version"
                                  else "--safe-mode --strict-mcp-config --settings"):
            found = self.envelope("reviewer")
            self.assertIsNone(found["setting_sources"])
            self.assertEqual(found["permission_rules"], {"deny": [], "ask": []})
            self.assertIn("SETTING_SOURCES_UNSUPPORTED", [entry["code"] for entry in found["degraded"]])
            self.assertEqual(self.envelope()["setting_sources"], ["user", "project"])  # the catalog value of a writer
            owner, item = self.matrix.owner("open"), self.matrix.item()
            item.options["instructions"]["isolation"] = "require"
            route = self.matrix.route(launch.load_catalog(), "reviewer", "claude-code", "open")
            with mock.patch.object(engine.sandbox, "probe", return_value=UP), self.assertRaises(Stop) as stop:
                launch_plan.authority(owner, item, "reviewer", route)
        self.assertEqual(stop.exception.code, "ISOLATION_UNAVAILABLE")
        self.assertIn("project permissions reach the role", stop.exception.message)

    def test_i_the_prompt_block_says_what_the_envelope_says(self):
        codex = self.envelope("executor", "codex")
        claude = self.envelope("executor", "claude-code")
        for doc, docker in ((codex, "you may use containers"), (claude, "not available here")):
            with self.subTest(guard=doc["guard"]):
                text = authority.prompt_block(doc)
                self.assertIn(docker, text)
                self.assertLessEqual(len(text.splitlines()), authority.PROMPT_LINES)
        self.assertIn("git push, git reset --hard, git clean are denied", authority.prompt_block(claude))
        self.assertIn("anywhere this user can", authority.prompt_block(codex))
        doc = json.loads((ORCH_ROOT / "fixtures" / "exec" / "v1" / "valid" / "execution-input" / "plan-bound.json")
                         .read_text(encoding="utf-8"))
        blocks = prompts.executor(doc, item="P1.1", step="executor.1", authority=authority.prompt_block(claude))
        self.assertEqual([block.origin for block in blocks if block.kind == "authority"], ["conductor"])

    def guard_route(self, *prefix) -> dict:
        command = [sys.executable, "fake_role.py", "executor"]
        return {"role": "executor", "provider": "grok", "transport": "jsonl",
                "argv": [sys.executable, str(ORCH_ROOT / "scripts" / "ro-run.py"), *prefix, "--", *command]}

    def guard_envelope(self, route: dict) -> dict:
        owner, item = self.matrix.owner("open"), self.matrix.item()
        item.options["scope"]["extra_paths"] = []
        return launch_plan.authority(owner, item, "executor", route, admit=False)

    def test_f2_the_default_writable_roots_of_the_guard_are_in_the_envelope(self):
        """The envelope names what ro-run.py really leaves writable (its parse of the same prefix), with and without
        --no-default-rw; the flag changes the digest."""
        spec = importlib.util.spec_from_file_location("ro_run", ORCH_ROOT / "scripts" / "ro-run.py")
        ro_run = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ro_run)
        self.assertEqual(tuple(ro_run.DEFAULT_WRITABLE), authority.GUARD_DEFAULT_WRITABLE)
        project, home = str(self.matrix.project), str(self.matrix.home)
        found = {}
        for flags in ((), ("--no-default-rw",)):
            with self.subTest(flags=flags):
                route = self.guard_route(*flags, "--rw", project)
                writable, _command, _protected = ro_run._parse(route["argv"][2:])
                expected = [path.replace(project, ".").replace(home, "~") for path in writable]
                found[flags] = self.guard_envelope(route)
                self.assertEqual([root["path"] for root in found[flags]["write_roots"]], expected)
        self.assertEqual([root["path"] for root in found[()]["write_roots"]], ["/tmp", "/var/tmp", "/dev", "~/.grok", "."])
        self.assertNotEqual(found[()]["digest"], found[("--no-default-rw",)]["digest"])

    def test_f3_a_resume_command_that_grants_more_is_refused_before_the_record_and_the_process(self):
        catalog = launch.load_catalog()
        shipped = self.matrix.route(catalog, "executor", "grok", "open")
        wider = dict(shipped, resume_argv=[*shipped["resume_argv"][:2], "--rw", "/srv/output", *shipped["resume_argv"][2:]])
        owner, item = self.matrix.owner("open"), self.matrix.item()
        envelope = launch_plan.authority(owner, item, "executor", wider, admit=False)
        problem = launch_plan.resume_problem(owner, item, "executor", wider, ["S1"], envelope)
        self.assertIn("write_roots", problem)
        handle = {"directory": self.matrix.base / "agents" / "agent-x-1", "usage": dict.fromkeys(agents.USAGE_KEYS, 0)}
        with mock.patch.object(launch_plan.sessions, "resume_args", return_value=["S1"]), \
                mock.patch.object(process, "run_role") as ran, self.assertRaises(Stop) as stop:
            roles.launch(owner, item, handle, "executor", wider, "prompt", attempt=1, raw=Path("raw"), timeout_s=1)
        self.assertEqual((stop.exception.code, ran.call_count), ("AUTHORITY_RESUME_MISMATCH", 0))
        self.assertFalse((handle["directory"] / "authority").exists())
        with self.assertRaises(Stop):  # the command line of the attempt is refused the same way
            with mock.patch.object(launch_plan.sessions, "resume_args", return_value=["S1"]):
                launch_plan.role_argv(owner, item, "executor", wider)

    def test_f3_the_shipped_resume_commands_have_the_authority_of_their_command(self):
        catalog = launch.load_catalog()
        for provider in ("codex", "grok"):
            for access in ("open", "confined"):
                with self.subTest(provider=provider, access=access):
                    owner, item = self.matrix.owner(access), self.matrix.item()
                    route = self.matrix.route(catalog, "executor", provider, access)
                    envelope = launch_plan.authority(owner, item, "executor", route, admit=False)
                    self.assertIsNone(launch_plan.resume_problem(owner, item, "executor", route, ["S1"], envelope))
                    resumed = launch_plan.authority(owner, item, "executor",
                                                    dict(route, argv=launch_plan.resume_command(route, ["S1"])),
                                                    admit=False)
                    self.assertEqual(resumed["guard"], "codex-sandbox" if (provider, access) == ("codex", "confined")
                                     else envelope["guard"])

    def test_f4_a_filesystem_guard_is_no_command_deny_layer(self):
        reviewer = self.envelope("reviewer", "grok")
        self.assertEqual(reviewer["guard"], "landlock-protect")
        self.assertEqual({key: reviewer["git"][key] for key in ("push", "reset_hard", "clean")},
                         dict.fromkeys(("push", "reset_hard", "clean"), "unenforced"))
        self.assertFalse(reviewer["git"]["dot_git_write"])
        self.assertIn({"path": "./vendor", "why": "guard"}, reviewer["write_roots"])
        self.assertNotIn("denied", authority.prompt_block(reviewer))
        codex = self.envelope("reviewer", "codex")
        self.assertEqual((codex["guard"], codex["git"]["push"]), ("codex-sandbox", "unenforced"))
        claude = self.envelope("executor", "claude-code")  # the deny rules of orch are a command deny layer
        self.assertEqual(claude["git"]["push"], "denied")

    def test_the_matrix_command_is_the_table_of_the_docs(self):
        """(h) ``orch.py roles matrix --markdown`` prints the block between the markers of docs/conductor.md."""
        done = subprocess.run([sys.executable, str(ORCH_ROOT / "scripts" / "orch.py"), "roles", "matrix", "--markdown"],
                              capture_output=True, text=True, timeout=60,
                              env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)})
        self.assertEqual(done.returncode, 0, done.stderr)
        text = (ORCH_ROOT / "docs" / "conductor.md").read_text(encoding="utf-8")
        block = text.split("<!-- authority-matrix:begin -->\n", 1)[1].split("<!-- authority-matrix:end -->", 1)[0]
        self.assertEqual(done.stdout, block, "docs/conductor.md drifted from orch.py roles matrix: paste its output")
        rows = json.loads(subprocess.run([sys.executable, str(ORCH_ROOT / "scripts" / "orch.py"), "roles", "matrix",
                                          "--json"], capture_output=True, text=True, timeout=60, check=True,
                                         env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)}).stdout)
        executor = {row["access"]: row for row in rows if (row["role"], row["provider"]) == ("executor", "codex")}
        self.assertEqual((executor["open"]["docker"], executor["confined"]["docker"]), ("open", "blocked"))


class RecordTests(unittest.TestCase):
    """``agents.write_authority``: the record of a launch, checked and never rewritten."""

    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        self.handle = {"directory": base / "agents" / "agent-x-1", "usage": dict.fromkeys(agents.USAGE_KEYS, 0)}
        self.doc = json.loads((ORCH_ROOT / "fixtures" / "conductor" / "v1" / "valid" / "authority-envelope"
                               / "claude-executor.json").read_text(encoding="utf-8"))

    def test_the_record_is_written_once_and_an_other_authority_for_the_same_attempt_is_refused(self):
        path = agents.write_authority(self.handle, 1, self.doc)
        self.assertEqual(path, self.handle["directory"] / "authority" / "a1.json")
        written = path.read_bytes()
        agents.write_authority(self.handle, 1, self.doc)  # the same authority: kept as it is
        self.assertEqual(path.read_bytes(), written)
        other = dict(self.doc, access="confined")
        other["digest"] = authority.digest(other)
        with self.assertRaises(Stop) as stop:
            agents.write_authority(self.handle, 1, other)
        self.assertEqual(stop.exception.code, "AUTHORITY_RECORD_CONFLICT")
        self.assertEqual(path.read_bytes(), written)
        self.assertEqual(self.handle["authority"], [{"attempt": 1, "provider": "claude-code", "digest": self.doc["digest"]}])

    def test_an_envelope_outside_its_contract_is_not_written(self):
        with self.assertRaises(Stop) as stop:
            agents.write_authority(self.handle, 1, dict(self.doc, guard="landlock"))
        self.assertEqual(stop.exception.code, "RECORD_INVALID")
        self.assertFalse((self.handle["directory"] / "authority").exists())

    def test_k_a_crash_between_the_record_and_the_process_leaves_the_record_and_no_result(self):
        owner = engine.Conductor.__new__(engine.Conductor)
        owner.project, owner.state, owner.progress, owner.store, owner.env = Path(self.handle["directory"]), {}, mock.Mock(), None, None
        owner._authority = mock.Mock(return_value=self.doc)
        owner._role_argv = mock.Mock(return_value=["fake"])
        owner._role_env = mock.Mock(return_value={})
        item = types.SimpleNamespace(ref="W1", state={}, options={})
        route = {"provider": "claude-code", "transport": "jsonl"}
        with mock.patch.object(process, "run_role", side_effect=SystemExit(9)), self.assertRaises(SystemExit):
            roles.launch(owner, item, self.handle, "executor", route, "prompt", attempt=2, raw=Path("raw"), timeout_s=1)
        self.assertTrue((self.handle["directory"] / "authority" / "a2.json").is_file())
        self.assertFalse((self.handle["directory"] / "result.json").exists())
        self.assertEqual(item.state["authority"], {"executor": self.doc["digest"]})

    def kept(self, text: str) -> Path:
        path = self.handle["directory"] / "authority" / "a1.json"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_f5_an_existing_record_is_checked_before_it_is_kept(self):
        """A record already written is read back like any record: not JSON, outside the schema (only a digest) or with
        a digest that is not the one of its content (tampered) stops the launch; the file stays, the handle names
        nothing."""
        tampered = dict(self.doc, docker="open")  # schema-valid, the old digest
        for name, text in (("not json", "{"), ("only a digest", json.dumps({"digest": self.doc["digest"]})),
                           ("tampered", json.dumps(tampered))):
            with self.subTest(name):
                shutil.rmtree(self.handle["directory"], ignore_errors=True)
                self.handle.pop("authority", None)
                path = self.kept(text)
                with self.assertRaises(Stop) as stop:
                    agents.write_authority(self.handle, 1, self.doc)
                self.assertEqual(stop.exception.code, "RECORD_INVALID", stop.exception.message)
                self.assertEqual(path.read_text(encoding="utf-8"), text)
                self.assertNotIn("authority", self.handle)
        shutil.rmtree(self.handle["directory"], ignore_errors=True)
        self.kept(json.dumps(self.doc))  # a valid identical record: kept, and named by the handle
        agents.write_authority(self.handle, 1, self.doc)
        self.assertEqual(self.handle["authority"][0]["digest"], self.doc["digest"])
        other = dict(self.doc, access="confined")
        other["digest"] = authority.digest(other)
        with self.assertRaises(Stop) as stop:  # a valid conflicting record
            agents.write_authority(dict(self.handle, authority=[]), 1, other)
        self.assertEqual(stop.exception.code, "AUTHORITY_RECORD_CONFLICT")
        with self.assertRaises(Stop):  # an incoming envelope whose digest is not its own is a defect of the writer
            agents.write_authority(self.handle, 2, dict(self.doc, docker="open"))

    def test_f5_a_damaged_record_starts_no_process(self):
        self.kept(json.dumps({"digest": self.doc["digest"]}))
        owner = engine.Conductor.__new__(engine.Conductor)
        owner.project, owner.state, owner.progress, owner.store, owner.env = Path(self.handle["directory"]), {}, mock.Mock(), None, None
        owner._authority = mock.Mock(return_value=self.doc)
        owner._role_argv = mock.Mock(return_value=["fake"])
        owner._role_env = mock.Mock(return_value={})
        item = types.SimpleNamespace(ref="W1", state={}, options={})
        with mock.patch.object(process, "run_role") as ran, self.assertRaises(Stop) as stop:
            roles.launch(owner, item, self.handle, "executor", {"provider": "claude-code", "transport": "jsonl"},
                         "prompt", attempt=1, raw=Path("raw"), timeout_s=1)
        self.assertEqual((stop.exception.code, ran.call_count, item.state), ("RECORD_INVALID", 0, {}))


class LaunchSiteTests(unittest.TestCase):
    def test_l_the_conductor_starts_a_provider_process_in_one_place(self):
        found = []
        for path in sorted((ORCH_ROOT / "lib" / "orch" / "conductor").rglob("*.py")):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if "process.run_role(" in line and not line.lstrip().startswith("#"):
                    found.append(f"{path.relative_to(ORCH_ROOT)}:{number}")
        self.assertEqual(len(found), 1, found)
        self.assertTrue(found[0].startswith("lib/orch/conductor/infrastructure/roles.py:"), found)


class AuthorityRunCase(ConductorCase):
    """Runs of fake roles whose executor looks like a Claude Code role with a shell (and names a Codex sandbox for its
    fallback), with the provider sandbox probe replaced."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(engine.sandbox, "probe", return_value=UP)
        patcher.start()
        self.addCleanup(patcher.stop)

    def stand_in(self, *roles_with_shell) -> None:
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in RUN_ROLES + ("report-fixer",)}
        for role in roles_with_shell:
            argv[role] += ["--tools", "Bash,Read,Edit", "--sandbox", "workspace-write"]
        self.write_config(argv)

    def agent_dirs(self, err: str, role: str) -> list:
        folder = self.run_dir(err) / "W1" / agents.AGENTS
        return [path for path in sorted(folder.iterdir())
                if json.loads((path / "request.json").read_text(encoding="utf-8"))["role"] == role]

    def envelopes(self, directory: Path) -> list:
        return [json.loads(path.read_text(encoding="utf-8"))
                for path in sorted((directory / "authority").glob("a*.json"), key=lambda p: int(p.stem[1:]))]

    def said(self, err: str, code: str) -> list:
        return [line for line in self.lines(err) if line.get("reason_code") == code]

    def events(self, kind: str, role: str) -> list:
        stored, _ = journal.read_events(self.project)
        return [event.data for event in stored if event.type == kind and event.data["role"] == role]


class RunTests(AuthorityRunCase):
    def test_f_the_record_is_written_before_the_process_and_named_by_the_result_and_the_event(self):
        self.stand_in("executor")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        seen, real = [], process.run_role

        def launched(argv, prompt, **kwargs):
            seen.append(sorted(path.name for path in (kwargs["agent_directory"] / "authority").glob("*.json")))
            return real(argv, prompt, **kwargs)
        with mock.patch.object(process, "run_role", launched):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        self.assertTrue(seen and all(names == ["a1.json"] for names in seen), seen)  # every process had its record first
        executor = self.agent_dirs(err, "executor")[0]
        envelope = self.envelopes(executor)[0]
        self.assertEqual(contract.problems(envelope, "authority-envelope"), [])
        self.assertEqual((envelope["guard"], envelope["setting_sources"]), ("claude-sandbox", ["user"]))
        result = records.read(executor / "result.json", "agent-result")
        self.assertEqual(result["authority"], [{"attempt": 1, "provider": "claude-code", "digest": envelope["digest"]}])
        finished = self.events("orch.agent.finished", "executor")
        self.assertEqual([event["authority_digests"] for event in finished], [[envelope["digest"]]])
        self.assertNotIn("authority_digests", self.events("orch.agent.started", "executor")[0])
        self.assertNotIn("authority", json.loads((executor / "request.json").read_text(encoding="utf-8")))
        state = self.state(err)["items"]["W1"]["authority"]
        self.assertEqual(state["executor"], envelope["digest"])
        self.assertIn("## Authority", self.prompt("executor", 1))  # (i) the executor is told its authority
        self.assertIn("Docker: not available here", self.prompt("executor", 1))
        self.assertIn("do not start containers or call docker or compose", self.prompt("executor", 1))

    def test_g_two_attempts_of_the_executor_with_another_access_say_authority_changed_once(self):
        self.stand_in("executor")
        marker = self.project.parent / "first-attempt-done"
        self.script({"executor": [{"exit": 1, "stderr": "something odd", "write": {str(marker): "x"}},
                                  executor_ok("W1")], "reviewer": [GREEN]})
        access = mock.patch.object(engine.Conductor, "_launch_access",
                                   lambda owner: "confined" if marker.exists() else "open")
        with access:
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        changed = self.said(err, "AUTHORITY_CHANGED")
        self.assertEqual(len(changed), 1, err)
        self.assertRegex(changed[0]["message"], r"^W1 executor: authority [0-9a-f]{12} -> [0-9a-f]{12} \(access\)$")
        first, second = self.envelopes(self.agent_dirs(err, "executor")[0])
        self.assertEqual((first["access"], second["access"]), ("open", "confined"))

    def test_j_a_fallback_to_another_provider_records_each_attempt_with_its_own_guard(self):
        self.stand_in("executor")
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"fallback_routes": [
            {"role": "executor", "provider": "codex", "model_class": "implementation"}]}}]}})
        self.script({"executor": [quota_failure(3600), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        executor = self.agent_dirs(err, "executor")
        self.assertEqual(len(executor), 1)
        first, second = self.envelopes(executor[0])
        self.assertEqual([(doc["provider"], doc["guard"]) for doc in (first, second)],
                         [("claude-code", "claude-sandbox"), ("codex", "codex-sandbox")])
        self.assertNotEqual(first["digest"], second["digest"])
        result = records.read(executor[0] / "result.json", "agent-result")
        self.assertEqual(result["authority"], [{"attempt": 1, "provider": "claude-code", "digest": first["digest"]},
                                               {"attempt": 2, "provider": "codex", "digest": second["digest"]}])
        self.assertEqual(len(self.said(err, "AUTHORITY_CHANGED")), 1, err)
        self.assertEqual([event["authority_digests"] for event in self.events("orch.agent.finished", "executor")],
                         [[first["digest"], second["digest"]]])

    def sent(self, err: str) -> list:
        """``(prompt sent, envelope recorded)`` of every executor attempt of W1."""
        envelopes = self.envelopes(self.agent_dirs(err, "executor")[0])
        return [(self.prompt("executor", number), doc) for number, doc in enumerate(envelopes, 1)]

    def assert_prompt_matches(self, text: str, envelope: dict) -> None:
        self.assertIn(authority.prompt_block(envelope), text)
        if envelope["docker"] == "open":
            self.assertNotIn("do not start containers", text)
            self.assertIn("container-based ones included", text)
        else:
            self.assertIn("do not start containers or call docker or compose", text)
            self.assertNotIn("container-based ones included", text)

    def test_f1_a_fallback_from_the_claude_sandbox_to_an_open_codex_gets_the_authority_of_its_own_launch(self):
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in RUN_ROLES}
        argv["executor"] += ["--tools", "Bash,Read,Edit"]  # a Claude shell the sandbox confines; an open Codex
        self.write_config(argv)
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {"fallback_routes": [
            {"role": "executor", "provider": "codex", "model_class": "implementation"}]}}]}})
        self.script({"executor": [quota_failure(3600), executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        (first, a1), (second, a2) = self.sent(err)
        self.assertEqual([(doc["guard"], doc["docker"]) for doc in (a1, a2)], [("claude-sandbox", "blocked"), ("none", "open")])
        self.assert_prompt_matches(first, a1)
        self.assert_prompt_matches(second, a2)
        manifest = json.loads((self.run_dir(err) / "W1" / "prompts" / "executor.1.manifest.json").read_text())
        block = next(row for row in manifest["blocks"] if row["kind"] == "authority")
        text = authority.prompt_block(a2) + "\n\n"  # the manifest of the step is the one of its last attempt
        self.assertEqual(block["sha256"], __import__("hashlib").sha256(text.encode("utf-8")).hexdigest())

    def test_f1_a_fallback_from_an_open_codex_to_the_claude_sandbox_loses_the_docker_it_had(self):
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in RUN_ROLES}
        argv["executor"] += ["--tools", "Bash,Read,Edit"]
        self.write_config(argv)
        self.set_items({"W1": {"options": [{"source": "item:W1", "options": {
            "stages": [{"role": "executor", "provider": "codex"}], "fallback_routes": [
                {"role": "executor", "provider": "claude-code", "model_class": "implementation"}]}}]}})
        self.script({"executor": [{"codex_failed": "You’ve hit your usage limit. Try later.", "exit": 1},
                                  executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        (first, a1), (second, a2) = self.sent(err)
        self.assertEqual([(doc["provider"], doc["docker"]) for doc in (a1, a2)], [("codex", "open"), ("claude-code", "blocked")])
        self.assert_prompt_matches(first, a1)
        self.assert_prompt_matches(second, a2)

    def test_f2_dropping_the_default_writable_roots_of_the_guard_is_an_authority_change(self):
        """The guard prefix of round 2 gains --no-default-rw: the digest moves, AUTHORITY_CHANGED is said and the
        executor session starts fresh with the reason authority_digest."""
        wrapper = self.project.parent / "ro-run.py"  # a stand-in guard: runs the command after --
        wrapper.write_text("import subprocess, sys\nsys.exit(subprocess.run(sys.argv[sys.argv.index('--') + 1:]).returncode)\n",
                           encoding="utf-8")
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in RUN_ROLES}
        argv["executor"] = [sys.executable, str(wrapper), "--rw", str(self.project), "--", *argv["executor"]]
        self.write_config(argv, extra='[orch.conductor]\nsession_executor = "handoff"\n')
        marker = self.project.parent / "round-one-done"
        self.script({"executor": [{"result": report("W1"), "write": {str(marker): "x"}}, executor_ok("W1")],
                     "reviewer": [GREEN]})
        real = launch_plan.authority

        def flagged(owner, item, role, route, **kwargs):
            if role == "executor" and marker.exists():
                route = dict(route, argv=[*route["argv"][:2], "--no-default-rw", *route["argv"][2:]])
            return real(owner, item, role, route, **kwargs)
        with mock.patch.object(engine.Conductor, "_authority", flagged):
            code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (0, ("finished", None)), err)
        changed = self.said(err, "AUTHORITY_CHANGED")
        self.assertEqual(len(changed), 1, err)
        self.assertIn("write_roots", changed[0]["message"])
        fresh = [line["message"] for line in self.said(err, "SESSION_FRESH")]
        self.assertEqual(len(fresh), 2, err)
        self.assertIn("reason=fingerprint_changed:authority_digest", fresh[1])

    def test_k_a_crash_of_the_conductor_at_the_launch_keeps_the_record_and_a_resume_starts_a_new_agent_run(self):
        self.stand_in("executor")
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        calls, real = [], process.run_role

        def crash(argv, prompt, **kwargs):
            calls.append(kwargs["agent_directory"])
            if len(calls) == 2:  # the scout ran; the executor dies between its record and its process
                raise KeyboardInterrupt
            return real(argv, prompt, **kwargs)
        with mock.patch.object(process, "run_role", crash):
            code, _, err = self.run_items("W1")
        self.assertNotEqual(code, 0, err)
        crashed = calls[1]
        kept = (crashed / "authority" / "a1.json").read_bytes()
        code, _, again = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertEqual((code, self.outcome(again)), (0, ("finished", None)), again)
        self.assertEqual((crashed / "authority" / "a1.json").read_bytes(), kept)  # never rewritten
        executor = self.agent_dirs(err, "executor")
        self.assertEqual(len(executor), 2)
        self.assertNotEqual(executor[1], crashed)
        self.assertTrue((executor[1] / "authority" / "a1.json").is_file())

    def test_l_the_report_fixer_and_the_batch_roles_record_their_launch(self):
        self.stand_in()
        broken = {"write": {"out/W1.txt": "ok\n"}, "result": report("W1", changed_paths=["out/W1.txt", "out/W1.txt"])}
        self.script({"executor": [broken], "reviewer": [GREEN],
                     "report-fixer": [{"result": report("W1"), "tag": "stage-report"}]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        fixer = self.agent_dirs(err, "report-fixer")
        self.assertEqual(len(fixer), 1)
        self.assertEqual([doc["role"] for doc in self.envelopes(fixer[0])], ["report-fixer"])
        self.assertTrue(records.read(fixer[0] / "result.json", "agent-result")["authority"])
        owner = engine.Conductor.__new__(engine.Conductor)  # a batch role: review_plan.run_agent
        owner.project = owner.directory = self.project
        owner.env, owner.settings, owner.run_id, owner.state, owner.progress = None, None, "", {}, mock.Mock()
        owner.store = mock.Mock()
        owner.store.mutating.side_effect = contextlib.nullcontext
        owner._save, owner._admit_budget, owner._tokens = mock.Mock(), mock.Mock(), mock.Mock()
        directory = self.project.parent / "batch"
        owner._agent_start = lambda item, key, role, route, prompt_file, attempt: {
            "directory": directory / key, "usage": dict.fromkeys(agents.USAGE_KEYS, 0)}
        owner._agent_end = lambda handle, error=None, succeeded=False: agents.finish(
            handle, exit_code=0, error=error, decisions=[], duration_s=0.1, stream=None, lingered=False)
        item = types.SimpleNamespace(ref="W1", directory=directory, state={}, options={
            "instructions": {"isolate_roles": ["reviewer"], "isolation": "prefer", "sandbox": "prefer"}, "scope": {}})
        route = {"provider": "claude-code", "argv": [sys.executable, "-c", "pass"], "transport": "text"}
        with mock.patch.object(process, "run_role", return_value=process.RoleRun(exit=0, text="ok")):
            review_plan._run_agent(owner, item, "group-review-1", "reviewer", route, "prompt", directory / "raw", 30)
        self.assertEqual(json.loads((directory / "group-review-1" / "authority" / "a1.json").read_text())["role"],
                         "reviewer")
        self.assertEqual(item.state["authority"]["reviewer"],
                         records.read(directory / "group-review-1" / "result.json", "agent-result")["authority"][0]["digest"])

    def test_h_the_dry_run_shows_the_authority_of_every_role(self):
        self.stand_in("executor")
        code, out, err = self.conduct("run", "--plan", "T", "--ready", "--dry-run", "--scenario", "full")
        self.assertEqual(code, 0, err)
        preview = json.loads(out)
        self.assertEqual(sorted(preview["authority"]), sorted(preview["routes"]))
        for role, doc in preview["authority"].items():
            with self.subTest(role=role):
                self.assertEqual(contract.problems(doc, "authority-envelope"), [])
        self.assertEqual(preview["authority"]["executor"]["guard"], "claude-sandbox")
        self.assertEqual(preview["network"]["executor"]["by"], "claude-sandbox")

    def test_h_the_invocation_scope_of_the_dry_run_reaches_the_envelope_as_it_reaches_the_launch(self):
        """PREVIEW-SCOPE-001 kept: a CLI-only --allow-path is in the envelope and the full command line of the dry run
        (routes[*].argv stays the base template without it), the same as a launch of the same options; an unsafe
        path is refused by the same validator, and without flags the scope is the default."""
        self.stand_in("executor")
        allowed = self.project.parent / "preview-output"
        allowed.mkdir()
        argv = ("run", "--plan", "T", "--ready", "--dry-run", "--scenario", "full")
        code, out, err = self.conduct(*argv, "--fence", "plan", "--allow-path", str(allowed))
        self.assertEqual(code, 0, err)
        preview = json.loads(out)
        exact = str(allowed.resolve())
        self.assertIn({"path": exact, "why": "extra_paths"}, preview["authority"]["executor"]["write_roots"])
        self.assertNotIn(exact, preview["routes"]["executor"]["argv"])  # the base route template
        full = preview["isolation_args"]["executor"]
        self.assertEqual(full[full.index("--add-dir") + 1], exact)
        self.assertEqual(json.loads(full[full.index("--settings") + 1])["sandbox"]["filesystem"]["allowWrite"], [exact])
        self.assertFalse([root for root in preview["authority"]["reviewer"]["write_roots"]
                          if root["why"] == "extra_paths"])  # only a writer gets the grant
        code, _, err = self.conduct(*argv, "--allow-path", "/")
        self.assertEqual(code, 1)
        self.assertTrue(err.startswith("OPTIONS_UNSAFE_PATH:"), err)
        code, out, err = self.conduct(*argv)
        self.assertEqual(code, 0, err)
        self.assertFalse([root for root in json.loads(out)["authority"]["executor"]["write_roots"]
                          if root["why"] == "extra_paths"])

    def test_m_the_new_fields_pass_the_records_on_save_load_and_resume_and_old_records_stay_valid(self):
        self.stand_in("executor")
        self.script({"executor": [{"result": report("W1", "blocked", open_issues=[{"text": "x", "kind": "escalation"}])},
                                  executor_ok("W1")], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 1, err)
        state = records.read(self.run_dir(err) / engine.STATE_FILE, "state")  # checked on read
        self.assertTrue(state["items"]["W1"]["authority"]["executor"].startswith("sha256:"))
        code, _, again = self.conduct("resume", "--run", self.run_dir(err).name, "--retry", "W1", "--json-lines")
        self.assertEqual((code, self.outcome(again)), (0, ("finished", None)), again)
        for path in (self.run_dir(err) / "W1" / agents.AGENTS).glob("*/result.json"):
            records.read(path, "agent-result")
        legacy = self.project.parent / "legacy-result.json"
        legacy.write_text(json.dumps({"exit": 0, "decisions": [], "duration_s": 1.0, "stream": None, "lingered": False}),
                          encoding="utf-8")
        self.assertNotIn("authority", records.read(legacy, "agent-result"))  # written before P6.2: still valid
        old_state = json.loads((ORCH_ROOT / "schemas" / "records" / "v1" / "examples" / "valid" / "state" /
                                "green.json").read_text(encoding="utf-8"))
        self.assertFalse(any("authority" in piece for piece in old_state["items"].values()))
        self.assertEqual(records.problems(old_state, "state"), [])


if __name__ == "__main__":
    unittest.main()
