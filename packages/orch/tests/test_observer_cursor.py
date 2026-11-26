"""``ProgressCursor``: the observer reads only the lines the journal gained, never half a line, and starts again when the
journal was cut or replaced; ``follow`` prints through it what the whole-journal reader would have printed."""
from __future__ import annotations

import importlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from orch.conductor import progress
from orch.conductor.observer import reader
from orch.conductor.observer.follow import follow

follow_mod = importlib.import_module("orch.conductor.observer.follow")  # the module: ``observer.follow`` is its function


def line(event: str, **fields) -> dict:
    return {"ts": "2026-10-20T10:00:00Z", "run": "cnd-cursor", "event": event, **fields}


def raw(doc: dict) -> bytes:
    return (json.dumps(doc, sort_keys=True) + "\n").encode("utf-8")


class CursorCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.path = self.directory / progress.PROGRESS_FILE
        self.cursor = reader.ProgressCursor(self.directory)

    def append(self, data: bytes) -> None:
        with self.path.open("ab") as handle:
            handle.write(data)

    def write(self, data: bytes) -> None:
        self.path.write_bytes(data)


class ReadNewTests(CursorCase):
    def test_a_missing_journal_is_no_lines(self):
        self.assertEqual([], self.cursor.read_new())

    def test_only_the_new_lines_come_back(self):  # (a)
        self.append(raw(line("run.start")) + raw(line("item.start", item="W1")))
        self.assertEqual(["run.start", "item.start"], [doc["event"] for doc in self.cursor.read_new()])
        self.assertEqual([], self.cursor.read_new())
        self.append(raw(line("item.end", item="W1", outcome="done")))
        self.assertEqual(["item.end"], [doc["event"] for doc in self.cursor.read_new()])

    def test_the_next_call_reads_from_the_offset_not_from_the_start(self):
        self.append(raw(line("run.start")) * 50)
        self.cursor.read_new()
        self.append(raw(line("run.end", outcome="finished")))
        with mock.patch.object(reader.json, "loads", wraps=json.loads) as parsed:
            found = self.cursor.read_new()
        self.assertEqual(["run.end"], [doc["event"] for doc in found])
        self.assertEqual(1, parsed.call_count)  # the 50 lines read before are not parsed again
        self.assertEqual(self.path.stat().st_size, self.cursor.offset)

    def test_a_line_without_its_newline_waits_for_it(self):  # (b)
        whole = raw(line("run.start"))
        self.append(whole[:-1])
        self.assertEqual([], self.cursor.read_new())
        self.assertEqual(whole[:-1], self.cursor.tail)
        self.assertEqual(0, self.cursor.discarded)
        self.append(b"\n")
        self.assertEqual(["run.start"], [doc["event"] for doc in self.cursor.read_new()])
        self.assertEqual(b"", self.cursor.tail)

    def test_a_line_that_arrives_in_pieces_is_read_once_when_it_is_whole(self):
        whole = raw(line("item.end", item="W1", outcome="done"))
        found = []
        for start in range(0, len(whole), 7):
            self.append(whole[start:start + 7])
            found += self.cursor.read_new()
        self.assertEqual(["item.end"], [doc["event"] for doc in found])
        self.assertEqual(0, self.cursor.discarded)

    def test_a_torn_tail_that_the_writer_ends_with_a_newline_is_one_skipped_line(self):
        self.append(raw(line("run.start")) + b"garbage-no-newline")
        self.assertEqual(["run.start"], [doc["event"] for doc in self.cursor.read_new()])
        progress.Progress("cnd-cursor", self.directory, "quiet", clock=lambda: "2026-10-20T10:00:01Z").emit("run.resume")
        found = self.cursor.read_new()
        self.assertEqual(["run.resume"], [doc["event"] for doc in found])
        self.assertEqual(1, self.cursor.discarded)

    def test_a_complete_line_that_is_not_a_progress_line_is_skipped_and_counted(self):  # (d)
        self.append(raw(line("run.start")) + b"not json\n" + b"\n" + b"[1]\n" + json.dumps({"event": "x"}).encode() + b"\n"
                    + raw(line("item.end", item="W1", outcome="done")))
        self.assertEqual(["run.start", "item.end"], [doc["event"] for doc in self.cursor.read_new()])
        self.assertEqual(3, self.cursor.discarded)  # the blank line is not a lost line

    def test_a_cut_journal_is_read_from_the_start(self):  # (c)
        self.append(raw(line("run.start")) + raw(line("item.start", item="W1")) + raw(line("item.end", item="W1", outcome="done")))
        self.assertEqual(3, len(self.cursor.read_new()))
        self.write(raw(line("run.start")))
        found = self.cursor.read_new()
        self.assertEqual(["run.start"], [doc["event"] for doc in found])
        self.assertTrue(self.cursor.restarted)
        self.assertEqual([], self.cursor.read_new())
        self.assertFalse(self.cursor.restarted)

    def test_a_journal_replaced_by_a_longer_file_is_read_from_the_start(self):
        self.append(raw(line("run.start", run="cnd-first")))
        self.cursor.read_new()
        replacement = self.directory / "other"
        replacement.write_bytes(raw(line("run.start", run="cnd-second")) + raw(line("run.end", outcome="finished")))
        os.replace(replacement, self.path)
        found = self.cursor.read_new()
        self.assertEqual(["run.start", "run.end"], [doc["event"] for doc in found])
        self.assertTrue(self.cursor.restarted)

    def test_a_journal_rewritten_in_place_with_other_content_is_read_from_the_start(self):
        self.append(raw(line("run.start", run="cnd-first")))
        self.cursor.read_new()
        self.write(raw(line("run.start", run="cnd-other")) + raw(line("run.end", outcome="finished")))
        self.assertEqual(["run.start", "run.end"], [doc["event"] for doc in self.cursor.read_new()])

    def test_a_vanished_journal_starts_again_when_it_comes_back(self):
        self.append(raw(line("run.start")))
        self.cursor.read_new()
        self.path.unlink()
        self.assertEqual([], self.cursor.read_new())
        self.append(raw(line("run.start")))
        self.assertEqual(["run.start"], [doc["event"] for doc in self.cursor.read_new()])

    def test_a_second_cursor_over_the_same_journal_starts_at_the_beginning(self):  # repeated start
        self.append(raw(line("run.start")) + raw(line("run.end", outcome="finished")))
        self.assertEqual(2, len(self.cursor.read_new()))
        again = reader.ProgressCursor(self.directory)
        self.assertEqual(2, len(again.read_new()))

    def test_the_cursor_matches_the_whole_journal_reader(self):
        lines = [line("run.start"), line("item.start", item="W1"), line("stage.end", item="W1", stage="checks.1",
                                                                      verdict="red V1"), line("run.end", outcome="stopped")]
        self.append(b"".join(raw(doc) for doc in lines) + b"junk\n")
        whole, discarded = progress.read_lines_counted(self.directory)
        self.assertEqual(whole, self.cursor.read_new())
        self.assertEqual(discarded, self.cursor.discarded)


