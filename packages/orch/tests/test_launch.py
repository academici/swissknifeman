from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from orch import launch

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SCOUT = ["claude", "-p", "--model", "haiku", "--effort", "low", "--tools", "Read,Grep,Glob",
                "--permission-prompts", "none", "--no-session-persistence"]
CODEX_SCOUT = ["codex", "-a", "never", "exec", "--sandbox", "read-only", "--model", "gpt-5.6-luna", "-c",
               'model_reasoning_effort="low"', "--ephemeral", "-"]


class LaunchCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = launch.load_catalog()

    def broken(self, mutate):
        catalog = copy.deepcopy(self.catalog)
        mutate(catalog["launch"])
        with self.assertRaises(launch.LaunchError) as raised:
            launch.validate_catalog(catalog)
        self.assertEqual(raised.exception.code, "LAUNCH_INVALID")
        return str(raised.exception)

    def test_repository_catalog_is_valid_and_complete(self):
        rows = [(role, provider) for role, providers in self.catalog["launch"].items() for provider in providers]
        self.assertEqual(len(rows), 18)
        self.assertEqual({provider for role, provider in rows if role == "triager"}, {"claude-code", "codex"})
        self.assertEqual({role for role, _ in rows}, set(launch.ROLES))
        self.assertNotIn(("scout", "grok"), rows)

    def test_scout_argv_matches_previous_lists(self):
        self.assertEqual(launch.build_argv(self.catalog, "scout", "claude-code", model="haiku"), CLAUDE_SCOUT)
        self.assertEqual(launch.build_argv(self.catalog, "scout", "codex", model="gpt-5.6-luna"), CODEX_SCOUT)

    def test_catalog_names_no_model(self):
        text = json.dumps(self.catalog)
        for name in ("haiku", "sonnet", "opus", "gpt-", "grok-4"):
            self.assertNotIn(name, text)

    def test_effort_override_and_cwd(self):
        argv = launch.build_argv(self.catalog, "executor", "claude-code", model="sonnet", effort="xhigh", cwd="/w")
        self.assertEqual(argv[argv.index("--effort") + 1], "xhigh")
        self.assertEqual(launch.build_argv(self.catalog, "executor", "grok"), ["grok", "agent", "stdio"])

    def test_grok_reviewer_runs_read_only_under_landlock(self):
        argv = launch.build_argv(self.catalog, "reviewer", "grok", model="m-1", effort="xhigh", cwd="/w")
        split = argv.index("--")
        self.assertEqual(argv[:split], ["python3", str(launch.ORCH_ROOT / "scripts" / "ro-run.py"), "--rw", "/w/vendor"])
        self.assertTrue((launch.ORCH_ROOT / "scripts" / "ro-run.py").is_file())
        grok = argv[split + 1:]
        self.assertEqual(grok[:3], ["grok", "--cwd", "/w"])
        for flag, value in (("--prompt-file", "/dev/stdin"), ("--model", "m-1"), ("--effort", "xhigh"),
                            ("--permission-mode", "bypassPermissions"), ("--disallowed-tools", "search_replace,write"),
                            ("--output-format", "streaming-messages-json")):
            self.assertEqual(grok[grok.index(flag) + 1], value)
        self.assertEqual(launch.entry(self.catalog, "reviewer", "grok")["transport"], "jsonl")

    def test_claude_code_roles_list_their_tools(self):
        # --tools cuts the start-up context of an isolated role from ≈14 K to ≈7 K tokens (measured, P12 prep);
        # --allowedTools alone only skips the permission prompt and leaves every tool definition in the context.
        for role, tools in {"executor": "Bash,Read,Edit,Write,Grep,Glob", "reviewer": "Bash,Read,Grep,Glob",
                            "triager": "Bash,Read,Grep,Glob"}.items():
            argv = launch.build_argv(self.catalog, role, "claude-code", model="sonnet")
            self.assertIn("--tools", argv, role)
            self.assertEqual(argv[argv.index("--tools") + 1], tools, role)

    def test_claude_code_print_roles_never_prompt(self):
        # --permission-prompts none: a headless role must not wait for an answer nobody gives (denied instead).
        claude = [(role, entry) for role, providers in self.catalog["launch"].items()
                  for provider, entry in providers.items() if provider == "claude-code" and "-p" in entry["argv"]]
        self.assertTrue(claude)
        for role, entry in claude:
            argv = entry["argv"]
            self.assertEqual(argv[argv.index("--permission-prompts") + 1], "none", role)
            self.assertNotIn("--bare", argv, role)  # D15: bare does not read the subscription OAuth

    def test_bounded_implementer_is_confined_like_executor(self):
        argv = launch.build_argv(self.catalog, "bounded-implementer", "claude-code", model="sonnet", cwd="/w")
        self.assertTrue(argv[1].endswith("ro-run.py"))
        self.assertIn("--", argv)  # ro-run refuses a command line without it
        self.assertEqual(argv[argv.index("--") + 1], "claude")
        self.assertEqual(argv[argv.index("--rw") + 1], "/w")
        self.assertEqual(argv[argv.index("--tools") + 1], "Bash,Read,Edit,Write,Grep,Glob")
        self.assertEqual(argv[argv.index("--allowedTools") + 1], "Bash")

    def test_bare_is_forbidden(self):
        self.assertIn("--bare", self.broken(lambda l: l["scout"]["codex"]["argv"].append("--bare")))

    def test_unknown_placeholder(self):
        self.assertIn("placeholder", self.broken(lambda l: l["scout"]["codex"]["argv"].append("{home}")))

    def test_unknown_role_provider_and_extra_key(self):
        self.broken(lambda l: l.update(janitor=l["scout"]))
        self.broken(lambda l: l["scout"].update(gemini=l["scout"]["codex"]))
        self.broken(lambda l: l["scout"]["codex"].update(extra=1))

    def test_scout_needs_text_transport(self):
        self.assertIn("plain text", self.broken(lambda l: l["scout"]["codex"].update(transport="jsonl")))

    def test_model_placeholder_matches_model_set(self):
        self.broken(lambda l: l["scout"]["codex"].update(argv=["codex", "exec", "-"]))
        self.broken(lambda l: l["executor"]["grok"].update(argv=["grok", "--model", "{model}"]))

    def test_bad_values(self):
        self.broken(lambda l: l["scout"]["codex"].update(timeout_s=0))
        self.broken(lambda l: l["scout"]["codex"].update(timeout_s=True))
        self.broken(lambda l: l["scout"]["codex"].update(model_class="huge"))
        self.broken(lambda l: l["scout"]["codex"].update(argv=[]))

    def test_lookup_and_request_errors(self):
        with self.assertRaises(launch.LaunchError) as raised:
            launch.build_argv(self.catalog, "scout", "grok", model="m")
        self.assertEqual(raised.exception.code, "LAUNCH_UNKNOWN")
        with self.assertRaises(launch.LaunchError):
            launch.build_argv(self.catalog, "scout", "codex")
        with self.assertRaises(launch.LaunchError):
            launch.build_argv(self.catalog, "scout", "codex", model="m", effort="max")

    def test_cli_argv_and_refusal(self):
        script = str(ROOT / "scripts" / "orch.py")
        done = subprocess.run([sys.executable, script, "launch", "argv", "scout", "claude-code", "--model", "haiku"],
                              capture_output=True, text=True, check=False)
        self.assertEqual(done.returncode, 0)
        self.assertEqual(json.loads(done.stdout)["argv"], CLAUDE_SCOUT)
        refused = subprocess.run([sys.executable, script, "launch", "argv", "scout", "grok"],
                                 capture_output=True, text=True, check=False)
        self.assertEqual(refused.returncode, 1)
        self.assertTrue(refused.stderr.startswith("LAUNCH_UNKNOWN:"))


if __name__ == "__main__":
    unittest.main()
