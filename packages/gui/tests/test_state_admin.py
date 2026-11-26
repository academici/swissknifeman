"""gui state check|rebuild: integrity report, row-exact rebuild, dry run, rollback and the CLI."""
import hashlib
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import aicore

import gui
from gui.backend import InstanceLock
from gui.core import state_admin
from gui.storage import db
import subprocess


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def populate(conn):
    conn.execute("INSERT INTO projects VALUES ('p1', '/work/a', 'a', 1, 'open', '2026-10-17T00:00:00Z')")
    conn.execute("INSERT INTO prefs VALUES ('theme', '\"dark\"', '2026-10-17T00:00:00Z')")
    for index in range(5):
        db.audit(conn, actor="user", action=f"act{index}", target="t", decision="allow", details={"i": index})
    conn.execute("INSERT INTO plugins VALUES ('x', 'enabled', NULL, NULL, 1, 'sha256:aa', '[\"net\"]', 'unit', 'now')")
    conn.execute("INSERT INTO plugins VALUES ('y', 'disabled', 'then', 'CRASH', 0, NULL, '[]', 'unit', 'now')")
    conn.execute("INSERT INTO plugin_events (plugin, at, kind, code, detail) VALUES ('x', 'now', 'start', NULL, 'd')")
    conn.execute("INSERT INTO plugin_events (plugin, at, kind, code, detail) VALUES ('y', 'now', 'crash', 'C', NULL)")
    conn.execute("INSERT INTO grants VALUES ('g1', 'x', 'net', 'p1', 'sha256:aa', 'now', NULL, 'user', NULL, NULL, NULL)")
    conn.execute("INSERT INTO runs (run_id, command, owner, state, dry_run, context_json, input_json, created_at, "
                 "actor_json, permission_json, log_json, correlation_id) "
                 "VALUES ('r1', 'c', 'o', 'done', 0, '{}', '{}', 'now', '{}', '{}', '{}', 'cid')")
    conn.execute("INSERT INTO run_transitions VALUES ('r1', 1, NULL, 'queued', 'now')")
    conn.execute("INSERT INTO run_transitions VALUES ('r1', 2, 'queued', 'done', 'now')")


def dump(path):
    conn = sqlite3.connect(str(path))
    try:
        return {table: sorted(conn.execute(f"SELECT * FROM {table}").fetchall()) for table in state_admin.TABLES}
    finally:
        conn.close()


class StateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.folder = self.tmp / "gui"
        self.folder.mkdir(mode=0o700)
        self.path = self.folder / "gui.db"
        conn = db.open_db(self.path)
        populate(conn)
        conn.close()


class TestCheck(StateCase):
    def test_healthy(self):
        report = state_admin.check(self.path)
        self.assertTrue(report["ok"], report)
        self.assertEqual(db.schema_version(), report["schema_version"])
        self.assertEqual(["ok"], report["integrity"])
        self.assertEqual(5, report["tables"]["audit"])
        self.assertEqual(2, report["tables"]["plugins"])

    def test_missing_file(self):
        report = state_admin.check(self.folder / "none.db")
        self.assertFalse(report["ok"])
        self.assertFalse(report["exists"])

    def test_not_sqlite(self):
        self.path.write_bytes(b"this is not a database" * 100)
        report = state_admin.check(self.path)
        self.assertFalse(report["ok"])
        self.assertTrue(report["problems"])

    def test_newer_schema(self):
        conn = sqlite3.connect(str(self.path))
        conn.execute(f"PRAGMA user_version = {db.schema_version() + 1}")
        conn.close()
        report = state_admin.check(self.path)
        self.assertFalse(report["ok"])
        self.assertIn("newer", report["problems"][0])

    def test_foreign_key_violation(self):
        conn = sqlite3.connect(str(self.path))
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("INSERT INTO run_transitions VALUES ('ghost', 1, NULL, 'queued', 'now')")
        conn.commit()
        conn.close()
        report = state_admin.check(self.path)
        self.assertFalse(report["ok"])
        self.assertEqual(1, report["foreign_key_violations"])

    def test_does_not_write(self):
        before = digest(self.path)
        state_admin.check(self.path)
        self.assertEqual(before, digest(self.path))