class FollowThroughTheCursorTests(CursorCase):
    def old_follow(self, stream) -> int:
        """The follow of before P5.5: the whole journal read again on every poll."""
        seen = 0
        while True:
            lines = progress.read_lines(self.directory)
            for entry in lines[seen:]:
                event = entry.get("event")
                if (event in ("item.end", "run.end", "run.resume") or entry.get("reason_code")
                        or (event == "info" and "repeating" in entry.get("message", ""))
                        or (event == "stage.end" and str(entry.get("verdict", "")).startswith("red"))):
                    print("observer: " + progress.text_line(entry), file=stream, flush=True)
            if next((entry.get("event") for entry in reversed(lines)
                     if entry.get("event") in ("run.start", "run.resume", "run.end")), None) == "run.end":
                return 0
            seen = len(lines)
            return 3

    def test_follow_prints_what_the_whole_journal_reader_printed(self):  # (e)
        journal = [line("run.start"), line("item.start", item="W1"), line("info", reason_code="STAGE_SLOW", message="slow"),
                   line("stage.end", item="W1", stage="checks.1", verdict="red V1"), line("info", message="repeating it"),
                   line("item.end", item="W1", outcome="done"), line("run.end", outcome="finished")]
        self.write(b"".join(raw(doc) for doc in journal))
        before, after = io.StringIO(), io.StringIO()
        self.assertEqual(0, self.old_follow(before))
        self.assertEqual(0, follow(self.directory, stream=after, poll_s=0.01, alive=lambda: True))
        self.assertEqual(before.getvalue(), after.getvalue())
        self.assertEqual(5, len(after.getvalue().splitlines()))

    def test_follow_reads_the_lines_of_later_polls_once(self):
        self.write(raw(line("run.start")) + raw(line("item.end", item="W1", outcome="done")))
        out = io.StringIO()

        def finish(_seconds):
            self.append(raw(line("item.end", item="W2", outcome="done")) + raw(line("run.end", outcome="finished")))
        with mock.patch.object(follow_mod.time, "sleep", side_effect=finish) as sleep:
            self.assertEqual(0, follow(self.directory, stream=out, poll_s=0.01, alive=lambda: True))
        self.assertEqual(1, sleep.call_count)
        self.assertEqual(["W1", "W2", "-"], [text.split("  ")[1] for text in out.getvalue().splitlines()])

    def test_follow_does_not_lose_a_line_that_is_finished_between_polls(self):
        whole = raw(line("item.end", item="W1", outcome="done"))
        self.write(raw(line("run.start")) + whole[:20])
        out = io.StringIO()

        def finish(_seconds):
            self.append(whole[20:] + raw(line("run.end", outcome="finished")))
        with mock.patch.object(follow_mod.time, "sleep", side_effect=finish):
            self.assertEqual(0, follow(self.directory, stream=out, poll_s=0.01, alive=lambda: True))
        self.assertEqual(2, len(out.getvalue().splitlines()))

    def test_follow_forgets_the_lifecycle_of_a_journal_that_was_cut(self):
        self.write(raw(line("run.start")) + raw(line("run.end", outcome="stopped")) + raw(line("run.resume")))
        out = io.StringIO()
        polls = []

        def cut(_seconds):
            polls.append(1)
            self.write(raw(line("run.start", run="cnd-new")))
        with mock.patch.object(follow_mod.time, "sleep", side_effect=cut):
            self.assertEqual(3, follow(self.directory, stream=out, poll_s=0.01, alive=lambda: False))
        self.assertIn("run cnd-new has no live conductor", out.getvalue())


if __name__ == "__main__":
    unittest.main()
