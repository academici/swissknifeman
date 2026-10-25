"""The executor prompt tells an executor that can use Docker nothing against it, and one that its provider sandbox keeps out of the
Docker socket not to try (and to report what it could not prove as pending). Whether it can is the ``docker`` of the
authority envelope of its launch (P6.2): a Claude Code executor confined by its sandbox is kept out too."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest import mock

from orch.conductor import engine, prompts
from tests.test_conductor import FIXTURES, GREEN, ROLES, ConductorCase, executor_ok

INPUT = Path(__file__).resolve().parents[1] / "fixtures" / "exec" / "v1" / "valid" / "execution-input" / "plan-bound.json"


class ContainersTests(unittest.TestCase):
    def prompt(self, **kwargs) -> str:
        doc = json.loads(INPUT.read_text(encoding="utf-8"))
        return prompts.render(prompts.executor(doc, item="P1.1", step="executor.1", **kwargs))

    def test_an_executor_that_can_use_docker_is_not_told_to_keep_away_from_it(self):
        text = self.prompt()
        self.assertNotIn("do not start containers", text)
        self.assertNotIn("the docker socket", text)
        self.assertIn("container-based ones included", text)
        self.assertIn("kind `pending`", text)  # what its environment cannot prove still goes to the conductor

    def test_an_executor_kept_out_of_docker_by_its_sandbox_is_told_not_to_try(self):
        text = self.prompt(containers=False)
        self.assertIn("do not start containers or call docker or compose", text)
        self.assertIn("a container, the docker socket, write access", text)
        self.assertNotIn("container-based ones included", text)


class EnvelopeTests(ConductorCase):
    UP = {"available": True, "reason": None, "checked": []}

    def run_with(self, *extra, provider: str = "") -> str:
        argv = {role: [sys.executable, str(FIXTURES / "fake_role.py"), role] for role in ROLES}
        argv["executor"] += list(extra)
        self.write_config(argv)
        self.script({"executor": [executor_ok("W1")], "reviewer": [GREEN]})
        options = ()
        if provider:
            path = self.project.parent / "options.json"
            path.write_text(json.dumps({"stages": [{"role": "executor", "provider": provider}]}), encoding="utf-8")
            options = ("--options", str(path))
        with mock.patch.object(engine.sandbox, "probe", return_value=self.UP):
            code, _, err = self.run_items("W1", extra=options)
        self.assertEqual(code, 0, err)
        return self.prompt("executor", 1)

    def test_a_claude_executor_its_sandbox_confines_is_told_not_to_use_docker(self):
        text = self.run_with("--tools", "Bash,Read,Edit")
        self.assertIn("do not start containers or call docker or compose", text)
        self.assertIn("Docker: not available here", text)

    def test_an_open_codex_executor_may_use_docker(self):
        text = self.run_with("--sandbox", "danger-full-access", provider="codex")  # access open: no provider sandbox
        self.assertIn("Docker: you may use containers", text)
        self.assertNotIn("do not start containers", text)
        self.assertIn("container-based ones included", text)

    def test_a_confined_codex_executor_is_kept_out_of_docker(self):
        text = self.run_with("--sandbox", "workspace-write", provider="codex")
        self.assertIn("do not start containers or call docker or compose", text)


if __name__ == "__main__":
    unittest.main()
