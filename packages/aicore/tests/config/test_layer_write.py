"""Layer writes: revision, plan_layer_edit, layer_lock, apply_layer_patch (CAS, rollback) and races of processes."""
import json
import os
import random
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from aicore import config
from aicore.config import ConfigError, toml
from aicore.state import list_backups
from aicore.util import io as _io

from tests.config.support import Workspace

LIB = str(Path(config.__file__).resolve().parents[2])
MAPS_SCHEMA = Path(__file__).resolve().parent / "fixtures" / "maps" / "configs" / "config.schema.json"

COMMENTED = """\
# Machine configuration of demo
schema_version = 1

[demo]
mode = "safe"   # keep this comment
verbose = true

[demo.recompute]
candidate_min_n = 18   # and this one
"""

EMPTY_REVISION = config.layer_revision(b"")


def child_env(home):
    env = dict(os.environ)
    env.update({"PYTHONPATH": LIB, "HOME": str(home)})
    return env


def run_child(code, *args, home, **kwargs):
    return subprocess.Popen([sys.executable, "-c", code, *args], env=child_env(home), text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs)


HOLDER = """
import sys
from aicore.config import layer_lock
with layer_lock(sys.argv[1], timeout_s=5):
    print("ready", flush=True)
    sys.stdin.readline()
"""

WRITER = """
import sys
from aicore import config
path, prefix, count = sys.argv[1], sys.argv[2], int(sys.argv[3])
schema = config.load_module_schema(sys.argv[4], "maps")
for i in range(count):
    config.apply_layer_patch(path, "maps", [("set", "hooks.%s-%d.level" % (prefix, i), 3)], schema=schema,
                             layer="machine", lock_timeout_s=30)
"""

CAS = """
import sys
from aicore import config
path, name, revision = sys.argv[1], sys.argv[2], sys.argv[3]
schema = config.load_module_schema(sys.argv[4], "maps")
try:
    config.apply_layer_patch(path, "maps", [("set", "hooks.%s.level" % name, 4)], schema=schema, layer="machine",
                             expected_revision=revision, lock_timeout_s=30)
    print("ok")
except config.ConfigError as exc:
    print(exc.code)
"""


class TestRevision(Workspace):
    def test_revision_is_the_tagged_digest_of_the_bytes(self):
        self.assertEqual(EMPTY_REVISION, config.layer_revision(b""))
        self.assertRegex(EMPTY_REVISION, r"^sha256:[0-9a-f]{64}$")
        self.assertNotEqual(EMPTY_REVISION, config.layer_revision(b"\n"))

    def test_missing_and_empty_file_have_the_same_revision(self):
        missing = config.read_layer(self.machine_file, "demo", schema=self.schema, layer="machine")
        self.assertEqual((missing.exists, missing.text, missing.revision, missing.values),
                         (False, "", EMPTY_REVISION, {}))
        self.write(self.machine_file, "")
        empty = config.read_layer(self.machine_file, "demo", schema=self.schema, layer="machine")
        self.assertEqual((empty.exists, empty.revision), (True, EMPTY_REVISION))

    def test_bom_is_part_of_the_revision_but_not_of_the_text(self):
        raw = b"\xef\xbb\xbf" + b'schema_version = 1\n[demo]\nmode = "fast"\n'
        self.machine_file.parent.mkdir(parents=True)
        self.machine_file.write_bytes(raw)
        snap = config.read_layer(self.machine_file, "demo", schema=self.schema, layer="machine")
        self.assertEqual(snap.revision, config.layer_revision(raw))
        self.assertTrue(snap.text.startswith("schema_version"))
        self.assertEqual(snap.values, {"mode": "fast"})
        self.assertEqual(snap.lines, {"mode": 3})

    def test_snapshot_values_and_lines_of_nested_keys(self):
        self.write(self.machine_file, COMMENTED)
        snap = config.read_layer(self.machine_file, "demo", schema=self.schema, layer="machine")
        self.assertEqual(snap.values, {"mode": "safe", "verbose": True, "recompute.candidate_min_n": 18})
        self.assertEqual(snap.lines["recompute.candidate_min_n"], 9)

    def test_invalid_file_is_reported(self):
        self.write(self.machine_file, "not toml [[[")
        with self.assertRaises(ConfigError):
            config.read_layer(self.machine_file, "demo", schema=self.schema, layer="machine")

    def test_comment_change_changes_the_revision(self):
        self.write(self.machine_file, COMMENTED)
        first = config.read_layer(self.machine_file, "demo", schema=self.schema, layer="machine").revision
        self.write(self.machine_file, COMMENTED + "# more\n")
        self.assertNotEqual(first, config.read_layer(self.machine_file, "demo", schema=self.schema,
                                                     layer="machine").revision)


