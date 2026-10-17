"""``apply``: the critical section of the migration under PlanLock, staging, rename, marker, import and failure paths."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import unittest
from unittest import mock

import workspace_fixture as fx
from workspace_fixture import PLAN_NAME, ARCHIVED_NAME, PROJECT_ID, SECRET, BridgeCase, tree

import apply as migrate_apply  # noqa: E402
import inspector  # noqa: E402
import partners  # noqa: E402
import verify  # noqa: E402

from aicore.util import schema  # noqa: E402

WORKSPACE = partners.workspace_module_root()
CONTRACT = WORKSPACE / "schemas" / "plans-migrator" / "v1" if WORKSPACE is not None else None
store = partners.planner_engine("plan.store")


def actions(answer: dict) -> dict:
    return {plan["name"]: plan["action"] for plan in answer["plans"]}


class ApplyTests(BridgeCase):
    def assert_nothing_moved(self):
        self.assertFalse((self.project_dir / "plans").exists())
        self.assertFalse((self.project_dir / "legacy-plans").exists())
        self.assertEqual(self.staging_entries(), [])
        self.assertIsNone(fx.read_marker(self.checkout))

    def test_initial_migration_moves_everything_and_switches_the_marker(self):
        source = tree(self.plans)
        answer = self.apply()
        self.assertEqual(answer["result"], "applied", answer)
        self.assertEqual(answer["phase"], "done")
        self.assertEqual(set(actions(answer).values()), {"copied"})
        self.assertEqual(sorted(actions(answer)), sorted([PLAN_NAME, ARCHIVED_NAME, "old-thing", "only-artifacts", "_root"]))
        plans = self.project_dir / "plans"
        self.assertEqual(sorted(path.name for path in plans.iterdir()), ["2026.10.05-№7-DEMO", "archive"])
        self.assertEqual((plans / PLAN_NAME / "plan.json").read_bytes(), (self.plans / PLAN_NAME / "plan.json").read_bytes())
        self.assertEqual((plans / ARCHIVED_NAME / "plan.json").is_file(), True)
        legacy = self.project_dir / "legacy-plans"
        self.assertEqual((legacy / "old-thing/notes.txt").read_bytes(), (self.plans / "old-thing/notes.txt").read_bytes())
        self.assertTrue((legacy / "only-artifacts/artifacts/a.txt").is_file())
        self.assertEqual((legacy / "_root/README.md").read_text(encoding="utf-8"), "top level\n")
        self.assertEqual((legacy / "_root/archive/NOTE.md").read_text(encoding="utf-8"), "archive note\n")
        for derived in ("views", "context", ".lock", "__pycache__"):
            self.assertFalse((plans / PLAN_NAME / derived).exists(), derived)
        self.assertEqual(fx.read_marker(self.checkout), {"$schema": "urn:swissknifeman:aicore:project-marker:v1",
                                                       "project_id": PROJECT_ID, "plans_store": "workspace"})
        after = tree(self.plans)
        after = {key: value for key, value in after.items() if not key.endswith(".lock")}  # PlanLock makes .lock files
        self.assertEqual(after, {key: value for key, value in source.items() if not key.endswith(".lock")},
                         "the source is not touched")
        self.assertEqual(self.staging_entries(), [])

    def test_answer_has_sizes_and_digests_and_no_content_or_absolute_path(self):
        manifest = inspector.inspect(self.checkout)
        answer = self.apply(manifest=manifest)
        text = fx.dump(answer)
        self.assertNotIn(SECRET, text)
        self.assertNotIn(str(self.checkout), text)
        self.assertNotIn(str(self.workspace), text)
        digests = {plan["name"]: plan["digest"] for plan in manifest["plans"]}
        for row in answer["plans"]:
            if row["name"] != "_root":
                self.assertEqual(row["digest"], digests[row["name"]])
            self.assertGreater(row["files"], 0)

    @unittest.skipIf(CONTRACT is None, "workspace module not found (set SKM_WORKSPACE_MODULE_ROOT)")
    def test_answers_match_the_contract(self):
        registry = schema.load_contract_set(CONTRACT)[0]
        request = self.request()
        self.assertEqual(schema.validate(request, "request", registry), [])
        self.assertEqual(schema.validate(migrate_apply.run(request, progress=None), "response", registry), [])
        refused = migrate_apply.run(dict(request, op_id="mig_other", mode="bogus"), progress=None)
        self.assertEqual(refused["code"], "INPUT_INVALID")
        self.assertEqual(schema.validate(refused, "response", registry), [])

    def test_apply_through_the_plugin_process(self):
        document = {"protocol": "1", "request_id": "r1", "op": "invoke", "point": "workspace:plans-migrator",
                    "input": self.request()}
        done = subprocess.run([sys.executable, str(partners.BRIDGE / "migrator.py")], input=fx.dump(document),
                              capture_output=True, text=True, encoding="utf-8", check=False, cwd=self.tmp,
                              env=dict(os.environ, AICORE_ROOT=str(partners.aicore_lib().parent)))
        self.assertEqual(done.returncode, 0, done.stderr)
        answer = json.loads(done.stdout)
        self.assertEqual((answer["status"], answer["output"]["result"]), ("ok", "applied"), answer)
        self.assertIn("workspace-planner: phase lock", done.stderr, "progress goes to stderr")
        self.assertNotIn(SECRET, done.stdout + done.stderr)
        self.assertEqual(fx.read_marker(self.checkout)["plans_store"], "workspace")

    def test_the_migrated_plans_load_and_check_like_the_source(self):
        self.assertEqual(self.apply()["result"], "applied")
        report = verify.compare_roots(self.project_dir / "plans", self.plans, unbound=True)
        self.assertTrue(report["ok"], report)
        self.assertEqual({row["name"] for row in report["plans"]}, {PLAN_NAME, ARCHIVED_NAME})

    def test_second_apply_is_a_noop(self):
        self.assertEqual(self.apply()["result"], "applied")
        again = self.apply(op_id="mig_again")
        self.assertEqual(again["result"], "noop", again)
        self.assertEqual(set(actions(again).values()), {"skipped-equal"})
        self.assertEqual(self.staging_entries(), [])

    def test_noop_refuses_when_the_workspace_copy_changed(self):
        self.assertEqual(self.apply()["result"], "applied")
        fx.write(self.project_dir / "plans" / PLAN_NAME / "artifacts/P1.1/out.txt", "edited in the workspace\n")
        again = self.apply(op_id="mig_again")
        self.assertEqual(again["code"], "MIGRATION_ALREADY_APPLIED")
        self.assertEqual(again["paths"], [PLAN_NAME])

    def test_marker_of_another_project_is_refused(self):
        other = "prj_" + "0" * 24 + "22"
        fx.aicore_workspace.write_marker(self.checkout, other, "legacy")
        answer = self.apply()
        self.assertEqual((answer["result"], answer["code"], answer["phase"]),
                         ("refused", "PROJECT_MARKER_MISMATCH", "request"))
        self.assertFalse((self.project_dir / "plans").exists())

    def test_legacy_marker_is_switched_and_keeps_its_project(self):
        fx.aicore_workspace.write_marker(self.checkout, PROJECT_ID, "legacy")
        self.assertEqual(self.apply()["result"], "applied")
        self.assertEqual(fx.read_marker(self.checkout)["plans_store"], "workspace")

    def test_source_changed_after_the_dry_run(self):
        manifest = inspector.inspect(self.checkout)
        fx.write(self.plans / "old-thing/notes.txt", "changed after the plan\n")
        answer = self.apply(manifest=manifest)
        self.assertEqual((answer["code"], answer["phase"]), ("MIGRATION_SOURCE_CHANGED", "digest"))
        self.assertEqual(answer["changed"], ["old-thing"])
        self.assert_nothing_moved()

    def test_a_new_plan_after_the_dry_run_is_a_source_change(self):
        manifest = inspector.inspect(self.checkout)
        fx.make_plan(self.plans, "2026.10.06-№8-DEMO-NEW")
        answer = self.apply(manifest=manifest)
        self.assertEqual(answer["code"], "MIGRATION_SOURCE_CHANGED")
        self.assertIn("2026.10.06-№8-DEMO-NEW", answer["changed"])
        self.assert_nothing_moved()

    def test_a_plan_removed_after_the_dry_run_is_a_source_change(self):
        manifest = inspector.inspect(self.checkout)
        shutil.rmtree(self.plans / PLAN_NAME)
        answer = self.apply(manifest=manifest)
        self.assertEqual((answer["code"], answer["phase"]), ("MIGRATION_SOURCE_CHANGED", "lock"))
        self.assertFalse((self.plans / PLAN_NAME).exists(), "the lock did not recreate the folder")
        self.assert_nothing_moved()

    def test_symlink_blocks_before_anything_is_copied(self):
        os.symlink(self.tmp, self.plans / "old-thing/link")
        answer = self.apply(manifest=inspector.inspect(self.checkout))
        self.assertEqual((answer["code"], answer["phase"]), ("MIGRATION_BLOCKED_SYMLINK", "digest"))
        self.assertEqual(answer["symlinks"], ["old-thing/link"])
        self.assertEqual(self.staging_entries(), [])
        self.assert_nothing_moved()

    # ---------------------------------------------------------------------------------------------- locks

    def test_apply_waits_for_a_plan_lock_and_goes_on(self):
        self.hold(self.plans / PLAN_NAME, 1.5)
        started = time.monotonic()
        answer = self.apply(lock_timeout_s=10)
        self.assertEqual(answer["result"], "applied", answer)
        self.assertGreaterEqual(time.monotonic() - started, 1.0)

    def test_plan_lock_timeout_is_migration_locked_and_releases_the_others(self):
        names = sorted([PLAN_NAME, ARCHIVED_NAME], key=lambda name: str(self.plans / name))
        self.hold(self.plans / names[1], 6)
        answer = self.apply(lock_timeout_s=0.3)
        self.assertEqual((answer["code"], answer["phase"], answer["locked"]), ("MIGRATION_LOCKED", "lock", [names[1]]))
        with store.PlanLock(self.plans / names[0], timeout=0.5):  # taken before the timeout, released after it
            pass
        self.assert_nothing_moved()

    def test_second_migration_of_the_project_is_locked(self):
        with migrate_apply.migration_lock(PROJECT_ID):
            answer = self.apply()
        self.assertEqual((answer["code"], answer["phase"]), ("MIGRATION_LOCKED", "lock"))
        self.assertEqual(answer["locked"], [f"migrate-{PROJECT_ID}"])
        self.assert_nothing_moved()

    def test_a_writer_after_the_switch_gets_plans_migrated(self):
        self.assertEqual(self.apply()["result"], "applied")
        with self.assertRaises(store.PlanError) as caught:
            with store.PlanLock(self.plans / PLAN_NAME, timeout=1):
                self.fail("the lock of a migrated plan must not be granted")
        self.assertEqual(caught.exception.code, "PLANS_MIGRATED")

    def test_a_writer_waiting_during_the_migration_gets_plans_migrated(self):
        code = ("import sys\n"
                f"sys.path.insert(0, {str(partners.require_planner_root() / 'lib')!r})\n"
                "from planner.plan import store\n"
                "import time\n"
                # The waiting writer and the migration compete for the lock the holder lets go (flock is not fair):
                # a writer granted before the switch is right, it only has to see PLANS_MIGRATED once the switch is done.
                "deadline = time.monotonic() + 30\n"
                "while time.monotonic() < deadline:\n"
                "    try:\n"
                "        with store.PlanLock(sys.argv[1], timeout=20):\n"
                "            print('GRANTED', flush=True)\n"
                "    except store.PlanError as exc:\n"
                "        print(exc.code, flush=True)\n"
                "        break\n"
                "    time.sleep(0.05)\n")
        self.hold(self.plans / PLAN_NAME, 2)
        writer = subprocess.Popen([sys.executable, "-c", code, str(self.plans / PLAN_NAME)],
                                  stdout=subprocess.PIPE, text=True, env=dict(os.environ))
        self.addCleanup(writer.stdout.close)
        self.addCleanup(writer.wait)
        time.sleep(0.3)  # the writer waits for the plan lock
        self.assertEqual(self.apply(lock_timeout_s=10)["result"], "applied")
        seen = writer.communicate(timeout=40)[0].split()
        self.assertEqual(seen[-1:], ["PLANS_MIGRATED"], seen)
        self.assertEqual(set(seen[:-1]) - {"GRANTED"}, set(), seen)

    # ----------------------------------------------------------------------------------- failure paths

    def test_failure_before_the_rename_leaves_no_trace(self):
        with mock.patch.dict(os.environ, {"SKM_MIGRATOR_FAIL_AT": "pre-rename"}):
            answer = self.apply()
        self.assertEqual((answer["result"], answer["code"], answer["phase"]), ("refused", "MIGRATION_FAILED", "rename"))
        self.assert_nothing_moved()

    def test_failure_while_copying_leaves_no_trace(self):
        with mock.patch.dict(os.environ, {"SKM_MIGRATOR_FAIL_AT": "copy"}):
            answer = self.apply()
        self.assertEqual((answer["code"], answer["phase"]), ("MIGRATION_FAILED", "copy"))
        self.assert_nothing_moved()

    def test_failed_verification_leaves_no_trace(self):
        real = verify.check_plan

        def worse(folder, unbound=False):
            result = real(folder, unbound)
            if unbound:
                result = dict(result, errors=result["errors"] + [("INJECTED", "plan.json")])
            return result
        with mock.patch.object(verify, "check_plan", worse):
            answer = self.apply()
        self.assertEqual((answer["code"], answer["phase"]), ("MIGRATION_VERIFY_FAILED", "verify"))
        self.assertEqual(answer["plans"][0]["new_errors"], [{"code": "INJECTED", "where": "plan.json"}])
        self.assert_nothing_moved()

    def test_a_red_plan_stays_the_same_red(self):
        item = self.plans / PLAN_NAME / "phases/P2/P2.2.json"
        document = json.loads(item.read_text(encoding="utf-8"))
        document["status"] = "not-a-status"
        item.write_text(json.dumps(document, indent=2), encoding="utf-8")
        red = verify.check_plan(self.plans / PLAN_NAME)
        self.assertTrue(red["errors"], "the fixture must be red before the migration")
        answer = self.apply()
        self.assertEqual(answer["result"], "applied", answer)
        report = verify.compare_roots(self.project_dir / "plans", self.plans, unbound=True)
        row = next(row for row in report["plans"] if row["name"] == PLAN_NAME)
        self.assertEqual(row["new_errors"], [])
        self.assertTrue(row["check_codes"])

    def test_failure_after_the_rename_is_completed_by_a_repeat(self):
        with mock.patch.dict(os.environ, {"SKM_MIGRATOR_FAIL_AT": "post-rename"}):
            failed = self.apply()
        self.assertEqual((failed["code"], failed["phase"]), ("MIGRATION_FAILED", "rename"))
        self.assertTrue((self.project_dir / "plans" / PLAN_NAME / "plan.json").is_file())
        self.assertIsNone(fx.read_marker(self.checkout), "the marker is switched last")
        again = self.apply(op_id="mig_resume")
        self.assertEqual(again["result"], "applied", again)
        self.assertEqual(set(actions(again).values()), {"skipped-equal"})
        self.assertEqual(fx.read_marker(self.checkout)["plans_store"], "workspace")

    def test_a_repeat_copies_what_the_failed_run_did_not_move(self):
        with mock.patch.dict(os.environ, {"SKM_MIGRATOR_FAIL_AT": "post-rename"}):
            self.apply()
        shutil.rmtree(self.project_dir / "legacy-plans")  # as if the run stopped between the two moves
        again = self.apply(op_id="mig_resume")
        self.assertEqual(again["result"], "applied", again)
        self.assertEqual(actions(again)[PLAN_NAME], "skipped-equal")
        self.assertEqual(actions(again)["old-thing"], "copied")
        self.assertTrue((self.project_dir / "legacy-plans" / "old-thing" / "notes.txt").is_file())

    def test_a_workspace_copy_that_differs_is_a_conflict_not_a_resume(self):
        fx.write(self.project_dir / "plans" / PLAN_NAME / "plan.json", "{}")
        answer = self.apply()
        self.assertEqual((answer["code"], answer["conflicts"]), ("MIGRATION_CONFLICT", [PLAN_NAME]))
        self.assertIsNone(fx.read_marker(self.checkout))
        self.assertEqual(self.staging_entries(), [])

    def test_a_stale_staging_folder_of_the_same_op_is_replaced(self):
        fx.write(self.workspace / ".staging" / "mig_test" / "junk.txt", "left by a dead process\n")
        self.assertEqual(self.apply()["result"], "applied")
        self.assertEqual(self.staging_entries(), [])

    def test_staging_of_another_operation_is_left_alone(self):
        fx.write(self.workspace / ".staging" / "mig_other" / "keep.txt", "another operation\n")
        with migrate_apply.migration_lock(PROJECT_ID):
            self.apply(op_id="mig_other")  # refused: the lock is held; must not remove the staging of that operation
        self.assertTrue((self.workspace / ".staging" / "mig_other" / "keep.txt").exists())

    def test_invalid_requests(self):
        for fields, code in (({"project_id": "nope"}, "INPUT_INVALID"), ({"op_id": "../x"}, "INPUT_INVALID"),
                             ({"manifest": {"x": 1}}, "INPUT_INVALID"), ({"on_conflict": "merge"}, "INPUT_INVALID"),
                             ({"project_root": "relative"}, "INPUT_INVALID"), ({"lock_timeout_s": -1}, "INPUT_INVALID")):
            answer = self.apply(**fields)
            self.assertEqual((answer["code"], answer["phase"]), (code, "request"), fields)
        self.assert_nothing_moved()

    # --------------------------------------------------------------------------------------- import mode

    def prepare_import(self):
        """The workspace holds a copy of the live plan (equal) and a different copy of the archived plan."""
        plans = self.project_dir / "plans"
        shutil.copytree(self.plans / PLAN_NAME, plans / PLAN_NAME,
                        ignore=shutil.ignore_patterns("views", "context", ".lock", "__pycache__"))
        shutil.copytree(self.plans / ARCHIVED_NAME, plans / ARCHIVED_NAME,
                        ignore=shutil.ignore_patterns("views", "context", ".lock", "__pycache__"))
        fx.write(plans / ARCHIVED_NAME / "artifacts/extra/local.txt", "local change of this machine\n")

    def test_import_without_on_conflict_refuses_on_a_differing_plan(self):
        self.prepare_import()
        answer = self.apply(mode="import")
        self.assertEqual((answer["code"], answer["phase"], answer["conflicts"]),
                         ("MIGRATION_CONFLICT", "plan", [ARCHIVED_NAME]))
        self.assertIsNone(fx.read_marker(self.checkout))
        self.assertEqual(self.staging_entries(), [])
        self.assertFalse((self.project_dir / "legacy-plans").exists(), "nothing moved before the refusal")

    def test_import_keep_workspace(self):
        self.prepare_import()
        before = tree(self.project_dir / "plans" / ARCHIVED_NAME)
        answer = self.apply(mode="import", on_conflict="keep-workspace")
        self.assertEqual(answer["result"], "applied", answer)
        self.assertEqual(actions(answer)[PLAN_NAME], "skipped-equal")
        self.assertEqual(actions(answer)[ARCHIVED_NAME], "kept-workspace")
        self.assertEqual(actions(answer)["old-thing"], "copied")
        self.assertEqual(tree(self.project_dir / "plans" / ARCHIVED_NAME), before)
        self.assertEqual(fx.read_marker(self.checkout)["plans_store"], "workspace")

    def test_import_copy_goes_next_to_the_workspace_plan(self):
        self.prepare_import()
        answer = self.apply(mode="import", on_conflict="import-copy")
        self.assertEqual(answer["result"], "applied", answer)
        row = next(plan for plan in answer["plans"] if plan["name"] == ARCHIVED_NAME)
        self.assertEqual((row["action"], row["stored_as"]), ("imported-copy", f"{ARCHIVED_NAME}~{fx.DEVICE}"))
        copy = self.project_dir / "plans" / f"{ARCHIVED_NAME}~{fx.DEVICE}"
        self.assertEqual(tree(copy), {key: value for key, value in tree(self.plans / ARCHIVED_NAME).items()
                                       if not key.startswith(("views/", "context/")) and key != ".lock"})
        self.assertTrue((self.project_dir / "plans" / ARCHIVED_NAME / "artifacts/extra/local.txt").exists())

    def test_import_adds_only_missing_plans(self):
        plans = self.project_dir / "plans"
        shutil.copytree(self.plans / PLAN_NAME, plans / PLAN_NAME,
                        ignore=shutil.ignore_patterns("views", "context", ".lock", "__pycache__"))
        answer = self.apply(mode="import")
        self.assertEqual(answer["result"], "applied", answer)
        self.assertEqual(actions(answer)[PLAN_NAME], "skipped-equal")
        self.assertEqual(actions(answer)[ARCHIVED_NAME], "copied")
        self.assertTrue((plans / ARCHIVED_NAME / "plan.json").is_file())

    def test_a_legacy_folder_that_differs_gets_the_device_suffix(self):
        fx.write(self.project_dir / "legacy-plans" / "old-thing" / "notes.txt", "other machine\n")
        answer = self.apply(mode="import")
        self.assertEqual(answer["result"], "applied", answer)
        row = next(plan for plan in answer["plans"] if plan["name"] == "old-thing")
        self.assertEqual((row["action"], row["stored_as"]), ("imported-copy", f"old-thing~{fx.DEVICE}"))
        self.assertEqual((self.project_dir / "legacy-plans" / "old-thing" / "notes.txt").read_text(encoding="utf-8"),
                         "other machine\n")
        self.assertTrue((self.project_dir / "legacy-plans" / f"old-thing~{fx.DEVICE}" / "notes.txt").is_file())

    def test_import_copy_needs_a_device_name(self):
        self.prepare_import()
        answer = self.apply(mode="import", on_conflict="import-copy", device_short=None)
        self.assertEqual((answer["code"], answer["phase"]), ("INPUT_INVALID", "plan"))
        self.assertIsNone(fx.read_marker(self.checkout))

    def test_an_empty_workspace_plans_folder_counts_as_absent(self):
        (self.project_dir / "plans").mkdir(parents=True)
        answer = self.apply()
        self.assertEqual(answer["result"], "applied", answer)
        self.assertTrue((self.project_dir / "plans" / PLAN_NAME / "plan.json").is_file())

    def test_a_project_without_v4_plans_still_gets_a_plans_folder(self):
        shutil.rmtree(self.plans / PLAN_NAME)
        shutil.rmtree(self.plans / "archive" / "2026.09.01-№3-DEMO")
        answer = self.apply()
        self.assertEqual(answer["result"], "applied", answer)
        self.assertTrue((self.project_dir / "plans").is_dir(), "the resolver needs the folder")
        self.assertEqual(list((self.project_dir / "plans").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
