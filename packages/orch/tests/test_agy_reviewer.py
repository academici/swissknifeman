"""The owner exception admits only a protected local reviewer and records its remaining authority."""
from pathlib import Path
import json
import os
import platform
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from orch import catalog, contracts, launch
from orch.conductor import contract, process, prompts
from orch.conductor.application import retry_service, route_service
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import launch_plan
from orch.conductor.policies import authority
from tests.test_conductor import ConductorCase, FIXTURES, ROLES


class AntigravityReviewerTests(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="agy-reviewer-")
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.project = self.root / "checkout"
        self.project.mkdir()
        self.tmpdir = self.root / "agent/tmp"
        self.tmpdir.mkdir(parents=True)
        self.env = {**os.environ, launch.AGY_OPT_IN: "", launch.AGY_REVIEW_OPT_IN: launch.AGY_OPT_IN_VALUE}
        self.route = {"role": "reviewer", "provider": "antigravity", "transport": "jsonl",
                      "model": "gemini-4-argon-high", "effort": "high"}
        self.route["argv"] = launch.build_argv(launch.load_catalog(), "reviewer", "antigravity",
                                               model=self.route["model"], effort="high", cwd=str(self.project))
        self.item = SimpleNamespace(options={}, output_write_dirs=[str(self.root / "outputs")])
        self.owner = SimpleNamespace(project=self.project, env=self.env, directory=self.root,
            _local=SimpleNamespace(agent={"directory": self.tmpdir.parent}),
            role_ports=SimpleNamespace(note_isolation=lambda *a: None,
                launch_facts=lambda *a, **kw: {"sandbox": {}, "access": "confined", "declared_network": "none"}),
            _scope_option=lambda *a: [], provider_disabled=lambda provider: None,
            _launch_access=lambda: "confined", _codex_sandboxed=lambda route: False)
        self.isolation = {"mode": "off", "isolated": False, "guarantee": "none", "env": {},
                          "home": None, "degraded": []}
        self.enterContext(patch.object(launch_plan, "isolation_plan", return_value=self.isolation))

    def envelope(self, **changes):
        return launch_plan.authority(self.owner, self.item, "reviewer", {**self.route, **changes})

    def test_opt_in_is_exact_separate_and_read_from_the_run_environment(self):
        for value in ("", "yes", "1"):
            self.owner.env[launch.AGY_REVIEW_OPT_IN] = value
            self.owner.env[launch.AGY_OPT_IN] = launch.AGY_OPT_IN_VALUE
            with patch.dict(os.environ, {launch.AGY_REVIEW_OPT_IN: launch.AGY_OPT_IN_VALUE}):
                self.assertTrue(route_service.route_problem(self.owner, self.route).startswith("AGY_AUTHORITY_UNPROVEN"))
        self.owner.env = self.env = {launch.AGY_REVIEW_OPT_IN: launch.AGY_OPT_IN_VALUE}
        for role in ("executor", "bounded-implementer", "triager", "researcher", "advisor", None):
            self.assertFalse(launch.agy_role_opted_in(role, self.env))
        with patch("orch.conductor.application.route_service.process.available", return_value=True), \
             patch("orch.conductor.application.route_service.gates.blocked", return_value=None):
            self.assertIsNone(route_service.route_problem(self.owner, self.route))

    def test_named_unknown_model_requires_exact_selector_and_separate_reviewer_opt_in(self):
        from aicore.provider.models import load_model_catalog
        self.owner._catalog_get = lambda: SimpleNamespace(models=load_model_catalog())
        chosen = {**self.route, "model_class": "implementation"}
        self.assertEqual(route_service.named_model_class(self.owner, self.item, "reviewer",
                                                        {"model": chosen["model"]}, chosen), chosen)
        for role, target, model in (("executor", chosen["model"], chosen["model"]),
                                    ("reviewer", None, chosen["model"]),
                                    ("reviewer", "other", "other")):
            with self.assertRaises(Stop):
                route_service.named_model_class(self.owner, self.item, role, {"model": target},
                                                 {**chosen, "model": model})

    def test_envelope_discloses_open_boundaries_and_grants_no_checkout_or_output_writes(self):
        with patch.object(launch_plan, "landlock_abi", return_value=3), \
             patch.object(launch_plan.platform, "machine", return_value="x86_64"):
            doc = self.envelope()
        self.assertEqual(contract.problems(doc, "authority-envelope"), [])
        self.assertEqual(doc["digest"], authority.digest(doc))
        self.assertEqual(doc["guard"], "landlock-protect")
        self.assertEqual((doc["network"]["effective"], doc["docker"], doc["read_masks"]), ("open", "open", "none"))
        self.assertEqual([row["why"] for row in doc["write_roots"]], ["guard", "tmpdir"])
        self.assertEqual(doc["write_roots"][0]["path"], "/dev")
        self.assertIn("AGY_UNSAFE_REVIEWER_OPT_IN", [row["code"] for row in doc["degraded"]])
        command = launch_plan.argv_from(doc, self.route, [], shared=False, project=str(self.project))
        self.assertNotIn("--rw-strict", command)
        self.assertEqual(command[command.index("--rw") + 1], "/dev")
        env = launch_plan.role_env(self.owner, self.item, "reviewer", self.route)
        self.assertEqual(env["HOME"], str(self.tmpdir))
        self.assertNotIn(launch.AGY_OPT_IN, env)
        self.assertNotIn(launch.AGY_REVIEW_OPT_IN, env)
        prompt = authority.prompt_block(doc)
        for text in ("metadata", "host reads", "not isolated", "Docker", "do not change files", "/dev/shm"):
            self.assertIn(text, prompt)
        self.owner._stub = lambda *a: ("", "")
        self.owner._authority = lambda *a, **kw: doc
        blocks = retry_service.routed_blocks(self.owner, "reviewer", self.route,
                                             [prompts.Block("role_text", "reviewer", "Review")], self.item)
        self.assertIn(prompt, prompts.render(blocks))

    def test_opt_in_cannot_admit_writable_or_custom_guards_resume_or_extra_paths(self):
        with patch.object(launch_plan, "landlock_abi", return_value=3), \
             patch.object(launch_plan.platform, "machine", return_value="x86_64"):
            variants = [["custom"],
                        [arg for arg in self.route["argv"] if arg != "--metadata-guard"],
                        self.route["argv"][:2] + ["--rw", str(self.project)] + self.route["argv"][2:]]
            for argv in variants:
                with self.subTest(argv=argv), self.assertRaises(Stop) as caught:
                    self.envelope(argv=argv)
                self.assertEqual(caught.exception.code, "AGY_GUARD_REQUIRED")
            with self.assertRaises(Stop):
                self.envelope(resume_argv=["custom"])
            self.owner._scope_option = lambda *a: ["/extra"]
            with self.assertRaises(Stop):
                self.envelope()

    def test_missing_kernel_or_metadata_support_fails_closed(self):
        for abi, machine in ((2, "x86_64"), (3, "aarch64")):
            with self.subTest(abi=abi, machine=machine), \
                 patch.object(launch_plan, "landlock_abi", return_value=abi), \
                 patch.object(launch_plan.platform, "machine", return_value=machine), self.assertRaises(Stop) as caught:
                self.envelope()
            self.assertEqual(caught.exception.code, "PROTECT_UNAVAILABLE")

    def test_native_projection_requires_the_separate_opt_in_without_changing_capability_claims(self):
        from orch.bindings import Native, load_capabilities
        from orch.port import PortError
        fixtures = launch.ORCH_ROOT / "fixtures/exec/v1/valid"
        input_doc = json.loads((fixtures / "execution-input/plan-bound.json").read_text())
        policy = json.loads((fixtures / "run-policy/review-only.json").read_text())
        roles = {path.stem: json.loads(path.read_text()) for path in (launch.ORCH_ROOT / "roles").glob("*.json")}
        engine = Native(self.root / "prepared", catalog=catalog.Catalog.load())
        with patch.dict(os.environ, {launch.AGY_OPT_IN: launch.AGY_OPT_IN_VALUE, launch.AGY_REVIEW_OPT_IN: ""}):
            with self.assertRaises(PortError):
                engine.prepare(input_doc, policy, roles, provider="antigravity")
        with patch.dict(os.environ, {launch.AGY_REVIEW_OPT_IN: launch.AGY_OPT_IN_VALUE}):
            doc = engine.prepare(input_doc, policy, roles, provider="antigravity")
        self.assertEqual(contracts.validate(doc, "launch-plan"), [])
        (stage,) = doc["stages"]
        self.assertEqual(stage["role"], "reviewer")
        self.assertIn("--metadata-guard", stage["argv"])
        self.assertIn("--protect", stage["argv"])
        self.assertIn("AGY_UNSAFE_REVIEWER_OPT_IN", [row["code"] for row in doc["proof"]["warnings"]])
        self.assertEqual(load_capabilities()[("native", "antigravity")]["restrictions"]["tools_native"], "unsupported")

    def test_real_guard_protects_contents_and_metadata_in_provider_descendants(self):
        if launch_plan.landlock_abi() < 3 or platform.machine() != "x86_64":
            self.skipTest("Landlock ABI 3 and x86-64 seccomp required")
        sentinel = self.project / "sentinel"
        sentinel.write_text("original")
        before = sentinel.stat()
        executable = self.root / "agy"
        canary = """from pathlib import Path
import os,sys
p=Path(sys.argv[1])
for action in (lambda:p.write_text('bad'),lambda:p.chmod(0o777),lambda:os.utime(p,(1,1)),lambda:p.unlink()):
 try: action()
 except PermissionError: pass
 else: sys.exit(9)
# Native AGY uses a PTY even for noninteractive run_command calls.
import fcntl, termios, subprocess, array
master, slave = os.openpty()
attrs = termios.tcgetattr(slave)
termios.tcsetattr(slave, termios.TCSANOW, attrs)
fcntl.ioctl(slave, termios.TIOCSWINSZ, b'\\x18\\x00\\x50\\x00\\x00\\x00\\x00\\x00')
def terminal():
 os.setsid()
 fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
subprocess.run(['/bin/sh', '-c', 'printf terminal-ok'], stdin=slave, stdout=slave,
               stderr=slave, preexec_fn=terminal, check=True)
assert b'terminal-ok' in os.read(master, 1024)
# A terminal allowlist must not reopen filesystem mutation or terminal injection.
with p.open('rb') as handle:
 for request in (0x40086602, 0x40049409, 0x5412):
  try: fcntl.ioctl(handle, request, array.array('i', [0]))
  except PermissionError: pass
  else: sys.exit(10)
os.close(master); os.close(slave)
Path(os.environ['TMPDIR'],'canary').write_text('allowed')
"""
        source = ("#!" + sys.executable + "\nimport json,subprocess,sys\nsys.stdin.read()\n"
                  + "subprocess.run([sys.executable,'-c'," + repr(canary) + "," + repr(str(sentinel)) + "],check=True)\n"
                  + "print(json.dumps({'event':'init','conversation_id':'observed','init':{'model':'gemini-4-argon-high'}}))\n"
                  + "print(json.dumps({'event':'result','result':{'conversation_id':'observed','status':'SUCCESS','response':'reviewed'}}))\n")
        executable.write_text(source)
        executable.chmod(0o700)
        doc = self.envelope()
        command = launch_plan.argv_from(doc, self.route, [], shared=False, project=str(self.project))
        env = launch_plan.role_env(self.owner, self.item, "reviewer", self.route)
        env["PATH"] = str(self.root) + os.pathsep + os.environ["PATH"]
        result = process.run_role(command, "review the synthetic checkout", transport="jsonl", cwd=self.project,
                                  timeout_s=5, raw_path=self.root / "raw.jsonl", env=env, provider="antigravity")
        self.assertIsNone(result.error)
        self.assertEqual((result.exit, result.text, result.session), (0, "reviewed", "observed"))
        self.assertEqual(sentinel.read_text(), "original")
        after = sentinel.stat()
        self.assertEqual((after.st_mode, after.st_mtime_ns), (before.st_mode, before.st_mtime_ns))
        self.assertEqual((self.tmpdir / "canary").read_text(), "allowed")


