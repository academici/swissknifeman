"""The executor prompt tells an executor that can use Docker nothing against it, and one that its provider sandbox keeps out of the
Docker socket not to try (and to report what it could not prove as pending)."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from orch.conductor import prompts

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


if __name__ == "__main__":
    unittest.main()
