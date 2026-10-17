"""gui.storage.db: migrations by user_version, WAL, file modes and refusal of a newer database."""
import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from gui.errors import GuiError
from gui.storage import db


class TestOpen(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.path = self.tmp / "state" / "gui" / "gui.db"

    def test_migrates_from_scratch(self):
        conn = db.open_db(self.path)
        self.addCleanup(conn.close)
        self.assertEqual(db.schema_version(), conn.execute("PRAGMA user_version").fetchone()[0])
        self.assertEqual("wal", conn.execute("PRAGMA journal_mode").fetchone()[0])
        self.assertEqual(1, conn.execute("PRAGMA foreign_keys").fetchone()[0])
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertLessEqual({"projects", "prefs", "audit", "runs", "run_transitions"}, tables)
        self.assertEqual(0o600, stat.S_IMODE(os.stat(self.path).st_mode))
        self.assertEqual(0o700, stat.S_IMODE(os.stat(self.path.parent).st_mode))

    def test_migration_3_creates_the_plugin_tables(self):
        conn = db.open_db(self.path)
        self.addCleanup(conn.close)
        self.assertGreaterEqual(db.schema_version(), 3)
        columns = {table: [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
                   for table in ("plugins", "plugin_events", "grants")}
        self.assertEqual(["id", "desired", "quarantined_at", "quarantine_code", "reapproval", "digest", "effects_json",
                          "source", "updated_at"], columns["plugins"])
        self.assertEqual(["id", "plugin", "at", "kind", "code", "detail"], columns["plugin_events"])
        self.assertEqual(["id", "plugin", "capability", "project_id", "manifest_digest", "granted_at", "expires_at",
                          "granted_by", "revoked_at", "voided_at", "void_reason"], columns["grants"])
        indexes = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'index'")}
        self.assertLessEqual({"plugin_events_by_plugin", "grants_by_plugin"}, indexes)
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO plugins (id, desired, source, updated_at) VALUES ('x', 'bogus', 'unit', 'now')")

    def test_database_of_version_2_is_upgraded_to_3(self):
        conn = db.open_db(self.path, migrations=db.MIGRATIONS[:2])
        conn.execute("INSERT INTO prefs (key, value_json, updated_at) VALUES ('k', '1', 'now')")
        conn.close()
        conn = db.open_db(self.path)
        self.addCleanup(conn.close)
        self.assertEqual(db.schema_version(), conn.execute("PRAGMA user_version").fetchone()[0])
        self.assertEqual(1, conn.execute("SELECT COUNT(*) FROM prefs").fetchone()[0])
        self.assertEqual(0, conn.execute("SELECT COUNT(*) FROM plugins").fetchone()[0])

    def test_reopen_is_a_no_op(self):
        db.open_db(self.path).close()
        conn = db.open_db(self.path)
        self.addCleanup(conn.close)
        self.assertEqual(db.schema_version(), db.migrate(conn))

    def test_default_path_follows_skm_home(self):
        self.assertEqual(self.tmp / "state" / "gui" / "gui.db", db.default_path({"SKM_HOME": str(self.tmp)}))

    def test_newer_database_is_refused_untouched(self):
        raw = sqlite3.connect(self.path.parent.mkdir(parents=True) or str(self.path))
        raw.execute(f"PRAGMA user_version = {db.schema_version() + 1}")
        raw.close()
        before = self.path.read_bytes()
        with self.assertRaises(GuiError) as caught:
            db.open_db(self.path)
        self.assertEqual("STATE_INCOMPATIBLE", caught.exception.code)
        self.assertEqual(before, self.path.read_bytes())
        self.assertFalse(Path(str(self.path) + "-wal").exists())

    def test_not_a_database_is_refused(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_bytes(b"not sqlite at all" * 100)
        with self.assertRaises(GuiError) as caught:
            db.open_db(self.path)
        self.assertEqual("STATE_INCOMPATIBLE", caught.exception.code)

    def test_later_migration_applies_on_top_and_failure_rolls_back(self):
        db.open_db(self.path).close()
        known = db.schema_version()
        extra = db.MIGRATIONS + [(known + 1, "CREATE TABLE extra (id INTEGER PRIMARY KEY);")]
        conn = db.open_db(self.path, migrations=extra)
        self.assertEqual(known + 1, conn.execute("PRAGMA user_version").fetchone()[0])
        conn.close()
        broken = extra + [(known + 2, "CREATE TABLE three (id INTEGER);\nCREATE TABLE three (id INTEGER);")]
        with self.assertRaises(sqlite3.OperationalError):
            db.open_db(self.path, migrations=broken)
        conn = db.open_db(self.path, migrations=extra)
        self.addCleanup(conn.close)
        self.assertEqual(known + 1, conn.execute("PRAGMA user_version").fetchone()[0])
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertNotIn("three", tables)

    def test_numbering_must_be_contiguous(self):
        conn = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(conn.close)
        with self.assertRaises(ValueError):
            db.migrate(conn, [(1, "SELECT 1;"), (3, "SELECT 1;")])

    def test_audit_row(self):
        conn = db.open_db(self.path)
        self.addCleanup(conn.close)
        row_id = db.audit(conn, actor="gui", action="x.y", target="t", decision="allowed", details={"b": 2, "a": 1},
                          correlation_id="c1")
        row = conn.execute("SELECT * FROM audit WHERE id = ?", (row_id,)).fetchone()
        self.assertEqual(('{"a": 1, "b": 2}', "c1"), (row["details_json"], row["correlation_id"]))
        self.assertRegex(row["at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")


if __name__ == "__main__":
    unittest.main()