class TestPlan(Workspace):
    def plan(self, text, ops, **kwargs):
        return config.plan_layer_edit(text, "demo", ops, schema=self.schema, layer="machine", **kwargs)

    def test_plan_is_pure(self):
        self.write(self.machine_file, COMMENTED)
        before = self.machine_file.stat().st_mtime_ns
        missing = self.root / "nowhere" / "config.toml"
        plan = self.plan(COMMENTED, [("set", "mode", "fast")], file=str(missing))
        self.assertTrue(plan.changed)
        self.assertEqual(before, self.machine_file.stat().st_mtime_ns)
        self.assertFalse(missing.parent.exists())
        self.assertEqual(sorted(p.name for p in self.machine_file.parent.iterdir()), ["config.toml"])

    def test_three_ops_keep_comments_and_order(self):
        plan = self.plan(COMMENTED, [("set", "mode", "fast"), ("unset", "verbose", None),
                                     ("set", "recompute.candidate_min_n", 25)])
        self.assertEqual(plan.issues, ())
        self.assertEqual(plan.text_after, COMMENTED.replace('"safe"', '"fast"').replace("verbose = true\n", "")
                         .replace("= 18", "= 25"))
        self.assertEqual(plan.before, {"mode": "safe", "verbose": True, "recompute.candidate_min_n": 18})
        self.assertEqual(plan.after, {"mode": "fast", "recompute.candidate_min_n": 25})

    def test_empty_text_starts_with_the_version_line(self):
        plan = self.plan("", [("set", "mode", "fast")])
        self.assertEqual(plan.text_after, 'schema_version = 1\n\n[demo]\nmode = "fast"\n')
        self.assertEqual((plan.changed, plan.before, plan.after), (True, {}, {"mode": "fast"}))

    def test_unset_of_absent_key_changes_nothing(self):
        plan = self.plan("", [("unset", "mode", None)])
        self.assertEqual((plan.changed, plan.text_after), (False, ""))

    def test_each_bad_op_is_an_issue_and_good_ones_still_apply(self):
        ops = [("set", "mode", "turbo"), ("set", "nope", 1), ("set", "token", "plain-secret-value"),
               ("set", "cache_dir", "x"), ("set", "verbose", True), ("flip", "verbose", None)]
        plan = self.plan("", ops, file="proj.toml")
        self.assertEqual([issue.code for issue in plan.issues],
                         ["CONFIG_TYPE", "CONFIG_UNKNOWN_KEY", "SECRET_REF_INVALID", "CONFIG_EDIT_REFUSED"])
        self.assertEqual(plan.after, {"cache_dir": "x", "verbose": True})
        self.assertNotIn("plain-secret-value", " ".join(str(issue) for issue in plan.issues))
        self.assertNotIn("plain-secret-value", plan.text_after)

    def test_layer_forbidden_is_an_issue(self):
        plan = config.plan_layer_edit("", "demo", [("set", "cache_dir", "x")], schema=self.schema, layer="project")
        self.assertEqual([issue.code for issue in plan.issues], ["CONFIG_LAYER_FORBIDDEN"])
        self.assertFalse(plan.changed)

    def test_secret_reference_is_accepted(self):
        plan = self.plan("", [("set", "token", "env://DEMO_TOKEN")])
        self.assertEqual((plan.issues, plan.after), ((), {"token": "env://DEMO_TOKEN"}))

    def test_toml_refusal_is_an_edit_refused_issue_and_still_a_toml_edit_error(self):
        text = 'schema_version = 1\n[demo]\nsources = [\n  "a",\n]\n'
        plan = self.plan(text, [("set", "sources", ["b"])])
        refusals = [i for i in plan.issues if i.code == "CONFIG_EDIT_REFUSED"]
        for issue in refusals:
            self.assertIsInstance(issue, config.toml_edit.TomlEditError)

    def test_bad_layer_is_a_value_error(self):
        with self.assertRaises(ValueError):
            config.plan_layer_edit("", "demo", [], schema=self.schema, layer="env")

    def test_random_sequences_round_trip(self):
        rng = random.Random(20261016)
        choices = {"mode": ["fast", "safe"], "verbose": [True, False], "recompute.candidate_min_n": [1, 18, 999],
                   "recompute.ratio": [0.25, 1.0], "recompute.window.days": [3, 30], "sources": [["a"], ["b", "c"]],
                   "limits.retries": [0, 5], "cache_dir": ["", "/tmp/x"]}
        keys = sorted(choices)
        for _ in range(200):
            text, expected = COMMENTED, {"mode": "safe", "verbose": True, "recompute.candidate_min_n": 18}
            ops = []
            for _step in range(rng.randint(1, 8)):
                key = rng.choice(keys)
                if rng.random() < 0.35:
                    ops.append(("unset", key, None))
                    expected.pop(key, None)
                else:
                    value = rng.choice(choices[key])
                    ops.append(("set", key, value))
                    expected[key] = value
            plan = self.plan(text, ops)
            self.assertEqual(plan.issues, (), ops)
            section = toml.loads(plan.text_after)["demo"]
            flat = {}

            def walk(body, base=()):
                for name, value in body.items():
                    if isinstance(value, dict):
                        walk(value, base + (name,))
                    else:
                        flat[".".join(base + (name,))] = value
            walk(section)
            self.assertEqual(flat, expected, ops)
            if "mode" in expected and expected["mode"] == "safe" and not any(op[1] == "mode" for op in ops):
                self.assertIn("# keep this comment", plan.text_after)
            if not any(op[1] == "recompute.candidate_min_n" for op in ops):
                self.assertIn("# and this one", plan.text_after)


