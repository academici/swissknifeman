"""Stubs in a conductor run: the additional instructions of the project and the machine reach the prompt of their role
between the role text and the task, a run keeps the snapshot it started with (a resume says STUBS_CHANGED when the files
moved on), an unusable stub stops the run with STUBS_INVALID before any role starts, and ``orch stubs`` publishes and
explains them."""
from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import unittest

from orch import cli as orch_cli

from tests.test_conductor import ConductorCase, executor_ok


class StubRunTests(ConductorCase):
    scenario = "scout-solo"

    def stub(self, layer: str, slot: str, text: str) -> Path:
        root = self.project / ".swissknifeman" / "stubs" if layer == "project" else self.home / "skm" / "config" / "stubs"
        path = root / slot
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if layer == "project":  # a project stub is a file of the repository: committed like any other
            self.git("add", "-A")
            self.git("commit", "-q", "-m", "stub")
        return path

    def orch(self, *argv) -> tuple:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = orch_cli.main(["--project", str(self.project), *argv])
        return code, out.getvalue(), err.getvalue()

    def test_the_stub_stands_between_the_role_text_and_the_task(self):
        self.stub("machine", "orch/roles/_all.md", "Machine rule for every role.\n")
        self.stub("project", "orch/roles/executor.md", "Project rule: prefer small commits.\n")
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        prompt = self.prompt("executor", 1)
        heading = prompt.index("## Additional instructions")
        self.assertLess(heading, prompt.index("Goal"))
        self.assertLess(prompt.index("Machine rule for every role."), prompt.index("Project rule: prefer small commits."))
        snapshot = json.loads((self.run_dir(err) / "instructions.json").read_text(encoding="utf-8"))
        run_doc = json.loads((self.run_dir(err) / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(run_doc["instructions_digest"], snapshot["digest"])
        self.assertEqual([part["layer"] for part in snapshot["targets"]["orch.role.executor"]["parts"]],
                         ["machine", "project"])
        manifest = json.loads((self.run_dir(err) / "W1" / "prompts" / "executor.1.manifest.json")
                              .read_text(encoding="utf-8")) \
            if (self.run_dir(err) / "W1" / "prompts" / "executor.1.manifest.json").exists() else None
        if manifest is not None:
            self.assertIn("stub", [block["kind"] for block in manifest["blocks"]])

    def test_without_stubs_the_prompt_has_no_block(self):
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("## Additional instructions", self.prompt("executor", 1))

    def test_an_unusable_stub_stops_before_any_role(self):
        (self.project / ".swissknifeman" / "stubs" / "orch" / "roles").mkdir(parents=True)
        os.symlink("/etc/hostname", self.project / ".swissknifeman" / "stubs" / "orch" / "roles" / "executor.md")
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)[1] if self.lines(err) else None), (1, "STUBS_INVALID"), err) \
            if any(line.get("event") == "run.end" for line in self.lines(err)) else self.assertIn("STUBS_INVALID", err)
        self.assertEqual(self.calls("executor"), 0)

    def test_a_resume_keeps_the_snapshot_and_says_stubs_changed(self):
        self.stub("project", "orch/roles/executor.md", "first text\n")
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        kept = (self.run_dir(err) / "instructions.json").read_text(encoding="utf-8")
        self.stub("project", "orch/roles/executor.md", "second text\n")
        _, _, err2 = self.conduct("resume", "--run", self.run_dir(err).name, "--json-lines")
        self.assertIn("STUBS_CHANGED", [line.get("reason_code") for line in self.lines(err2)], err2)
        self.assertEqual((self.run_dir(err) / "instructions.json").read_text(encoding="utf-8"), kept)

    def test_a_machine_without_the_project_layer_ignores_project_stubs(self):
        self.write_config(extra='[orch.stubs]\nlayers = ["machine"]')
        self.stub("project", "orch/roles/executor.md", "project text\n")
        self.script({"executor": [executor_ok("W1")]})
        code, _, err = self.run_items("W1")
        self.assertEqual(code, 0, err)
        self.assertNotIn("project text", self.prompt("executor", 1))

    def test_publish_list_and_show(self):
        code, out, err = self.orch("stubs", "publish", "--json")
        self.assertEqual(code, 0, err)
        files = json.loads(out)["files"]
        self.assertIn("orch/roles/reviewer.md", [row["slot"] for row in files])
        self.assertNotIn("orch/roles/registrar.md", [row["slot"] for row in files])
        self.assertEqual({row["status"] for row in files}, {"created"})
        self.stub("project", "orch/roles/reviewer.md", "Look at the error paths first.\n")
        code, out, _ = self.orch("stubs", "publish")
        self.assertEqual(code, 0)
        self.assertNotIn("created", out)
        code, out, _ = self.orch("stubs", "show", "reviewer")
        self.assertEqual(code, 0)
        self.assertIn("Look at the error paths first.", out)
        self.assertIn("## Additional instructions", out)
        code, out, _ = self.orch("stubs", "list", "--json")
        self.assertEqual(json.loads(out)["targets"]["orch.role.reviewer"]["parts"][0]["layer"], "project")
        code, _, err = self.orch("stubs", "show", "registrar")
        self.assertEqual(code, 1)
        self.assertIn("STUB_TARGET_UNKNOWN", err)


if __name__ == "__main__":
    unittest.main()