class TestRebuild(StateCase):
    def test_rows_survive_and_backup_exists(self):
        before = dump(self.path)
        report = state_admin.rebuild(self.folder)
        self.assertTrue(report["rebuilt"])
        self.assertEqual(before, dump(self.path))
        for table in state_admin.OPERATOR_TABLES:
            self.assertTrue(before[table], table)
        backup = Path(report["backup"])
        self.assertTrue(backup.is_file())
        self.assertEqual(before, dump(backup))
        self.assertEqual(0o600, backup.stat().st_mode & 0o777)
        self.assertEqual(0o600, self.path.stat().st_mode & 0o777)
        self.assertTrue(state_admin.check(self.path)["ok"])
        self.assertEqual([], [p.name for p in self.folder.iterdir() if p.name.startswith(".gui.db.new")])
        conn = db.open_db(self.path)  # opens and migrates like the backend does
        self.assertEqual(5, conn.execute("SELECT count(*) FROM audit").fetchone()[0])
        conn.close()

    def test_idempotent(self):
        first = state_admin.rebuild(self.folder)
        second = state_admin.rebuild(self.folder)
        self.assertNotEqual(first["backup"], second["backup"])
        self.assertEqual(dump(Path(first["backup"])), dump(self.path))
        self.assertEqual(dump(Path(second["backup"])), dump(self.path))

    def test_old_schema_is_upgraded(self):
        old = self.tmp / "old"
        old.mkdir()
        conn = db.open_db(old / "gui.db", migrations=db.MIGRATIONS[:2])
        conn.execute("INSERT INTO prefs VALUES ('k', '1', 'now')")
        conn.close()
        report = state_admin.rebuild(old)
        self.assertEqual((2, db.schema_version()), (report["from_version"], report["to_version"]))
        conn = db.open_db(old / "gui.db")
        self.assertEqual(1, conn.execute("SELECT count(*) FROM prefs").fetchone()[0])
        self.assertEqual(0, conn.execute("SELECT count(*) FROM plugins").fetchone()[0])
        conn.close()

    def test_dry_run_writes_nothing(self):
        before_hash, before_mtime = digest(self.path), os.stat(self.path).st_mtime_ns
        report = state_admin.rebuild(self.folder, dry_run=True)
        self.assertTrue(report["dry_run"])
        self.assertFalse(report["rebuilt"])
        self.assertEqual(2, report["tables"]["plugins"]["rows"])
        self.assertEqual(before_hash, digest(self.path))
        self.assertEqual(before_mtime, os.stat(self.path).st_mtime_ns)
        # a read-only WAL reader may leave gui.db-wal/-shm; no backup and no new database appear
        self.assertEqual([], [p.name for p in self.folder.iterdir() if ".bak-" in p.name or ".new-" in p.name])

    def test_failure_in_the_middle_leaves_the_original(self):
        before_hash, before_mtime = digest(self.path), os.stat(self.path).st_mtime_ns
        real, calls = state_admin._copy_table, []

        def flaky(conn, table, columns):
            calls.append(table)
            if len(calls) == 4:
                raise sqlite3.OperationalError("disk I/O error")
            real(conn, table, columns)

        with mock.patch.object(state_admin, "_copy_table", flaky):
            with self.assertRaises(state_admin.StateError) as caught:
                state_admin.rebuild(self.folder)
        self.assertEqual(state_admin.REBUILD_FAILED, caught.exception.code)
        self.assertEqual(4, len(calls))
        self.assertEqual(before_hash, digest(self.path))
        self.assertEqual(before_mtime, os.stat(self.path).st_mtime_ns)
        self.assertEqual([], [p.name for p in self.folder.iterdir() if p.name.startswith(".gui.db.new")])

    def test_failure_of_the_swap_leaves_the_original(self):
        before = digest(self.path)
        with mock.patch.object(state_admin.os, "replace", side_effect=OSError("denied")):
            with self.assertRaises(state_admin.StateError):
                state_admin.rebuild(self.folder)
        self.assertEqual(before, digest(self.path))
        self.assertEqual([], [p.name for p in self.folder.iterdir() if p.name.startswith(".gui.db.new")])

    def test_row_loss_is_detected_before_the_swap(self):
        before = digest(self.path)
        real = state_admin._copy_table

        def lossy(conn, table, columns):
            real(conn, table, columns)
            if table == "grants":
                conn.execute("DELETE FROM main.grants")

        with mock.patch.object(state_admin, "_copy_table", lossy):
            with self.assertRaises(state_admin.StateError) as caught:
                state_admin.rebuild(self.folder)
        self.assertIn("grants", caught.exception.message)
        self.assertEqual(before, digest(self.path))

    def test_not_a_database_is_refused_untouched(self):
        self.path.write_bytes(b"garbage" * 200)
        before = digest(self.path)
        with self.assertRaises(state_admin.StateError):
            state_admin.rebuild(self.folder)
        self.assertEqual(before, digest(self.path))

    def test_newer_schema_is_refused(self):
        conn = sqlite3.connect(str(self.path))
        conn.execute(f"PRAGMA user_version = {db.schema_version() + 1}")
        conn.close()
        with self.assertRaises(state_admin.StateError) as caught:
            state_admin.rebuild(self.folder)
        self.assertEqual(state_admin.INCOMPATIBLE, caught.exception.code)

    def test_missing_file(self):
        with self.assertRaises(state_admin.StateError) as caught:
            state_admin.rebuild(self.tmp)
        self.assertEqual(state_admin.MISSING, caught.exception.code)