class TestApply(Workspace):
    def apply(self, ops, path=None, **kwargs):
        kwargs.setdefault("layer", "machine")
        kwargs.setdefault("env", self.env)
        return config.apply_layer_patch(path or self.machine_file, "demo", ops, schema=self.schema, **kwargs)

    def test_patch_writes_backs_up_and_returns_the_new_revision(self):
        self.write(self.machine_file, COMMENTED)
        old = config.layer_revision(COMMENTED.encode())
        result = self.apply([("set", "mode", "fast"), ("unset", "verbose", None)], expected_revision=old)
        self.assertTrue(result.changed)
        self.assertEqual(len(list_backups(env=self.env)), 1)
        self.assertEqual(result.revision, config.layer_revision(self.machine_file.read_bytes()))
        self.assertEqual(self.resolve().get("mode"), "fast")
        self.assertIn("# keep this comment", self.machine_file.read_text(encoding="utf-8"))

    def test_unchanged_patch_returns_the_current_revision_and_writes_nothing(self):
        self.write(self.machine_file, COMMENTED)
        result = self.apply([("set", "mode", "safe")])
        self.assertEqual((result.changed, result.backup, result.revision),
                         (False, None, config.layer_revision(COMMENTED.encode())))
        self.assertEqual(self.machine_file.read_text(encoding="utf-8"), COMMENTED)

    def test_edit_result_still_unpacks_to_two(self):
        changed, saved = self.apply([("set", "mode", "fast")])
        self.assertEqual((changed, saved), (True, None))

    def test_conflict_leaves_file_and_backups_alone(self):
        self.write(self.machine_file, COMMENTED)
        with self.assertRaises(ConfigError) as caught:
            self.apply([("set", "mode", "fast")], expected_revision="sha256:" + "0" * 64)
        self.assertEqual(caught.exception.code, "CONFIG_REVISION_CONFLICT")
        self.assertEqual(self.machine_file.read_text(encoding="utf-8"), COMMENTED)
        self.assertEqual(list_backups(env=self.env), [])

    def test_conflict_on_a_missing_file_creates_no_layer_file(self):
        with self.assertRaises(ConfigError) as caught:
            self.apply([("set", "mode", "fast")], expected_revision="sha256:" + "1" * 64)
        self.assertEqual(caught.exception.code, "CONFIG_REVISION_CONFLICT")
        self.assertFalse(self.machine_file.exists())

    def test_expected_revision_of_a_missing_file_is_the_empty_digest(self):
        result = self.apply([("set", "mode", "fast")], expected_revision=EMPTY_REVISION)
        self.assertEqual((result.changed, result.backup), (True, None))

    def test_issue_is_raised_and_nothing_is_written(self):
        self.write(self.machine_file, COMMENTED)
        with self.assertRaises(ConfigError) as caught:
            self.apply([("set", "mode", "fast"), ("set", "mode", "turbo")])
        self.assertEqual(caught.exception.code, "CONFIG_TYPE")
        self.assertEqual(self.machine_file.read_text(encoding="utf-8"), COMMENTED)

    def test_secret_value_is_not_written_nor_quoted(self):
        with self.assertRaises(ConfigError) as caught:
            self.apply([("set", "token", "hunter2-secret")])
        self.assertNotIn("hunter2-secret", str(caught.exception))
        self.assertFalse(self.machine_file.exists())

    def test_corrupted_write_is_rolled_back_to_the_backup(self):
        self.write(self.machine_file, COMMENTED)

        def corrupt(path, text, **kwargs):
            _io.durable_replace(path, b"garbage [[[", mode=kwargs.get("mode"))

        with mock.patch("aicore.util.io.atomic_write_text", corrupt):
            with self.assertRaises(ConfigError) as caught:
                self.apply([("set", "mode", "fast")])
        self.assertEqual(caught.exception.code, "CONFIG_FILE_INVALID")
        self.assertEqual(self.machine_file.read_text(encoding="utf-8"), COMMENTED)

    def test_corrupted_write_of_a_new_file_removes_it(self):
        def corrupt(path, text, **kwargs):
            _io.durable_replace(path, b"garbage [[[", mode=kwargs.get("mode"))

        with mock.patch("aicore.util.io.atomic_write_text", corrupt):
            with self.assertRaises(ConfigError) as caught:
                self.apply([("set", "mode", "fast")])
        self.assertEqual(caught.exception.code, "CONFIG_FILE_INVALID")
        self.assertFalse(self.machine_file.exists())

    def test_symlink_stays_a_symlink(self):
        real = self.root / "real" / "config.toml"
        self.write(real, COMMENTED)
        self.machine_file.parent.mkdir(parents=True)
        self.machine_file.symlink_to(real)
        self.apply([("set", "mode", "fast")])
        self.assertTrue(self.machine_file.is_symlink())
        self.assertIn('mode = "fast"', real.read_text(encoding="utf-8"))
        self.assertTrue(Path(str(real) + ".lock").exists())

    def test_mode_of_the_file_is_kept(self):
        self.write(self.machine_file, COMMENTED)
        os.chmod(self.machine_file, 0o640)
        self.apply([("set", "mode", "fast")])
        self.assertEqual(self.machine_file.stat().st_mode & 0o777, 0o640)

    def test_lock_file_is_private_and_stays(self):
        self.apply([("set", "mode", "fast")])
        lock = Path(str(self.machine_file) + ".lock")
        self.assertTrue(lock.exists())
        self.assertEqual(lock.stat().st_mode & 0o777, 0o600)

    def test_bad_layer(self):
        with self.assertRaises(ValueError):
            self.apply([], layer="env")

    def test_edit_layer_file_goes_through_the_patch(self):
        result = config.edit_layer_file(self.machine_file, "demo", "mode", "fast", schema=self.schema,
                                        env=self.env)
        self.assertEqual(result.revision, config.layer_revision(self.machine_file.read_bytes()))


