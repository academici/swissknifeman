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
READ_ONLY_DENY = ("search_replace,write,spawn_subagent,scheduler_create,scheduler_delete,workflow,"
                  "image_gen,image_edit,image_to_video,reference_to_video")


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
        self.assertEqual(len(rows), 24)
        self.assertEqual({provider for role, provider in rows if role == "triager"}, {"claude-code", "codex", "grok"})
        self.assertEqual({role for role, _ in rows}, set(launch.ROLES))
        self.assertIn(("scout", "grok"), rows)

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

    def test_grok_writers_use_jsonl_under_landlock_with_only_the_checkout_grant(self):
        for role, model_class, effort, timeout in (("executor", "implementation", "high", 3600),
                                                  ("bounded-implementer", "economy", "medium", 1800)):
            with self.subTest(role=role):
                argv = launch.build_argv(self.catalog, role, "grok", model="m-1", cwd="/w")
                entry = launch.entry(self.catalog, role, "grok")
                self.assertEqual(argv[:argv.index("--")],
                                 ["python3", str(ROOT / "scripts/ro-run.py"), "--rw", "/w"])
                for flag, value in (("--cwd", "/w"), ("--prompt-file", "/dev/stdin"), ("--model", "m-1"),
                                    ("--effort", effort), ("--permission-mode", "bypassPermissions"),
                                    ("--output-format", "streaming-messages-json")):
                    self.assertEqual(argv[argv.index(flag) + 1], value)
                self.assertNotIn("--disallowed-tools", argv)
                self.assertNotIn("--protect", argv)
                self.assertEqual((entry["transport"], entry["model_set"], entry["model_class"], entry["timeout_s"]),
                                 ("jsonl", "supported", model_class, timeout))

    def test_synthetic_acp_entry_still_builds_without_a_model(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["launch"]["executor"]["grok"].update(
            transport="acp", model_set="unknown", argv=["grok", "agent", "stdio"])
        launch.validate_catalog(catalog)
        self.assertEqual(launch.build_argv(catalog, "executor", "grok"), ["grok", "agent", "stdio"])

    def test_grok_reviewer_runs_read_only_under_landlock(self):
        argv = launch.build_argv(self.catalog, "reviewer", "grok", model="m-1", effort="xhigh", cwd="/w")
        split = argv.index("--")
        self.assertEqual(argv[:split], ["python3", str(launch.ORCH_ROOT / "scripts" / "ro-run.py"),
                                       "--protect", "/w", "--rw", "/w/vendor"])
        self.assertTrue((launch.ORCH_ROOT / "scripts" / "ro-run.py").is_file())
        grok = argv[split + 1:]
        self.assertEqual(grok[:3], ["grok", "--cwd", "/w"])
        for flag, value in (("--prompt-file", "/dev/stdin"), ("--model", "m-1"), ("--effort", "xhigh"),
                            ("--permission-mode", "bypassPermissions"), ("--disallowed-tools", READ_ONLY_DENY),
                            ("--output-format", "streaming-messages-json")):
            self.assertEqual(grok[grok.index(flag) + 1], value)
        self.assertEqual(launch.entry(self.catalog, "reviewer", "grok")["transport"], "jsonl")

    def test_grok_report_fixer_has_protection_and_cannot_call_shell(self):
        argv = launch.build_argv(self.catalog, "report-fixer", "grok", model="m-1", cwd="/w")
        self.assertEqual(argv[:argv.index("--")], ["python3", str(ROOT / "scripts/ro-run.py"), "--protect", "/w"])
        self.assertEqual(set(argv[argv.index("--disallowed-tools") + 1].split(",")),
                         set(READ_ONLY_DENY.split(",")) | {"run_terminal_command"})
        self.assertEqual(argv[argv.index("--output-format") + 1], "streaming-messages-json")

    def test_new_grok_roles_have_the_contracted_limits_and_tools(self):
        for role, model_class, effort, timeout in (("scout", "economy", "low", 300),
                                                  ("triager", "implementation", "medium", 1800),
                                                  ("researcher", "implementation", "medium", 1800),
                                                  ("advisor", "frontier", "high", 1800)):
            with self.subTest(role=role):
                entry = launch.entry(self.catalog, role, "grok")
                argv = launch.build_argv(self.catalog, role, "grok", model="m", cwd="/w")
                guard = ["python3", str(ROOT / "scripts/ro-run.py"), "--protect", "/w"]
                if role == "triager":
                    guard += ["--rw", "/w/vendor"]
                self.assertEqual(argv[:argv.index("--")], guard)
                self.assertEqual((entry["model_class"], entry["effort"], entry["timeout_s"], entry["model_set"]),
                                 (model_class, effort, timeout, "supported"))
                denied = argv[argv.index("--disallowed-tools") + 1]
                self.assertEqual(denied, READ_ONLY_DENY)
                self.assertNotIn("run_terminal_command", denied.split(","))
                self.assertNotIn("web_search", denied.split(","))
                self.assertEqual("--disable-web-search" in argv, role == "scout")

    def test_claude_code_roles_list_their_tools(self):
        # --tools cuts the start-up context of an isolated role from ≈14 K to ≈7 K tokens (measured, P12 prep);
        # --allowedTools alone only skips the permission prompt and leaves every tool definition in the context.
        for role, tools in {"executor": "Bash,Read,Edit,Write,Grep,Glob", "reviewer": "Bash,Read,Grep,Glob",
                            "triager": "Bash,Read,Grep,Glob", "researcher": "Bash,Read,Grep,Glob",
                            "advisor": "Bash,Read,Grep,Glob"}.items():
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
        self.broken(lambda l: l["executor"]["grok"].update(model_set="unknown"))

    def test_bad_values(self):
        self.broken(lambda l: l["scout"]["codex"].update(timeout_s=0))
        self.broken(lambda l: l["scout"]["codex"].update(timeout_s=True))
        self.broken(lambda l: l["scout"]["codex"].update(model_class="huge"))
        self.broken(lambda l: l["scout"]["codex"].update(argv=[]))

    def test_lookup_and_request_errors(self):
        with self.assertRaises(launch.LaunchError) as raised:
            launch.build_argv(self.catalog, "janitor", "grok", model="m")
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
        grok = subprocess.run([sys.executable, script, "launch", "argv", "scout", "grok", "--model", "m"],
                              capture_output=True, text=True, check=False)
        self.assertEqual(grok.returncode, 0, grok.stderr)
        self.assertEqual(json.loads(grok.stdout)["transport"], "text")
        refused = subprocess.run([sys.executable, script, "launch", "argv", "registrar", "grok"],
                                 capture_output=True, text=True, check=False)
        self.assertEqual(refused.returncode, 1)
        self.assertTrue(refused.stderr.startswith("LAUNCH_REFUSED: registrar/grok:"), refused.stderr)

    def test_catalog_without_refusals_remains_valid_and_missing_pairs_stay_unknown(self):
        catalog = copy.deepcopy(self.catalog)
        catalog.pop("refusals", None)
        launch.validate_catalog(catalog)
        with self.assertRaises(launch.LaunchError) as raised:
            launch.entry(catalog, "registrar", "grok")
        self.assertEqual(raised.exception.code, "LAUNCH_UNKNOWN")

    def test_refused_pairs_preserve_the_exact_reason_in_entry_and_build_argv(self):
        self.assertEqual({(role, provider) for role, providers in self.catalog["refusals"].items()
                          for provider in providers},
                         {("registrar", "grok"), ("researcher", "codex"), ("advisor", "codex")})
        for role, providers in self.catalog["refusals"].items():
            for provider, reason in providers.items():
                for lookup in (launch.entry, launch.build_argv):
                    with self.subTest(role=role, provider=provider, lookup=lookup.__name__):
                        with self.assertRaises(launch.LaunchError) as raised:
                            lookup(self.catalog, role, provider)
                        self.assertEqual(raised.exception.code, "LAUNCH_REFUSED")
                        self.assertEqual(str(raised.exception), f"{role}/{provider}: {reason}")

    def test_refusals_reject_unknown_keys_bad_shapes_and_invalid_reasons(self):
        for refusals in (None, [], {"janitor": {"grok": "no"}}, {"scout": []},
                         {"scout": {"gemini": "no"}},
                         *({"registrar": {"grok": reason}} for reason in (None, 1, "", " \n", "x" * 301))):
            with self.subTest(refusals=refusals):
                catalog = copy.deepcopy(self.catalog)
                catalog["refusals"] = refusals
                with self.assertRaises(launch.LaunchError) as raised:
                    launch.validate_catalog(catalog)
                self.assertEqual(raised.exception.code, "LAUNCH_INVALID")

    def test_refusals_reject_a_pair_also_present_in_launch(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["refusals"] = {"scout": {"grok": "explicit refusal"}}
        with self.assertRaises(launch.LaunchError) as raised:
            launch.validate_catalog(catalog)
        self.assertEqual(raised.exception.code, "LAUNCH_INVALID")
        self.assertIn("both launch and refusals", str(raised.exception))

    def test_refusal_reason_length_boundary_and_extra_top_level_key(self):
        catalog = copy.deepcopy(self.catalog)
        catalog["refusals"] = {"registrar": {"grok": "x" * 300}}
        launch.validate_catalog(catalog)
        catalog["extra"] = {}
        with self.assertRaises(launch.LaunchError) as raised:
            launch.validate_catalog(catalog)
        self.assertEqual(raised.exception.code, "LAUNCH_INVALID")


if __name__ == "__main__":
    unittest.main()