class TestCli(StateCase):
    def setUp(self):
        super().setUp()
        self.env = {**os.environ, "HOME": str(self.tmp / "home"), "SKM_HOME": str(self.tmp / "skm"),
                    "PYTHONPATH": os.pathsep.join(str(Path(module.__file__).resolve().parents[1])
                                                  for module in (gui, aicore))}
        self.env.pop("SKM_PROJECT_ROOT", None)
        (self.tmp / "home").mkdir()
        self.state = self.tmp / "skm" / "state" / "gui"
        self.state.mkdir(parents=True)
        shutil.copy(self.path, self.state / "gui.db")

    def gui(self, *argv):
        return subprocess.run([sys.executable, "-m", "gui.cli", *argv], env=self.env, cwd=str(self.tmp),
                              capture_output=True, text=True, timeout=60)

    def test_check_json(self):
        done = self.gui("state", "check", "--json")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertTrue(json.loads(done.stdout)["ok"])

    def test_check_fails_on_garbage(self):
        (self.state / "gui.db").write_bytes(b"nope" * 100)
        done = self.gui("state", "check")
        self.assertEqual(1, done.returncode)
        self.assertIn("FAILED", done.stdout)

    def test_rebuild_and_dry_run(self):
        done = self.gui("state", "rebuild", "--dry-run", "--json")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertFalse(json.loads(done.stdout)["rebuilt"])
        done = self.gui("state", "rebuild", "--json")
        self.assertEqual(0, done.returncode, done.stderr)
        self.assertTrue(json.loads(done.stdout)["rebuilt"])
        self.assertEqual(dump(self.path), dump(self.state / "gui.db"))

    def test_rebuild_refused_while_the_backend_runs(self):
        lock = InstanceLock(self.state).acquire()
        self.addCleanup(lock.release)
        before = digest(self.state / "gui.db")
        done = self.gui("state", "rebuild")
        self.assertEqual(1, done.returncode)
        self.assertIn("BACKEND_RUNNING", done.stderr)
        self.assertEqual(before, digest(self.state / "gui.db"))


if __name__ == "__main__":
    unittest.main()