class TestResolveTexts(Workspace):
    def test_layer_texts_replace_the_files(self):
        self.machine('[demo]\nmode = "fast"\n')
        text = 'schema_version = 1\n[demo]\nmode = "safe"\nverbose = true\n'
        resolved = self.resolve(layer_texts={"machine": text})
        self.assertEqual((resolved.get("mode"), resolved.get("verbose")), ("safe", True))
        entry = [e for e in resolved.explain() if e.key == "mode"][0]
        self.assertEqual((entry.layer, entry.file), ("machine", str(self.machine_file)))
        self.assertEqual(self.resolve().get("mode"), "fast")

    def test_project_text_without_a_file(self):
        resolved = self.resolve(layer_texts={"project": 'schema_version = 1\n[demo]\nmode = "fast"\n'})
        self.assertEqual(resolved.get("mode"), "fast")
        self.assertFalse(self.project_file.exists())

    def test_empty_text_hides_the_file(self):
        self.machine('[demo]\nmode = "fast"\n')
        self.assertEqual(self.resolve(layer_texts={"machine": ""}).get("mode"), "safe")


class TestLock(Workspace):
    def test_lock_times_out_while_another_process_holds_it(self):
        target = self.root / "x" / "config.toml"
        holder = run_child(HOLDER, str(target), home=self.root, stdin=subprocess.PIPE)
        self.addCleanup(holder.stderr.close)
        self.addCleanup(holder.stdout.close)
        self.addCleanup(holder.stdin.close)
        self.addCleanup(holder.kill)
        self.assertEqual(holder.stdout.readline().strip(), "ready")
        started = time.monotonic()
        with self.assertRaises(ConfigError) as caught:
            with config.layer_lock(target, timeout_s=0.2):
                self.fail("lock must not be granted")
        self.assertEqual(caught.exception.code, "CONFIG_LOCKED")
        self.assertLess(time.monotonic() - started, 2)
        with self.assertRaises(ConfigError) as patch:
            config.apply_layer_patch(target, "demo", [("set", "mode", "fast")], schema=self.schema,
                                     layer="machine", lock_timeout_s=0.2)
        self.assertEqual(patch.exception.code, "CONFIG_LOCKED")
        self.assertFalse(target.exists())
        holder.stdin.write("\n")
        holder.stdin.flush()
        holder.wait(timeout=5)
        with config.layer_lock(target, timeout_s=1):
            pass

    def test_lock_is_released_after_an_error(self):
        target = self.root / "y" / "config.toml"
        with self.assertRaises(RuntimeError):
            with config.layer_lock(target):
                raise RuntimeError("boom")
        with config.layer_lock(target, timeout_s=0.2):
            pass


