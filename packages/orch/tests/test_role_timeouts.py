"""Walls of the auxiliary roles (``limits.role_timeout_s``) and of a check (``check_timeout_s`` 7200) on fake providers."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest import mock

from orch.conductor import options, process
from orch.conductor.infrastructure.files import safe
from tests.test_conductor import ConductorCase, FIXTURES, GREEN, ROLES, executor_ok
from tests.test_conductor_input import EXECUTOR, InputCase


class RoleTimeoutTests(ConductorCase):
    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(process, "POLL_S", 0.1)  # the wall is looked at once per poll
        patcher.start()
        self.addCleanup(patcher.stop)

    def options_file(self, **limits):
        path = self.project.parent / "walls.json"
        path.write_text(json.dumps({"limits": limits}), encoding="utf-8")
        return path

    def preview(self, *extra) -> dict:
        code, out, err = self.conduct("run", "--plan", "T", "--items", "W1", "--dry-run", *extra)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def test_a_reviewer_that_outlasts_its_wall_stops_with_timeout_after_the_retries(self):
        self.script({"executor": [executor_ok("W1")], "reviewer": [dict(GREEN, sleep=10)]})
        code, _, err = self.run_items("W1", extra=("--options", self.options_file(role_timeout_s={"reviewer": 1})))
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TIMEOUT")), err)
        self.assertGreater(self.calls("reviewer"), 1)  # repeated by the retry rule before the stop

    def test_the_executor_has_no_wall_unless_one_is_named(self):
        self.script({"executor": [dict(executor_ok("W1"), sleep=3)], "reviewer": [GREEN]})
        code, _, err = self.run_items("W1", extra=("--options", self.options_file(role_timeout_s={"reviewer": 1})))
        self.assertEqual(code, 0, err)
        self.assertEqual(self.calls("executor"), 1)

    def test_a_wall_from_the_configuration_reaches_the_role(self):
        """A wall set in ``[orch.conductor.limits.role_timeout_s]`` (not in ``--options``) stops the role."""
        self.write_config(extra="[orch.conductor.limits.role_timeout_s]\nreviewer = 1\n")
        self.script({"executor": [executor_ok("W1")], "reviewer": [dict(GREEN, sleep=10)]})
        code, _, err = self.run_items("W1")
        self.assertEqual((code, self.outcome(err)), (1, ("stopped", "TIMEOUT")), err)

    def test_the_group_review_runs_under_the_reviewer_wall(self):
        self.set_items({ref: {} for ref in ("W1", "W2")})
        self.script({"executor": [executor_ok("W1"), executor_ok("W2")],
                     "reviewer": [{"text": "## Findings\nnone\n## Checked and fine\n- a\n"}]})
        path = self.project.parent / "group-walls.json"
        path.write_text(json.dumps({"limits": {"role_timeout_s": {"reviewer": 7}}, "review": {"strategy": "single"}}),
                        encoding="utf-8")
        real, seen = process.run_role, []

        def spy(argv, prompt, **kwargs):
            seen.append((Path(kwargs["raw_path"]).name, kwargs["timeout_s"]))
            return real(argv, prompt, **kwargs)
        with mock.patch.object(process, "run_role", spy):
            code, _, err = self.run_items("W1", "W2", extra=("--options", path))
        self.assertEqual(code, 0, err)
        group = [wall for name, wall in seen if name.startswith("group-review")]
        self.assertEqual(group, [7], seen)

    def test_the_defaults_are_visible_in_the_preview(self):
        found = self.preview()
        limits = found["options"]["limits"]
        self.assertEqual(limits["check_timeout_s"], 7200)
        self.assertEqual(limits["role_timeout_s"], options.DEFAULT_LIMITS["role_timeout_s"])
        self.assertEqual((limits["unmetered"], limits["unmetered_charge_tokens"]), ("stop", 50000))
        self.assertEqual(found["routes"]["report-fixer"]["timeout_s"], 600)
        self.assertEqual(found["routes"]["executor"]["timeout_s"], 0)

    def test_a_layer_names_only_the_walls_it_changes(self):
        found = self.preview("--options", str(self.options_file(role_timeout_s={"report-fixer": 7, "executor": 9})))
        self.assertEqual(found["routes"]["report-fixer"]["timeout_s"], 7)
        self.assertEqual(found["routes"]["executor"]["timeout_s"], 9)
        self.assertEqual(found["options"]["limits"]["role_timeout_s"]["reviewer"], 1800)

    def test_text_roles_use_the_role_wall_with_explicit_zero_and_stage_precedence(self):
        found = self.preview("--scenario", "full")
        self.assertEqual(found["routes"]["context-scout"]["transport"], "text")
        self.assertEqual(found["routes"]["context-scout"]["timeout_s"], 900)
        for wall in (7, 0):
            with self.subTest(wall=wall):
                found = self.preview("--scenario", "full", "--options", str(self.options_file(role_timeout_s={"context-scout": wall})))
                self.assertEqual(found["routes"]["context-scout"]["timeout_s"], wall)
                self.assertEqual(found["routes"]["context-scout"]["idle_timeout_s"], 0)
        found = self.preview("--scenario", "full", "--options", str(self.options_file(stage_timeout_s=11,
                                                               role_timeout_s={"context-scout": 7})))
        self.assertEqual(found["routes"]["context-scout"]["timeout_s"], 11)

    def test_stage_timeout_wins_over_the_role_walls_and_zero_removes_one(self):
        found = self.preview("--options", str(self.options_file(stage_timeout_s=11)))
        self.assertEqual({role: route["timeout_s"] for role, route in found["routes"].items()
                          if route["transport"] != "text"}, {role: 11 for role, route in found["routes"].items()
                                                              if route["transport"] != "text"})
        found = self.preview("--options", str(self.options_file(role_timeout_s={"report-fixer": 0})))
        self.assertEqual(found["routes"]["report-fixer"]["timeout_s"], 0)

    def test_the_wall_keys_are_checked(self):
        for bad in ({"role_timeout_s": {"reviewer": -1}}, {"role_timeout_s": {"Reviewer": 5}},
                    {"role_timeout_s": []}, {"unmetered": "ignore"}, {"unmetered_charge_tokens": -1}):
            with self.subTest(bad=bad):
                self.assertTrue(options.layer_problems({"limits": bad}), bad)


class ScoutTimeoutResumeTests(InputCase):
    def test_resume_keeps_scout_attempts_streams_and_retry_budget(self):
        self.enterContext(mock.patch.object(process, "POLL_S", .05))
        scout = self.project.parent / "slow_scout.py"
        scout.write_text("""import os,sys,time