class AntigravityReviewerConductorTests(ConductorCase):
    def test_review_only_uses_the_shipped_guard_and_records_the_owner_exception(self):
        from orch import adhoc
        if launch_plan.landlock_abi() < 3 or platform.machine() != "x86_64":
            self.skipTest("Landlock ABI 3 and x86-64 seccomp required")
        self.write_config(argv={role: [sys.executable, str(FIXTURES / "fake_role.py"), role]
                                for role in ROLES if role != "reviewer"})
        self.script({"triager": [{"result": {"confirmed": [], "rejected": []}}]})
        executable = self.project.parent / "agy"
        executable.write_text("#!" + sys.executable + "\n" + """import json,os,sys
from pathlib import Path
prompt=json.loads(sys.stdin.readline())['message']['content']
assert 'network, IPC (including Docker), host reads and external' in prompt, prompt
assert 'SKM_ORCH_AGY_UNSAFE_REVIEWER' not in os.environ
try: Path('README.md').write_text('bad')
except PermissionError: pass
else: sys.exit(9)
print(json.dumps({'event':'init','conversation_id':'observed-review','init':{'model':'gemini-4-argon-high'}}))
response='```review-findings\\n'+json.dumps({'verdict':'GREEN','findings':[]})+'\\n```'
print(json.dumps({'event':'result','result':{'conversation_id':'observed-review','status':'SUCCESS','response':response}}))
""")
        executable.chmod(0o700)
        doc = adhoc.build_adhoc_input(None, [], review="HEAD..WORKTREE")
        path = self.project.parent / "review.json"
        path.write_text(json.dumps(doc))
        options = self.project.parent / "options.json"
        options.write_text(json.dumps({"reviewer": "antigravity/gemini-4-argon-high/high", "fallback_routes": []}))
        before = (self.project / "README.md").read_text()
        with patch.dict(os.environ, {launch.AGY_REVIEW_OPT_IN: launch.AGY_OPT_IN_VALUE,
                                    "PATH": str(executable.parent) + os.pathsep + os.environ["PATH"]}):
            code, output, err = self.conduct("run", "--input", path, "--options", options, "--json-lines")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(output.splitlines()[-1])["verdict"], "GREEN")
        self.assertEqual((self.project / "README.md").read_text(), before)
        envelopes = [json.loads(p.read_text()) for p in self.run_dir(err).rglob("authority/a1.json")]
        reviewer = next(row for row in envelopes if row["role"] == "reviewer")
        self.assertIn("AGY_UNSAFE_REVIEWER_OPT_IN", [row["code"] for row in reviewer["degraded"]])