class TestRaces(Workspace):
    def test_two_processes_lose_no_update(self):
        target = self.machine_file
        workers = [run_child(WRITER, str(target), name, "25", str(MAPS_SCHEMA), home=self.root)
                   for name in ("a", "b")]
        for worker in workers:
            _out, err = worker.communicate(timeout=120)
            self.assertEqual(worker.returncode, 0, err)
        hooks = toml.loads(target.read_text(encoding="utf-8"))["maps"]["hooks"]
        self.assertEqual(sorted(hooks), sorted(f"{p}-{i}" for p in "ab" for i in range(25)))

    def test_same_revision_commits_once(self):
        target = self.machine_file
        self.write(target, "schema_version = 1\n")
        revision = config.layer_revision(target.read_bytes())
        workers = [run_child(CAS, str(target), name, revision, str(MAPS_SCHEMA), home=self.root)
                   for name in ("p", "q")]
        results = []
        for worker in workers:
            out, err = worker.communicate(timeout=60)
            self.assertEqual(worker.returncode, 0, err)
            results.append(out.strip())
        self.assertEqual(sorted(results), ["CONFIG_REVISION_CONFLICT", "ok"])
        hooks = toml.loads(target.read_text(encoding="utf-8"))["maps"]["hooks"]
        self.assertEqual(len(hooks), 1)


if __name__ == "__main__":
    unittest.main()