from pathlib import Path
sys.stdin.read()
p=Path(os.environ['FAKE_ROLE_STATE'])/'context-scout.count'
n=int(p.read_text())+1 if p.exists() else 1
p.write_text(str(n))
print('observed attempt '+str(n),flush=True)
if n<=3:time.sleep(10)
else:print('map complete\\nUnknowns:\\n- none',flush=True)
""")
        argv = {name: [sys.executable, str(FIXTURES / "fake_role.py"), name] for name in ROLES}
        argv["context-scout"] = [sys.executable, str(scout)]
        self.write_config(argv=argv)
        path = self.write_input()
        options_file = self.project.parent / "scout-walls.json"
        options_file.write_text(json.dumps({"limits": {"role_timeout_s": {"context-scout": 1}, "retries": 1}}))
        self.script({"executor": [EXECUTOR], "reviewer": [GREEN]})
        code, _, error = self.run_input(path, "--options", options_file)
        self.assertEqual((code, self.outcome(error)), (1, ("stopped", "TIMEOUT")), error)
        directory = self.run_dir(error)
        piece = directory / safe(self.input_doc["input_id"])
        ref = self.input_doc["input_id"]
        first = json.loads((directory / "state.json").read_text())["items"][ref]
        self.assertEqual((self.calls("context-scout"), first["retries_by_stage"]["scout"], first["retries_used"]), (2, 2, 2))
        streams = {p.name: p.read_bytes() for p in (piece / "streams").glob("scout*")}
        code, _, error = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual((code, self.outcome(error)), (1, ("stopped", "TIMEOUT")), error)
        second = json.loads((directory / "state.json").read_text())["items"][ref]
        self.assertEqual((self.calls("context-scout"), second["retries_by_stage"]["scout"], second["retries_used"]), (3, 3, 3))
        self.assertEqual(second["tokens"], first["tokens"])
        self.assertEqual((piece / "streams/scout-a3.txt").read_text(), "observed attempt 3\n")
        for name, content in streams.items():
            self.assertEqual((piece / "streams" / name).read_bytes(), content)
        code, _, error = self.conduct("resume", "--run", directory.name, "--json-lines")
        self.assertEqual((code, self.outcome(error)), (0, ("finished", None)), error)
        state = json.loads((directory / "state.json").read_text())
        final = state["items"][ref]
        self.assertEqual((state["resumes"], self.calls("context-scout"), final["retries_by_stage"]["scout"],
                          final["retries_used"]), (2, 4, 3, 3))
        self.assertEqual(final["steps"]["scout"]["result"]["attempts"], 4)
        for name, content in streams.items():
            self.assertEqual((piece / "streams" / name).read_bytes(), content)


if __name__ == "__main__":
    unittest.main()
