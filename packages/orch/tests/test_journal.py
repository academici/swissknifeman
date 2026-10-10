from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import stat
import tempfile
from unittest import mock
import unittest

from orch import journal
from orch.port import PortError

RUN = "run-journal-1"


def event(seq, kind="output", **extra):
    doc = {
        "$schema": "urn:swissknifeman:orch:exec:run-event:v1", "contract_version": "exec/v1",
        "run_id": RUN, "stage_id": "primary", "attempt": 1, "seq": seq,
        "ts": f"2026-10-05T17:00:{seq % 60:02d}Z", "kind": kind, "event_id": f"evt-j-{seq}",
    }
    doc.update(extra)
    return doc


def _writer(directory, start):
    for seq in range(start, start + 25):
        journal.append_event(directory, event(seq))


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / "skm"
        self.env = {"SKM_HOME": str(self.home)}
        self.directory = journal.run_dir(RUN, env=self.env)

    def seqs(self, after=None):
        return [doc["seq"] for doc in journal.read_events(self.directory, after)]

    def test_run_dir_is_under_the_state_of_the_machine_or_the_project(self):
        self.assertEqual(self.directory, self.home / "state" / "orch" / "runs" / RUN)
        project = Path(self.tmp.name) / "project"
        self.assertEqual(journal.run_dir(RUN, project=project),
                         project / ".swissknifeman" / "state" / "orch" / "runs" / RUN)
        self.assertFalse(self.directory.exists())  # nothing is created by resolving

    def test_run_id_cannot_leave_the_runs_directory(self):
        for run_id in ("", "../x", "a/b", "..", ".hidden", "a" * 161):
            with self.subTest(run_id=run_id), self.assertRaises(PortError) as caught:
                journal.run_dir(run_id, env=self.env)
            self.assertEqual(caught.exception.code, "INPUT_INVALID")

    def test_after_seq_returns_exactly_the_later_events(self):
        for seq in (1, 2, 4, 7):
            self.assertTrue(journal.append_event(self.directory, event(seq)))
        self.assertEqual(self.seqs(), [1, 2, 4, 7])
        self.assertEqual(self.seqs(0), [1, 2, 4, 7])
        self.assertEqual(self.seqs(2), [4, 7])
        self.assertEqual(self.seqs(3), [4, 7])
        self.assertEqual(self.seqs(7), [])
        self.assertEqual(self.seqs(2), self.seqs(2))  # repeatable

    def test_missing_journal_is_empty(self):
        self.assertEqual(self.seqs(), [])

    def test_identical_append_is_not_written_twice(self):
        self.assertTrue(journal.append_event(self.directory, event(1)))
        before = (self.directory / "events.jsonl").read_bytes()
        self.assertFalse(journal.append_event(self.directory, event(1)))
        self.assertEqual((self.directory / "events.jsonl").read_bytes(), before)
        legacy = dict(event(2))
        del legacy["event_id"]  # keyed by (run_id, seq) when there is no event_id
        self.assertTrue(journal.append_event(self.directory, legacy))
        self.assertFalse(journal.append_event(self.directory, dict(legacy)))
        self.assertEqual(self.seqs(), [1, 2])

    def test_same_event_id_with_other_content_is_a_conflict(self):
        journal.append_event(self.directory, event(1))
        with self.assertRaises(PortError) as caught:
            journal.append_event(self.directory, event(2, event_id="evt-j-1"))
        self.assertEqual(caught.exception.code, "EVENT_CONFLICT")
        self.assertEqual(self.seqs(), [1])

    def test_same_seq_with_other_content_is_seq_order(self):
        journal.append_event(self.directory, event(1))
        with self.assertRaises(PortError) as caught:
            journal.append_event(self.directory, event(1, summary="other", event_id="evt-other"))
        self.assertEqual(caught.exception.code, "SEQ_ORDER")
        self.assertEqual(self.seqs(), [1])

    def test_invalid_or_foreign_event_is_refused_before_writing(self):
        for doc, code in ((event(1, kind="finished"), "INPUT_INVALID"),
                          (dict(event(1), run_id="other-run"), "RUN_UNKNOWN")):
            with self.subTest(code=code), self.assertRaises(PortError) as caught:
                journal.append_event(self.directory, doc)
            self.assertEqual(caught.exception.code, code)
        self.assertFalse(self.directory.exists())

    def test_torn_last_line_is_skipped_and_the_next_event_starts_on_a_new_line(self):
        journal.append_event(self.directory, event(1))
        path = self.directory / "events.jsonl"
        with open(path, "ab") as handle:
            handle.write(b'{"seq": 2, "kind": "outp')
        self.assertEqual(self.seqs(), [1])
        self.assertTrue(journal.append_event(self.directory, event(3)))
        self.assertEqual(self.seqs(), [1, 3])
        self.assertEqual(self.seqs(1), [3])

    def test_crash_after_the_body_before_the_newline_does_not_duplicate_the_event(self):
        journal.append_event(self.directory, event(1))
        real = os.write

        def crash(fd, data):
            body = bytes(data)
            if body.endswith(b"\n") and b'"seq":2' in body:
                real(fd, body[:-1])
                raise OSError("simulated crash")
            return real(fd, data)

        with mock.patch("os.write", crash), self.assertRaises(OSError):
            journal.append_event(self.directory, event(2))
        self.assertEqual(self.seqs(), [1])  # the body without its newline is not yet an event
        self.assertFalse(journal.append_event(self.directory, event(2)))  # the retry finds it, no second copy
        self.assertEqual(self.seqs(), [1, 2])
        self.assertTrue(journal.append_event(self.directory, event(3)))
        self.assertEqual(self.seqs(), [1, 2, 3])

    def test_reader_ignores_an_unfinished_line_while_a_write_is_in_progress(self):
        journal.append_event(self.directory, event(1))
        with open(self.directory / "events.jsonl", "ab") as handle:
            handle.write(json.dumps(event(2)).encode())  # complete JSON, newline not yet written
        self.assertEqual(self.seqs(), [1])

    def test_two_writers_never_lose_or_duplicate_events(self):
        self.directory.mkdir(parents=True)
        context = multiprocessing.get_context("fork")
        workers = [context.Process(target=_writer, args=(self.directory, start)) for start in (100, 200, 300)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(60)
            self.assertEqual(worker.exitcode, 0)
        seqs = self.seqs()
        self.assertEqual(sorted(seqs), sorted(list(range(100, 125)) + list(range(200, 225)) + list(range(300, 325))))
        lines = (self.directory / "events.jsonl").read_bytes().split(b"\n")
        self.assertEqual(lines[-1], b"")
        for line in lines[:-1]:
            json.loads(line)  # no interleaved bytes

    def test_files_stay_under_the_run_directory_with_private_modes(self):
        journal.append_event(self.directory, event(1))
        journal.write_doc(self.directory, "run.json", {"run_id": RUN})
        names = sorted(path.name for path in self.directory.iterdir())
        self.assertEqual(names, ["events.jsonl", "events.lock", "run.json"])
        self.assertEqual(stat.S_IMODE(os.stat(self.directory).st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(os.stat(self.directory / "events.jsonl").st_mode), 0o600)
        self.assertEqual([p for p in self.home.rglob("*") if RUN not in p.as_posix() and p.is_file()], [])

    def test_documents_roundtrip_atomically(self):
        self.assertIsNone(journal.read_doc(self.directory, "run.json"))
        journal.write_doc(self.directory, "run.json", {"status": "running"})
        journal.write_doc(self.directory, "run.json", {"status": "done"})
        journal.write_doc(self.directory, "receipts/1.json", {"n": 1})
        self.assertEqual(journal.read_doc(self.directory, "run.json"), {"status": "done"})
        self.assertEqual(journal.read_doc(self.directory, "receipts/1.json"), {"n": 1})
        self.assertEqual([p.name for p in self.directory.glob("*.tmp")], [])
        self.assertEqual([p.name for p in (self.directory / "receipts").iterdir()], ["1.json"])

    def test_failed_write_keeps_the_old_document(self):
        journal.write_doc(self.directory, "run.json", {"status": "running"})
        with self.assertRaises(TypeError):
            journal.write_doc(self.directory, "run.json", {"bad": object()})
        self.assertEqual(journal.read_doc(self.directory, "run.json"), {"status": "running"})
        self.assertEqual([p.name for p in self.directory.iterdir() if p.name.endswith(".tmp")], [])

    def test_only_known_document_names_are_written(self):
        for name in ("../escape.json", "events.jsonl", "receipts/../x.json", "/etc/passwd", "receipts/a/b.json", "x.json"):
            with self.subTest(name=name), self.assertRaises(PortError) as caught:
                journal.write_doc(self.directory, name, {})
            self.assertEqual(caught.exception.code, "INPUT_INVALID")


if __name__ == "__main__":
    unittest.main()
