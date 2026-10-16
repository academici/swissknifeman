"""Capacity gates: expiry, the later reset wins, concurrent writers lose nothing, the CLI."""
import contextlib
import io
import json
import multiprocessing
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

from orch.conductor import cli, gates  # noqa: E402

NOW = 1_800_000_000


def _write_one(args):
    file, provider, until = args
    gates.set_gate(provider, until=until, code="PROVIDER_QUOTA", run_id=provider, now=NOW, file=Path(file))


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "orch" / "provider-gates.json"

    def test_a_missing_or_damaged_file_means_no_gates(self):
        self.assertIsNone(gates.blocked("claude-code", NOW, file=self.file))
        self.file.parent.mkdir(parents=True)
        for text in ("not json", "[]", '{"schema": "x", "gates": {}}', '{"schema": "provider-gates/v1", "gates": []}'):
            self.file.write_text(text, encoding="utf-8")
            with self.subTest(text=text):
                self.assertEqual(gates.active(NOW, file=self.file), {})

    def test_set_then_blocked_until_the_reset_and_not_after(self):
        entry = gates.set_gate("claude-code", until=NOW + 600, code="PROVIDER_QUOTA", run_id="r1", now=NOW, file=self.file)
        self.assertEqual(entry["class"], "quota")
        self.assertEqual((entry["set_by"], entry["code"]), ("r1", "PROVIDER_QUOTA"))
        self.assertEqual(gates.blocked("claude-code", NOW + 599, file=self.file)["until"], entry["until"])
        self.assertIsNone(gates.blocked("claude-code", NOW + 600, file=self.file))
        self.assertIsNone(gates.blocked("codex", NOW, file=self.file))

    def test_file_format(self):
        gates.set_gate("codex", until=NOW + 60, code="PROVIDER_QUOTA", run_id="r1", now=NOW, file=self.file)
        doc = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(doc["schema"], "provider-gates/v1")
        self.assertEqual(set(doc["gates"]["codex"]), {"until", "class", "code", "set_by", "set_at"})
        self.assertRegex(doc["gates"]["codex"]["until"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_the_later_reset_wins_in_either_order(self):
        for first, second in ((600, 1200), (1200, 600)):
            with self.subTest(first=first, second=second):
                gates.clear(file=self.file)
                gates.set_gate("codex", until=NOW + first, code="A", run_id="r1", now=NOW, file=self.file)
                kept = gates.set_gate("codex", until=NOW + second, code="B", run_id="r2", now=NOW, file=self.file)
                self.assertEqual(gates.blocked("codex", NOW, file=self.file), kept)
                self.assertEqual(kept["set_by"], "r2" if second > first else "r1")

    def test_a_reset_in_the_past_sets_nothing(self):
        self.assertIsNone(gates.set_gate("codex", until=NOW, code="A", run_id="r", now=NOW, file=self.file))
        self.assertEqual(gates.active(NOW, file=self.file), {})

    def test_the_next_write_drops_expired_entries(self):
        gates.set_gate("codex", until=NOW + 10, code="A", run_id="r1", now=NOW, file=self.file)
        gates.set_gate("claude-code", until=NOW + 1000, code="B", run_id="r2", now=NOW + 100, file=self.file)
        self.assertEqual(set(json.loads(self.file.read_text(encoding="utf-8"))["gates"]), {"claude-code"})

    def test_an_invalid_entry_is_ignored_not_fatal(self):
        self.file.parent.mkdir(parents=True)
        doc = {"schema": "provider-gates/v1", "gates": {"codex": {"until": "soon"}, "Bad Name": {"until": "2099-01-01T00:00:00Z"},
                                                        "grok": {"until": "2099-01-01T00:00:00Z"}}}
        self.file.write_text(json.dumps(doc), encoding="utf-8")
        self.assertEqual(set(gates.active(NOW, file=self.file)), {"grok"})

    def test_a_sub_second_reset_never_opens_early(self):
        # 1800000000.7 + 0.2: the gate is stored rounded up, so it still holds at `now`
        now = NOW + 0.7
        entry = gates.set_gate("codex", until=now + 0.2, code="A", run_id="r", now=now, file=self.file)
        self.assertEqual(entry["until"], gates._stamp(NOW + 1))
        self.assertIsNotNone(gates.blocked("codex", now, file=self.file))
        self.assertIsNone(gates.blocked("codex", NOW + 1, file=self.file))

    def test_a_lock_file_removed_while_held_does_not_let_two_writers_overlap(self):
        # review finding: flock covers one inode; a writer on a replaced lock file must wait for the new one
        gates.set_gate("codex", until=NOW + 100, code="A", run_id="r", now=NOW, file=self.file)
        lock = self.file.with_name(gates.LOCK_FILE)
        first = gates._Locked(self.file)
        first.__enter__()
        lock.unlink()  # a third party removed the lock file under the holder
        second_inode = None
        old, gates.LOCK_TIMEOUT_S = gates.LOCK_TIMEOUT_S, 0.3
        self.addCleanup(setattr, gates, "LOCK_TIMEOUT_S", old)
        try:
            # a new writer creates a new lock file and gets it; it is the only holder of that one
            with gates._Locked(self.file) as second:
                second_inode = os.fstat(second.fd).st_ino
                self.assertNotEqual(second_inode, os.fstat(first.fd).st_ino)
                # a third writer must now wait on the file that is at the path, not slip through the dead inode
                with self.assertRaises(gates.GateError):
                    gates.set_gate("grok", until=NOW + 100, code="A", run_id="r", now=NOW, file=self.file)
        finally:
            first.__exit__()

    def test_a_forked_copy_of_the_lock_descriptor_does_not_keep_the_lock(self):
        old, gates.LOCK_TIMEOUT_S = gates.LOCK_TIMEOUT_S, 0.5
        self.addCleanup(setattr, gates, "LOCK_TIMEOUT_S", old)
        child = None
        try:
            with gates._Locked(self.file):
                child = os.fork()
                if child == 0:
                    import time
                    time.sleep(20)
                    os._exit(0)
            gates.set_gate("codex", until=NOW + 30, code="A", run_id="r", now=NOW, file=self.file)
        finally:
            if child:
                os.kill(child, 9)
                os.waitpid(child, 0)
        self.assertIsNotNone(gates.blocked("codex", NOW, file=self.file))

    def test_a_fifo_or_a_symlink_or_a_directory_is_no_gates_and_never_hangs(self):
        self.file.parent.mkdir(parents=True)
        os.mkfifo(self.file)
        self.assertEqual(gates.active(NOW, file=self.file), {})
        self.file.unlink()
        real = self.file.with_name("real.json")
        real.write_text(json.dumps({"schema": "provider-gates/v1", "gates": {"codex": {"until": "2099-01-01T00:00:00Z"}}}),
                        encoding="utf-8")
        self.file.symlink_to(real)
        self.assertEqual(gates.active(NOW, file=self.file), {})
        self.file.unlink()
        self.file.mkdir()
        self.assertEqual(gates.active(NOW, file=self.file), {})

    def test_a_write_through_a_symlinked_or_hard_linked_file_is_refused_not_followed(self):
        self.file.parent.mkdir(parents=True)
        real = self.file.with_name("real.json")
        real.write_text("keep", encoding="utf-8")
        self.file.symlink_to(real)
        with self.assertRaises(gates.GateError) as caught:
            gates.set_gate("codex", until=NOW + 100, code="A", run_id="r", now=NOW, file=self.file)
        self.assertEqual(caught.exception.code, "GATES_UNSAFE")
        self.assertEqual(real.read_text(encoding="utf-8"), "keep")
        self.file.unlink()
        os.link(real, self.file)
        with self.assertRaises(gates.GateError):
            gates.set_gate("codex", until=NOW + 100, code="A", run_id="r", now=NOW, file=self.file)

    def test_a_planted_temp_symlink_is_not_followed(self):
        self.file.parent.mkdir(parents=True)
        victim = self.file.with_name("victim.txt")
        victim.write_text("SECRET", encoding="utf-8")
        self.file.with_name(self.file.name + ".tmp").symlink_to(victim)
        gates.set_gate("codex", until=NOW + 100, code="A", run_id="r", now=NOW, file=self.file)
        self.assertEqual(victim.read_text(encoding="utf-8"), "SECRET")
        self.assertIsNotNone(gates.blocked("codex", NOW, file=self.file))

    def test_an_entry_with_only_until_is_listed_with_placeholders(self):
        self.file.parent.mkdir(parents=True)
        self.file.write_text(json.dumps({"schema": "provider-gates/v1", "gates": {"codex": {"until": "2099-01-01T00:00:00Z"}}}),
                             encoding="utf-8")
        entry = gates.blocked("codex", NOW, file=self.file)
        self.assertEqual((entry["class"], entry["code"], entry["set_by"]), ("unknown", "unknown", "unknown"))

    def test_provider_must_be_an_id(self):
        with self.assertRaises(ValueError):
            gates.set_gate("../x", until=NOW + 1, code="A", run_id="r", now=NOW, file=self.file)

    def test_clear_one_or_all(self):
        for name in ("codex", "claude-code"):
            gates.set_gate(name, until=NOW + 600, code="A", run_id="r", now=NOW, file=self.file)
        self.assertEqual(gates.clear("codex", file=self.file), ["codex"])
        self.assertEqual(gates.clear("codex", file=self.file), [])
        self.assertEqual(gates.clear(file=self.file), ["claude-code"])
        self.assertEqual(gates.active(NOW, file=self.file), {})

    def test_concurrent_writers_lose_no_entry(self):
        names = [f"p{index}" for index in range(12)]
        jobs = [(str(self.file), name, NOW + 600 + index) for index, name in enumerate(names)]
        with multiprocessing.get_context("fork").Pool(6) as pool:
            pool.map(_write_one, jobs * 3)  # every provider is written three times, interleaved
        self.assertEqual(set(gates.active(NOW, file=self.file)), set(names))

    def test_concurrent_writers_of_one_provider_keep_the_latest_reset(self):
        jobs = [(str(self.file), "codex", NOW + 100 + index) for index in range(40)]
        with multiprocessing.get_context("fork").Pool(6) as pool:
            pool.map(_write_one, jobs)
        self.assertEqual(gates.blocked("codex", NOW, file=self.file)["until"], gates._stamp(NOW + 139))

    def test_a_reader_never_sees_a_torn_file_while_writers_run(self):
        jobs = [(str(self.file), f"p{index % 5}", NOW + 600 + index) for index in range(60)]
        with multiprocessing.get_context("fork").Pool(4) as pool:
            pending = pool.map_async(_write_one, jobs)
            while not pending.ready():
                if self.file.exists():
                    json.loads(self.file.read_text(encoding="utf-8"))
            pending.get()

    def test_a_lock_held_too_long_is_reported(self):
        old = gates.LOCK_TIMEOUT_S
        gates.LOCK_TIMEOUT_S = 0.2
        self.addCleanup(setattr, gates, "LOCK_TIMEOUT_S", old)
        with gates._Locked(self.file):
            with self.assertRaises(gates.GateError) as caught:
                gates.set_gate("codex", until=NOW + 1, code="A", run_id="r", now=NOW, file=self.file)
        self.assertEqual(caught.exception.code, "GATES_LOCKED")


class GatesCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.old = {"SKM_HOME": os.environ.get("SKM_HOME")}
        os.environ["SKM_HOME"] = self.tmp.name
        self.addCleanup(self._restore)

    def _restore(self):
        for key, value in self.old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(["gates", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_machine_state_is_under_skm_home_and_empty_at_first(self):
        self.assertEqual(self.run_cli(), (0, "no gates\n", ""))
        code, out, _ = self.run_cli("--json")
        self.assertEqual((code, json.loads(out)["gates"]), (0, []))
        self.assertTrue(json.loads(out)["path"].startswith(self.tmp.name))

    def test_a_damaged_entry_and_an_unsafe_file_give_messages_not_tracebacks(self):
        file = gates.path()
        file.parent.mkdir(parents=True)
        file.write_text(json.dumps({"schema": "provider-gates/v1", "gates": {"codex": {"until": "2099-01-01T00:00:00Z"}}}),
                        encoding="utf-8")
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("codex: until 2099-01-01T00:00:00Z", out)
        real = file.with_name("real.json")
        file.rename(real)
        file.symlink_to(real)
        self.assertEqual(self.run_cli()[0], 0)  # an untrusted file is no gates
        file.unlink()
        os.link(real, file)
        code, _, err = self.run_cli("--clear")
        self.assertEqual(code, 1)
        self.assertIn("GATES_UNSAFE", err)

    def test_list_and_clear(self):
        import time
        now = time.time()
        gates.set_gate("claude-code", until=now + 3600, code="PROVIDER_QUOTA", run_id="run-1", now=now)
        gates.set_gate("codex", until=now + 3600, code="PROVIDER_QUOTA", run_id="run-2", now=now)
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("claude-code: until ", out)
        self.assertIn("set by run-2", out)
        rows = json.loads(self.run_cli("--json")[1])["gates"]
        self.assertEqual([row["provider"] for row in rows], ["claude-code", "codex"])
        self.assertEqual(self.run_cli("--clear", "codex")[:2], (0, "cleared: codex\n"))
        self.assertEqual(self.run_cli("--clear", "codex")[0], 1)
        self.assertIn("GATE_UNKNOWN", self.run_cli("--clear", "codex")[2])
        self.assertEqual(self.run_cli("--clear")[:2], (0, "cleared: claude-code\n"))
        self.assertEqual(self.run_cli("--clear")[:2], (0, "no gates\n"))


if __name__ == "__main__":
    unittest.main()
