"""Fixes after the batch review of P11.1-P11.3 (the layered conductor): each defect the reviewer traced has a case here."""
from __future__ import annotations

from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

from orch.conductor.application import run_service
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import work_source
from orch.conductor.stages import context, execute


class RetryOfAPieceTheConductorBlocked(unittest.TestCase):
    def fake(self, steps: dict):
        saved = []
        self_ = types.SimpleNamespace(state={"items": {"W1": {"outcome": "blocked", "steps": steps, "stop": {}}}, "questions": {}},
                                      _save=lambda: saved.append(1), progress=mock.Mock(), directory=Path(tempfile.mkdtemp()))
        return self_

    def test_checks_red_past_the_limit_has_no_blocked_round_and_retry_goes_on_from_the_last_executor_round(self):
        steps = {"brief": {"ended": "1"}, "executor.1": {"ended": "2", "result": {"report": {"status": "done"}}},
                 "checks.1": {"ended": "3"}, "executor.2": {"ended": "4", "result": {"report": {"status": "done"}}},
                 "checks.2": {"ended": "5"}}
        me = self.fake(steps)
        run_service.retry(me, "W1")
        self.assertEqual(sorted(me.state["items"]["W1"]["steps"]), ["checks.1", "executor.1"])
        self.assertNotIn("outcome", me.state["items"]["W1"])

    def test_a_piece_without_any_executor_round_is_still_refused(self):
        me = self.fake({"brief": {"ended": "1"}})
        with self.assertRaises(Stop) as stop:
            run_service.retry(me, "W1")
        self.assertEqual(stop.exception.code, "RETRY_NOT_BLOCKED")


class AdoptedPaths(unittest.TestCase):
    def test_a_stray_file_the_owner_removed_is_no_longer_adopted(self):
        item = types.SimpleNamespace(ref="W1", state={"adopted": ["src/ok", "notes/tmp"]},
                                     input_doc={"scope": {"write_set": ["src/**"]}})
        me = types.SimpleNamespace(_not_the_role=lambda it: [], _dirty_paths=lambda: ["src/ok"])
        with mock.patch.object(execute.scopes, "own", side_effect=lambda paths, _: list(paths)):
            self.assertEqual(execute.adopted(me, item), ["src/ok"])
        self.assertEqual(item.state["adopted"], ["src/ok"])


class BriefAndArtifacts(unittest.TestCase):
    def test_a_failed_re_brief_is_visible(self):
        me = types.SimpleNamespace(_orch=lambda *a: (1, None, "boom: no plan"), progress=mock.Mock(), project=Path("."))
        work_source.refresh_input(me, types.SimpleNamespace(ref="W1", orch_run="r"))
        reasons = [call.kwargs.get("reason_code") for call in me.progress.emit.call_args_list]
        self.assertIn("INPUT_REFRESH_FAILED", reasons)

    def test_artifacts_outside_the_project_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            me = types.SimpleNamespace(project=Path(tmp))
            item = types.SimpleNamespace(ref="W1", artifacts=None)
            work_source.open_artifacts(me, item, {"artifacts_dir": "plans/x/artifacts/W1"})
            self.assertEqual(item.artifacts, Path(tmp) / "plans/x/artifacts/W1")
            for bad in ("../outside", "/tmp/out"):
                with self.assertRaises(Stop) as stop:
                    work_source.open_artifacts(me, item, {"artifacts_dir": bad})
                self.assertEqual(stop.exception.code, "ARTIFACTS_OUTSIDE_PROJECT")


class RepositoryRulesWalk(unittest.TestCase):
    def test_a_write_set_pattern_that_climbs_out_never_reads_outside_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "secret").mkdir()
            (base / "secret" / "CLAUDE.md").write_text("## module-folders\\nSECRET RULE\\n", encoding="utf-8")
            project = base / "project"
            project.mkdir()
            item = types.SimpleNamespace(options={"instructions": {"module_rules": ["module-folders"]}},
                                         input_doc={"scope": {"write_set": ["../secret/CLAUDE.md/placeholder"]}})
            me = types.SimpleNamespace(project=project)
            self.assertNotIn("SECRET RULE", context.repo_rules(me, item, "executor"))


if __name__ == "__main__":
    unittest.main()
