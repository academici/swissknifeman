"""The seven launch-matrix invariants: coverage, effects, confinement, transports and decoding.

These inspect command lines and recorded streams only; no provider is started.
"""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from orch import catalog, launch
from orch.conductor import process
from orch.conductor.policies.routing import LAUNCH_ROLE

ROOT = Path(__file__).resolve().parents[1]
WRITERS = {"executor", "bounded-implementer"}
READ_ONLY = {"scout", "reviewer", "triager", "researcher", "advisor"}
READ_ONLY_DENY = {"search_replace", "write", "spawn_subagent", "scheduler_create", "scheduler_delete", "workflow",
                  "image_gen", "image_edit", "image_to_video", "reference_to_video"}
# The registrar writes through the plan channel. Its existing Codex workspace-write entry is retained;
# it is the sole exception to the read-only sandbox checks, not permission for other read-only roles.
READ_ONLY_EXCEPTIONS = {("registrar", "codex")}


def flag_values(argv, flag):
    return [argv[index + 1] for index, arg in enumerate(argv) if arg == flag]


class LaunchMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = launch.load_catalog()
        cls.entries = [(role, provider, entry) for role, providers in cls.catalog["launch"].items()
                       for provider, entry in providers.items()]
        cls.manifests = {doc["role_id"]: doc for path in (ROOT / "roles").glob("*.json")
                         for doc in [json.loads(path.read_text(encoding="utf-8"))]}

    def test_1_every_pair_is_launched_or_refused_and_manifests_map_to_launch_roles(self):
        self.assertEqual(len(launch.ROLES), 9)
        for role in launch.ROLES:
            for provider in launch.PROVIDERS:
                with self.subTest(role=role, provider=provider):
                    self.assertEqual(int(provider in self.catalog["launch"][role])
                                     + int(provider in self.catalog.get("refusals", {}).get(role, {})), 1)
        self.assertEqual(len(self.manifests), 8)
        mapped = [LAUNCH_ROLE.get(role, role) for role in self.manifests]
        self.assertEqual(len(mapped), len(set(mapped)))
        # report-fixer is a launch role with no role manifest: its prompt repairs result syntax only.
        self.assertEqual(set(mapped), set(launch.ROLES) - {"report-fixer"})

    def test_2_role_effect_classes_match_the_manifests(self):
        classes = [WRITERS, READ_ONLY, {"registrar"}, {"report-fixer"}]
        self.assertEqual(set.union(*classes), set(launch.ROLES))
        self.assertEqual(sum(map(len, classes)), len(launch.ROLES))
        for role, doc in self.manifests.items():
            role = LAUNCH_ROLE.get(role, role)
            with self.subTest(role=role):
                if role in WRITERS:
                    self.assertEqual(doc["write_authority"], "code_scope")
                    self.assertEqual(doc["tools"]["filesystem"], "write")
                    self.assertEqual(doc["tools"]["plan_api"], "none")
                elif role in READ_ONLY:
                    self.assertEqual(doc["write_authority"], "none")
                    self.assertEqual(doc["tools"]["filesystem"], "read")
                    self.assertEqual(doc["tools"]["plan_api"], "none")
                else:
                    self.assertEqual(role, "registrar")
                    self.assertEqual(doc["write_authority"], "plan")
                    self.assertEqual(doc["tools"]["plan_api"], "write")

    def assert_grok_read_only(self, argv):
        self.assertEqual(argv[:2], ["python3", "{orch}/scripts/ro-run.py"])
        guard = argv[:argv.index("--")]
        self.assertEqual(flag_values(guard, "--protect"), ["{cwd}"])
        self.assertTrue(set(flag_values(guard, "--rw")) <= {"{cwd}/vendor"}, guard)
        self.assertTrue(READ_ONLY_DENY <= set(flag_values(argv, "--disallowed-tools")[0].split(",")))

    def test_3_read_only_launches_cannot_write_the_checkout(self):
        used_exceptions = set()
        for role, provider, entry in self.entries:
            if role not in READ_ONLY | {"registrar"}:
                continue
            argv = entry["argv"]
            with self.subTest(role=role, provider=provider):
                if (role, provider) in READ_ONLY_EXCEPTIONS:
                    used_exceptions.add((role, provider))
                    self.assertEqual(flag_values(argv, "--sandbox"), ["workspace-write"])
                elif provider == "claude-code":
                    tools = flag_values(argv, "--tools")
                    denied = flag_values(argv, "--disallowedTools")
                    self.assertTrue((tools and not {"Edit", "Write", "NotebookEdit"} & set(tools[0].split(",")))
                                    or (denied and {"Edit", "Write"} <= set(denied[0].split(","))))
                elif provider == "codex":
                    self.assertEqual(flag_values(argv, "--sandbox"), ["read-only"])
                else:
                    self.assert_grok_read_only(argv)
        self.assertEqual(used_exceptions, READ_ONLY_EXCEPTIONS)

    def test_4_report_fixer_has_no_write_tools_or_shell(self):
        for provider, entry in self.catalog["launch"]["report-fixer"].items():
            argv = entry["argv"]
            with self.subTest(provider=provider):
                if provider == "claude-code":
                    self.assertEqual(flag_values(argv, "--tools"), [""])
                elif provider == "codex":
                    self.assertEqual(flag_values(argv, "--sandbox"), ["read-only"])
                else:
                    self.assert_grok_read_only(argv)
                    self.assertEqual(flag_values(argv[:argv.index("--")], "--rw"), [])
                    self.assertIn("run_terminal_command", flag_values(argv, "--disallowed-tools")[0].split(","))

    def test_5_writers_never_use_acp_and_scout_always_returns_text(self):
        for role, provider, entry in self.entries:
            with self.subTest(role=role, provider=provider):
                if role in WRITERS:
                    self.assertNotEqual(entry["transport"], "acp")
                if role == "scout":
                    self.assertEqual(entry["transport"], "text")
                    if provider == "grok":
                        self.assertEqual(flag_values(entry["argv"], "--output-format"), ["plain"])
                        self.assertIn("--disable-web-search", entry["argv"])

    def test_6_every_entry_renders_with_all_launch_placeholders(self):
        values = {"model": "fixture-model", "effort": "high", "cwd": "/work", "orch": str(launch.ORCH_ROOT)}
        for role, provider, entry in self.entries:
            with self.subTest(role=role, provider=provider):
                argv = launch.build_argv(self.catalog, role, provider, model=values["model"],
                                         effort=values["effort"], cwd=values["cwd"])
                self.assertEqual(argv, catalog.substitute(entry["argv"], values))
                self.assertFalse(any(launch._PLACEHOLDER_RE.search(arg) for arg in argv))

    def test_7_every_grok_jsonl_launch_decodes_success_error_and_missing_result(self):
        fixture = ROOT / "tests/fixtures/grok/streaming-messages-json.jsonl"
        success = fixture.read_text(encoding="utf-8")
        error = fixture.with_name("streaming-messages-json-error.jsonl").read_text(encoding="utf-8")
        no_result = "\n".join(line for line in success.splitlines() if json.loads(line).get("type") != "result")
        entries = [(role, entry) for role, provider, entry in self.entries
                   if provider == "grok" and entry["transport"] == "jsonl"]
        self.assertTrue(entries)
        for role, entry in entries:
            with self.subTest(role=role):
                self.assertEqual(flag_values(entry["argv"], "--output-format"), ["streaming-messages-json"])
                parsed = process.parse_stream(entry["transport"], success)
                self.assertTrue(parsed["text"])
                self.assertGreater(parsed["usage"]["input"], 0)
                self.assertGreater(parsed["usage"]["output"], 0)
                self.assertFalse(parsed["is_error"])
                self.assertTrue(process.parse_stream(entry["transport"], error)["is_error"])
                self.assertEqual(process.parse_stream(entry["transport"], no_result)["text"], "")  # ROLE_OUTPUT_EMPTY


if __name__ == "__main__":
    unittest.main()
