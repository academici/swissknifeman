"""The launch catalog file states only what is specific (defaults, shared role fields, named argv parts, per-provider
differences); the resolved catalog every reader sees is unchanged and is pinned by a reviewed snapshot."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from orch import launch

GOLDEN = Path(__file__).resolve().parent / "golden" / "launch-catalog-resolved.json"


def compact() -> dict:
    return {"catalog_version": "1.0.0", "defaults": {"transport": "jsonl", "model_set": "supported"},
            "parts": {"codex.exec": ["codex", "-a", "never", "exec"], "codex.model": ["--model", "{model}"]},
            "roles": {"executor": {"model_class": "implementation", "effort": "high", "timeout_s": 3600, "providers": {
                "codex": {"argv": ["@codex.exec", "--json", "--sandbox", "workspace-write", "@codex.model", "-"]}}},
                      "scout": {"model_class": "economy", "effort": "low", "transport": "text", "timeout_s": 300,
                                "providers": {"codex": {"timeout_s": 60, "argv": [
                                    "@codex.exec", "--sandbox", "read-only", "@codex.model", "-"]}}}}}


def expanded(doc: dict) -> dict:
    return launch.expand_catalog(copy.deepcopy(doc))


class ShippedFileTests(unittest.TestCase):
    def test_the_resolved_catalog_is_the_reviewed_snapshot(self):
        """Any change of a command line, a sandbox flag, a class, an effort, a transport or a timeout shows up here, whatever
        the way the file states it. Update the snapshot only as the review of that change."""
        self.assertEqual(launch.load_catalog(), json.loads(GOLDEN.read_text(encoding="utf-8")))

    def test_the_file_is_compact_and_every_part_is_used(self):
        raw = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8"))
        self.assertIn("roles", raw)
        self.assertNotIn("launch", raw)
        self.assertLess(len(launch.CATALOG_PATH.read_text(encoding="utf-8")), GOLDEN.stat().st_size * 0.6)

    def test_the_sandbox_of_every_codex_role_is_stated_in_its_own_entry(self):
        raw = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8"))
        for role, body in raw["roles"].items():
            argv = body["providers"].get("codex", {}).get("argv")
            if argv:
                with self.subTest(role=role):
                    self.assertIn("--sandbox", argv)  # the confinement is never hidden inside a shared part

    def test_claude_research_roles_keep_the_invocation_config_query(self):
        catalog = launch.load_catalog()
        for role in ("researcher", "advisor"):
            argv = catalog["launch"][role]["claude-code"]["argv"]
            self.assertIn("Bash(python3 *orch.py --config * research query *)", argv)


class ResumeArgvTests(unittest.TestCase):
    """``resume_argv``: the optional command line that continues a session of a provider (``{session}``)."""

    RESUME = ["@codex.exec", "resume", "{session}", "--json", "-c", 'sandbox_mode="{write_sandbox}"', "@codex.model", "-"]

    def with_resume(self, resume=None, shipped: bool = False) -> dict:
        """A compact catalog whose codex executor has ``resume_argv`` (the shipped file when ``shipped``, which holds every
        role a valid catalog needs; the small one only expands)."""
        doc = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8")) if shipped else compact()
        doc["roles"]["executor"]["providers"]["codex"]["resume_argv"] = self.RESUME if resume is None else resume
        return doc

    def test_a_catalog_with_resume_argv_is_valid_and_expands_its_parts(self):
        found = expanded(self.with_resume())["launch"]["executor"]["codex"]
        self.assertEqual(found["resume_argv"], ["codex", "-a", "never", "exec", "resume", "{session}", "--json", "-c",
                                                'sandbox_mode="{write_sandbox}"', "--model", "{model}", "-"])
        self.assertEqual(list(found).index("resume_argv"), list(found).index("argv") + 1)
        launch.validate_catalog(expanded(self.with_resume(shipped=True)))

    def test_a_catalog_without_resume_argv_is_valid_and_has_none(self):
        doc = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8"))
        del doc["roles"]["executor"]["providers"]["codex"]["resume_argv"]
        found = expanded(doc)
        launch.validate_catalog(found)
        self.assertNotIn("resume_argv", found["launch"]["executor"]["codex"])
        self.assertIsNone(launch.build_resume_argv(found, "executor", "codex", model="m"))

    def test_resume_argv_without_the_session_placeholder_is_refused(self):
        for resume in (["codex", "exec", "resume", "--json", "--model", "{model}"],
                       ["codex", "exec", "resume", "{model}", "--last"]):
            with self.subTest(resume=resume), self.assertRaises(launch.LaunchError) as raised:
                launch.validate_catalog(expanded(self.with_resume(resume, shipped=True)))
            self.assertEqual(raised.exception.code, "LAUNCH_INVALID")
            self.assertIn("{session}", str(raised.exception))

    def test_a_malformed_resume_argv_is_refused(self):
        for resume in ("codex resume {session}", [], [1, "{session}"], ["codex", "{session}", "{nope}", "{model}"],
                       ["codex", "{session}"]):  # a string, empty, not strings, an unknown placeholder, no {model}
            with self.subTest(resume=resume), self.assertRaises(launch.LaunchError):
                launch.validate_catalog(expanded(self.with_resume(resume, shipped=True)))

    def test_the_session_placeholder_is_not_allowed_in_argv(self):
        doc = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8"))
        doc["roles"]["executor"]["providers"]["codex"]["argv"].insert(2, "{session}")
        with self.assertRaises(launch.LaunchError):
            launch.validate_catalog(expanded(doc))

    def test_the_required_entry_keys_are_unchanged(self):
        self.assertEqual(launch.ENTRY_KEYS, {"model_class", "effort", "transport", "argv", "timeout_s", "model_set"})
        catalog = expanded(self.with_resume(shipped=True))
        del catalog["launch"]["executor"]["codex"]["timeout_s"]
        with self.assertRaises(launch.LaunchError):
            launch.validate_catalog(catalog)

    def test_build_resume_argv_fills_everything_but_the_session(self):
        catalog = expanded(self.with_resume())
        self.assertEqual(launch.build_resume_argv(catalog, "executor", "codex", model="gpt-x", effort="high"),
                         ["codex", "-a", "never", "exec", "resume", "{session}", "--json", "-c",
                          'sandbox_mode="danger-full-access"', "--model", "gpt-x", "-"])
        confined = launch.build_resume_argv(catalog, "executor", "codex", model="gpt-x", access="confined")
        self.assertIn('sandbox_mode="workspace-write"', confined)
        with self.assertRaises(launch.LaunchError):
            launch.build_resume_argv(catalog, "executor", "codex")  # a model is needed

    def test_the_shipped_catalog_resumes_a_codex_and_a_grok_executor_only(self):
        catalog = launch.load_catalog()
        self.assertEqual(catalog["catalog_version"], "1.7.0")
        found = [(role, provider) for role, providers in catalog["launch"].items() for provider, entry in providers.items()
                 if "resume_argv" in entry]
        self.assertEqual(found, [("executor", "codex"), ("executor", "grok")])
        argv = launch.build_resume_argv(catalog, "executor", "codex", model="gpt-6.1-sol", effort="xhigh")
        self.assertEqual(argv[:6], ["codex", "-a", "never", "exec", "resume", "{session}"])  # -a is before exec
        self.assertNotIn("--sandbox", argv)  # `codex exec resume` has no such option
        self.assertEqual(argv[argv.index("-c") + 1], 'sandbox_mode="danger-full-access"')

    def test_the_overrides_of_the_configuration_can_set_and_check_resume_argv(self):
        merged = launch.apply_entries(launch.load_catalog(), {"executor_codex": {"resume_argv": [
            "codex", "exec", "resume", "{session}", "--model", "{model}", "-"]}})
        self.assertEqual(merged["launch"]["executor"]["codex"]["resume_argv"][3], "{session}")
        with self.assertRaises(launch.LaunchError):
            launch.apply_entries(launch.load_catalog(), {"executor_codex": {"resume_argv": ["codex", "exec"]}})


class ExpandTests(unittest.TestCase):
    def test_defaults_then_role_then_provider_then_parts(self):
        found = expanded(compact())["launch"]
        self.assertEqual(found["executor"]["codex"], {
            "model_class": "implementation", "effort": "high", "timeout_s": 3600, "transport": "jsonl",
            "model_set": "supported",
            "argv": ["codex", "-a", "never", "exec", "--json", "--sandbox", "workspace-write", "--model", "{model}", "-"]})
        scout = found["scout"]["codex"]
        self.assertEqual((scout["transport"], scout["timeout_s"], scout["model_set"]), ("text", 60, "supported"))

    def test_a_catalog_in_the_resolved_form_is_returned_as_it_is(self):
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        self.assertIs(launch.expand_catalog(golden), golden)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.json"
            path.write_text(json.dumps(golden), encoding="utf-8")
            self.assertEqual(launch.load_catalog(path), golden)

    def test_an_at_sign_argument_is_written_twice(self):
        doc = compact()
        doc["roles"]["executor"]["providers"]["codex"]["argv"] = ["@codex.exec", "@@file", "@codex.model"]
        doc["roles"]["scout"]["providers"]["codex"]["argv"] = ["@codex.exec", "@codex.model", "-"]
        self.assertEqual(expanded(doc)["launch"]["executor"]["codex"]["argv"][-3:], ["@file", "--model", "{model}"])

    def refused(self, mutate, text: str):
        doc = compact()
        mutate(doc)
        with self.assertRaises(launch.LaunchError) as raised:
            launch.validate_catalog(expanded(doc))
        self.assertEqual(raised.exception.code, "LAUNCH_INVALID")
        self.assertIn(text, str(raised.exception))

    def test_malformed_compact_catalogs_are_refused_with_the_place(self):
        self.refused(lambda d: d["roles"]["executor"]["providers"]["codex"]["argv"].append("@nope"), "unknown part '@nope'")
        self.refused(lambda d: d["parts"].update({"spare": ["x"]}), "unused part(s) ['spare']")
        self.refused(lambda d: d["parts"].update({"outer": ["@codex.exec"]}), "cannot name another part")
        self.refused(lambda d: d.update({"launch": {}}), "no launch")
        self.refused(lambda d: d.update({"extra": 1}), "no launch")
        self.refused(lambda d: d["roles"]["executor"].update({"argv": ["x"]}), "/roles/executor")
        self.refused(lambda d: d["roles"]["executor"]["providers"]["codex"].pop("argv"), "must hold argv")
        self.refused(lambda d: d["roles"]["executor"]["providers"]["codex"].update({"bogus": 1}), "must hold argv")
        self.refused(lambda d: d["defaults"].update({"argv": ["x"]}), "/defaults")

    def test_an_entry_the_compact_form_leaves_incomplete_is_refused_by_the_catalog_rules(self):
        doc = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8"))
        del doc["roles"]["executor"]["effort"]  # no default states it
        with self.assertRaises(launch.LaunchError) as raised:
            launch.validate_catalog(expanded(doc))
        self.assertIn("/launch/executor/", str(raised.exception))

    def test_the_shipped_file_with_a_changed_field_changes_only_that_field(self):
        doc = json.loads(launch.CATALOG_PATH.read_text(encoding="utf-8"))
        doc["roles"]["reviewer"]["effort"] = "xhigh"
        golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
        found = expanded(doc)
        for provider in golden["launch"]["reviewer"]:
            golden["launch"]["reviewer"][provider]["effort"] = "xhigh"
        self.assertEqual(found, golden)

    def test_the_overrides_of_the_configuration_work_on_the_resolved_form(self):
        merged = launch.apply_entries(launch.load_catalog(), {"executor_codex": {"timeout_s": 7200}})
        self.assertEqual(merged["launch"]["executor"]["codex"]["timeout_s"], 7200)


if __name__ == "__main__":
    unittest.main()
