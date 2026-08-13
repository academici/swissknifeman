"""Focused deterministic and fail-closed tests for generated Codex commands."""
from dataclasses import replace
import json
from pathlib import Path
import shutil
import tempfile
import unittest

try:
    from . import fixtures  # noqa: F401,E402 — package invocation
except ImportError:
    import fixtures  # noqa: F401,E402 — direct discovery
from core.provider.lock import ArtifactActionKind
from task.command_catalog import build_command_catalog
from task.command_render import (PROVIDER_LOCK_PATH, apply_codex_command_plan,
                                 mapping_from_catalog, plan_codex_command_apply,
                                 plan_codex_command_render, render_invocation)


REPO_ROOT = Path(__file__).resolve().parents[3]
COMMAND_ROOT = REPO_ROOT / "packages/task/commands"
ROUTING_PATH = REPO_ROOT / "packages/task/configs/command-routing.json"
FIXTURE = REPO_ROOT / "packages/task/tests/fixtures_data/codex-command-cases.json"


class CodexCommandAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.catalog = build_command_catalog(COMMAND_ROOT, ROUTING_PATH)
        cls.mapping = mapping_from_catalog(cls.catalog, "codex")
        cls.support = dict(cls.mapping.capability_bindings)

    def render(self, **kwargs):
        return plan_codex_command_render(self.catalog, self.mapping, self.support, **kwargs)

    def test_invocation_and_exact_generated_inventory(self):
        records = self.catalog.by_id()
        for command_id, expected in self.expected["invocations"].items():
            arguments = expected.split(command_id + " ", 1)[1]
            self.assertEqual(render_invocation(records[command_id], arguments, self.mapping), expected)
        plan = self.render()
        self.assertTrue(plan.ok)
        self.assertEqual(len(plan.artifacts), 24)
        paths = {artifact.path for artifact in plan.artifacts}
        self.assertIn("packages/task/.codex-plugin/plugin.json", paths)
        self.assertIn("packages/task/adapters/codex/publication-lock.json", paths)
        for command_id in self.expected["command_ids"]:
            name = command_id.removeprefix("task:")
            self.assertIn(f"packages/task/adapters/codex/skills/task-{name}/SKILL.md", paths)
            self.assertIn(f"packages/task/adapters/codex/skills/task-{name}/command.md", paths)

    def test_two_renders_are_byte_identical_and_runtime_projection_is_self_contained(self):
        first, second = self.render(), self.render()
        self.assertEqual([(item.path, item.managed_bytes, item.rendered_hash)
                          for item in first.artifacts],
                         [(item.path, item.managed_bytes, item.rendered_hash)
                          for item in second.artifacts])
        by_path = {item.path: item for item in first.artifacts}
        for record in self.catalog.records:
            name = record.command_id.removeprefix("task:")
            path = f"packages/task/adapters/codex/skills/task-{name}/command.md"
            runtime = by_path[path].managed_bytes
            self.assertNotEqual(runtime, self.catalog.content_for(record.command_id))
            self.assertFalse(runtime.startswith(b"---\n"))
            self.assertIn(record.source.path.encode(), runtime)
            self.assertIn(record.source.content_hash.encode(), runtime)

    def test_task_runtime_paths_are_provider_specific_and_never_project_relative(self):
        canonical = self.catalog.content_for("task:plan-exec").decode("utf-8")
        self.assertIn('PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/lib"', canonical)
        self.assertNotIn("PYTHONPATH=packages/task/lib", canonical)
        codex_runtime = next(
            artifact.managed_bytes.decode("utf-8") for artifact in self.render().artifacts
            if artifact.path.endswith("/task-plan-exec/command.md"))
        self.assertIn("codex plugin marketplace list --json", codex_runtime)
        self.assertIn("packages/task/lib/task", codex_runtime)
        self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", codex_runtime)
        self.assertNotIn("PYTHONPATH=packages/task/lib", codex_runtime)

    def test_plan_runtime_requires_a_full_native_codex_launch_block(self):
        codex_runtime = next(
            artifact.managed_bytes.decode("utf-8") for artifact in self.render().artifacts
            if artifact.path.endswith("/task-plan-run/command.md"))
        self.assertIn("Native Codex launch-block — mandatory for every handoff", codex_runtime)
        self.assertIn("codex -C <repo-cwd> -m <model-selector>", codex_runtime)
        self.assertIn("model_reasoning_effort=\"<effort-selector>\"", codex_runtime)
        self.assertIn("-a never -s danger-full-access", codex_runtime)
        self.assertIn("do not reuse the preceding session's route", codex_runtime)

    def test_plan_run_prefers_current_thread_state_with_exact_native_fallback(self):
        canonical = self.catalog.content_for("task:plan-run").decode("utf-8")
        self.assertIn('source="cli-flag"', canonical)
        self.assertIn("route_evidence_codex.capture_current", canonical)

        runtime = next(
            artifact.managed_bytes.decode("utf-8") for artifact in self.render().artifacts
            if artifact.path.endswith("/task-plan-run/command.md"))
        self.assertIn('source="provider-thread-state"', runtime)
        self.assertIn("codex-turn-context-v1", runtime)
        self.assertIn("CODEX_THREAD_ID", runtime)
        self.assertIn("Codex clear command", runtime)
        self.assertIn("compatibility fallback", runtime)
        self.assertIn('source="cli-flag"', runtime)
        self.assertIn("route_evidence_codex.capture_current", runtime)
        self.assertNotIn('source="provider-doctor"', runtime)
        self.assertNotIn('source="self-attested"', runtime)

    def test_runtime_projection_changes_only_standalone_claude_ui_tokens(self):
        boundary_case = (
            b"\nmodel/effort <model/effort> path/effort\n"
            b"/model /effort /clear /task:fix\n"
        )
        source_contents = tuple(
            (command_id, content + boundary_case
             if command_id == "task:fix" else content)
            for command_id, content in self.catalog.source_contents)
        plan = plan_codex_command_render(
            replace(self.catalog, source_contents=source_contents),
            self.mapping, self.support)
        self.assertTrue(plan.ok, plan.diagnostics)
        runtime = next(
            artifact.managed_bytes.decode("utf-8")
            for artifact in plan.artifacts
            if artifact.path.endswith("/task-fix/command.md"))
        self.assertIn("model/effort <model/effort> path/effort", runtime)
        self.assertIn(
            "select the session model class select the session effort "
            "reset the session context $ task:fix",
            runtime)
        self.assertNotIn("modelsession effort setting", runtime)
        self.assertNotIn("session effort setting", runtime)

    def test_negative_diagnostics_precede_results_or_writes(self):
        cases = []
        support = dict(self.support)
        support.pop("skills.repository")
        cases.append(("CMD_CAPABILITY_UNSUPPORTED", self.mapping, support, {}))

        class_pairs = dict(self.mapping.class_selectors)
        class_pairs["frontier"] = ()
        cases.append(("CMD_MAPPING_MISSING",
                      replace(self.mapping, class_selectors=tuple(class_pairs.items())),
                      self.support, {}))

        class_pairs["frontier"] = ("gpt-5.6-sol", "gpt-5.6-sol-preview")
        cases.append(("CMD_MAPPING_AMBIGUOUS",
                      replace(self.mapping, class_selectors=tuple(class_pairs.items())),
                      self.support, {}))

        cases.append(("CMD_ROUTE_UNDERSHOOT", self.mapping, self.support,
                      {"task:plan-audit": ("implementation", "xhigh")}))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            before = tuple(root.rglob("*"))
            for expected, mapping, support, routes in cases:
                with self.subTest(expected=expected):
                    plan = plan_codex_command_render(self.catalog, mapping, support,
                                                     observed_routes=routes)
                    self.assertFalse(plan.ok)
                    self.assertEqual(plan.results, ())
                    self.assertIn(expected, {item.code for item in plan.diagnostics})
                    self.assertEqual(tuple(root.rglob("*")), before)

            for poison in (b"\nWorkflow({unknown})\n", b"\n/model <UNKNOWN>\n"):
                poisoned_contents = tuple(
                    (command_id, content + poison
                     if command_id == "task:fix" else content)
                    for command_id, content in self.catalog.source_contents)
                unsafe = plan_codex_command_render(
                    replace(self.catalog, source_contents=poisoned_contents),
                    self.mapping, self.support)
                self.assertFalse(unsafe.ok)
                self.assertEqual(unsafe.results, ())
                self.assertIn("CMD_INVOCATION_INVALID",
                              {item.code for item in unsafe.diagnostics})
                self.assertEqual(tuple(root.rglob("*")), before)

    def test_lock_lifecycle_repair_and_cache_containment(self):
        render = self.render()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            initial = plan_codex_command_apply(root, render, lock_bytes=None)
            self.assertTrue(all(action.action is ArtifactActionKind.CREATE
                                for action in initial.actions))
            apply_codex_command_plan(root, initial)
            lock_path = root / PROVIDER_LOCK_PATH
            lock_bytes = lock_path.read_bytes()

            second = plan_codex_command_apply(root, self.render(), lock_bytes=lock_bytes)
            self.assertTrue(all(action.action is ArtifactActionKind.NOOP
                                for action in second.actions))
            snapshot = tuple(sorted((path.relative_to(root).as_posix(), path.read_bytes())
                                    for path in root.rglob("*") if path.is_file()))
            apply_codex_command_plan(root, second)
            self.assertEqual(snapshot, tuple(sorted(
                (path.relative_to(root).as_posix(), path.read_bytes())
                for path in root.rglob("*") if path.is_file())))

            target = root / "packages/task/adapters/codex/skills/task-fix/command.md"
            target.write_bytes(b"drift\n")
            refused = plan_codex_command_apply(root, render, lock_bytes=lock_bytes)
            fix_action = next(action for action in refused.actions
                              if action.artifact_id == "task.codex.fix.runtime")
            self.assertEqual(fix_action.action, ArtifactActionKind.REFUSE)
            repaired = plan_codex_command_apply(
                root, render, lock_bytes=lock_bytes,
                repair_artifact_ids=("task.codex.fix.runtime",))
            apply_codex_command_plan(root, repaired)
            expected_runtime = next(
                artifact.managed_bytes for artifact in render.artifacts
                if artifact.path == target.relative_to(root).as_posix())
            self.assertEqual(target.read_bytes(), expected_runtime)
            self.assertEqual(target.with_name("command.md.provider-artifact.bak").read_bytes(),
                             b"drift\n")

            cache = root / "cache"
            shutil.copytree(root / "packages/task/adapters/codex", cache / "adapters/codex")
            shutil.copytree(root / "packages/task/.codex-plugin", cache / ".codex-plugin")
            shutil.rmtree(root / "packages/task/adapters/codex")
            shutil.rmtree(root / "packages/task/.codex-plugin")
            for command_id in self.expected["command_ids"]:
                name = command_id.removeprefix("task:")
                skill = cache / f"adapters/codex/skills/task-{name}/SKILL.md"
                runtime = skill.with_name("command.md")
                self.assertTrue(skill.is_file())
                self.assertTrue(runtime.is_file())
                self.assertIn(b"Read `command.md` completely", skill.read_bytes())
                self.assertGreater(len(runtime.read_bytes()), 0)

    def test_plugin_version_is_part_of_generated_provenance(self):
        current = self.render()
        bumped_catalog = replace(self.catalog, plugin_version="9.9.9")
        bumped = plan_codex_command_render(
            bumped_catalog, mapping_from_catalog(bumped_catalog, "codex"), self.support)
        self.assertTrue(bumped.ok)
        current_by_id = {item.provenance.artifact_id: item for item in current.results}
        bumped_by_id = {item.provenance.artifact_id: item for item in bumped.results}
        self.assertEqual(set(current_by_id), set(bumped_by_id))
        for artifact_id in current_by_id:
            self.assertNotEqual(current_by_id[artifact_id].provenance.source_hash,
                                bumped_by_id[artifact_id].provenance.source_hash)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
