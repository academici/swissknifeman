"""aicore.ext.events: the envelope, build_event, emit (best effort for the source) and read_events."""
import datetime
import json
import multiprocessing
import os
import io
import traceback
import unittest
import uuid
from contextlib import redirect_stderr
from unittest import mock

from aicore.config import Secret
from aicore.ext import delivery, events, journal
from aicore.ext.errors import CODES, ExtError, reset_warnings

from tests.ext.support import TempCase

SENTINEL = "s3cr3t-" + uuid.uuid4().hex


def _emitter(project, label, count):
    for index in range(count):
        events.emit("demo.thing.happened", {"w": label, "i": index}, source="demo", project=project)


class TestEnvelope(unittest.TestCase):
    def test_minimal_event(self):
        event = events.build_event("demo.thing.happened", source="demo")
        doc = event.to_json()
        self.assertEqual(list(doc), ["specversion", "id", "source", "type", "time"])
        self.assertEqual((doc["specversion"], doc["source"]), ("1.0", "urn:swissknifeman:module:demo"))
        self.assertRegex(doc["id"], r"^[0-9a-f]{32}$")
        self.assertRegex(doc["time"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$")
        self.assertEqual(event.module, "demo")
        self.assertIsNone(event.offset)

    def test_full_event_keeps_the_table_order(self):
        when = datetime.datetime(2026, 10, 9, 12, 0, 0, 123999, tzinfo=datetime.timezone.utc)
        event = events.build_event(
            "demo.thing.happened", {"b": [1, {"c": None}], "a": True}, source="demo", subject="PLAN/P1",
            dataschema="urn:demo:thing:v1", traceparent="00-" + "a" * 32 + "-" + "b" * 16 + "-01",
            causationid="c" * 32, correlationid="run-7", now=when, id="d" * 32)
        doc = event.to_json()
        self.assertEqual(list(doc), ["specversion", "id", "source", "type", "time", "subject", "datacontenttype",
                                     "dataschema", "data", "traceparent", "causationid", "correlationid"])
        self.assertEqual(doc["time"], "2026-10-09T12:00:00.123Z")
        self.assertEqual(doc["datacontenttype"], "application/json")
        self.assertEqual(doc["data"], {"b": [1, {"c": None}], "a": True})

    def test_aware_time_is_converted_to_utc(self):
        zone = datetime.timezone(datetime.timedelta(hours=3))
        event = events.build_event("demo.thing.happened", source="demo",
                                   now=datetime.datetime(2026, 1, 1, 3, 0, 0, tzinfo=zone))
        self.assertEqual(event.time, "2026-01-01T00:00:00.000Z")

    def test_type_and_source_rules(self):
        for kwargs in ({"source": "Demo"}, {"source": ""}, {"source": "other"}):
            with self.assertRaises(ExtError) as caught:
                events.build_event("demo.thing.happened", **kwargs)
            self.assertEqual(caught.exception.code, "EVENT_INVALID", kwargs)
        for bad in ("demo.thing", "Demo.thing.happened", "demo.thing.Happened", "demo..happened", 5):
            with self.assertRaises(ExtError) as caught:
                events.build_event(bad, source="demo")
            self.assertEqual(caught.exception.code, "EVENT_INVALID", bad)

    def test_invalid_optional_fields(self):
        for kwargs in ({"traceparent": "zz"}, {"causationid": "x"}, {"dataschema": "http://x"},
                       {"correlationid": ""}, {"subject": ""}, {"id": "ABC"}):
            with self.assertRaises(ExtError) as caught:
                events.build_event("demo.thing.happened", source="demo", **kwargs)
            self.assertEqual(caught.exception.code, "EVENT_INVALID", kwargs)

    def test_data_must_be_a_plain_object(self):
        for bad in ([1], "text", 5, {"x": 1.5}, {"x": {1, 2}}, {1: "a"}, {"x": object()}):
            with self.assertRaises(ExtError) as caught:
                events.build_event("demo.thing.happened", bad, source="demo")
            self.assertEqual(caught.exception.code, "EVENT_INVALID", bad)

    def test_data_size_limit_is_exact(self):
        overhead = len(json.dumps({"k": ""}, separators=(",", ":")))
        fits = {"k": "x" * (events.MAX_DATA_BYTES - overhead)}
        self.assertEqual(len(json.dumps(fits, separators=(",", ":"))), events.MAX_DATA_BYTES)
        events.build_event("demo.thing.happened", fits, source="demo")
        with self.assertRaises(ExtError) as caught:
            events.build_event("demo.thing.happened", {"k": "x" * (events.MAX_DATA_BYTES - overhead + 1)},
                               source="demo")
        self.assertEqual(caught.exception.code, "EVENT_DATA_TOO_LARGE")
        self.assertIn("artifact-ref", caught.exception.message)
        self.assertEqual(events.MAX_DATA_BYTES, 65536)

    def test_multibyte_data_counts_bytes(self):
        text = "é" * 40000  # 2 bytes each in UTF-8: 80000 bytes
        with self.assertRaises(ExtError) as caught:
            events.build_event("demo.thing.happened", {"k": text}, source="demo")
        self.assertEqual(caught.exception.code, "EVENT_DATA_TOO_LARGE")

    def test_text_that_cannot_be_utf8_is_refused_not_crashed(self):
        for kwargs in ({"subject": "ok\ud800"}, {"correlationid": "run\udfff"}):
            with self.assertRaises(ExtError) as caught:
                events.build_event("demo.thing.happened", source="demo", **kwargs)
            self.assertEqual(caught.exception.code, "EVENT_INVALID", kwargs)
        with self.assertRaises(ExtError):
            events.build_event("demo.thing.happened", {"k": "bad\ud800"}, source="demo")

    def test_from_json_keeps_unknown_extensions(self):
        doc = events.build_event("demo.thing.happened", source="demo").to_json()
        doc["acmeflag"] = True
        event = events.Event.from_json(doc, offset=5)
        self.assertEqual((event.extensions, event.offset), ({"acmeflag": True}, 5))
        self.assertEqual(event.to_json(), doc)

    def test_codes_are_registered(self):
        for code in ("EVENT_INVALID", "EVENT_SECRET", "EVENT_DATA_TOO_LARGE", "JOURNAL_LOCKED", "CONFIG_INVALID"):
            self.assertIn(code, CODES)


class TestSecretsNeverReachEvents(unittest.TestCase):
    def test_secret_in_data_is_refused_without_the_value(self):
        secret = Secret("env://SKM_DEMO_TOKEN", lambda: SENTINEL)
        for data in ({"token": secret}, {"a": {"b": [1, {"c": secret}]}}, {"a": (secret,)}, {secret: 1}):
            with self.assertRaises(ExtError) as caught:
                events.build_event("demo.thing.happened", data, source="demo")
            error = caught.exception
            self.assertEqual(error.code, "EVENT_SECRET")
            text = str(error) + repr(error) + "".join(traceback.format_exception(type(error), error,
                                                                                 error.__traceback__))
            self.assertNotIn(SENTINEL, text)
            self.assertIn("reference", error.message)

    def test_secret_reference_string_is_ordinary_data(self):
        event = events.build_event("demo.thing.happened", {"token": "env://SKM_DEMO_TOKEN"}, source="demo")
        self.assertEqual(event.data, {"token": "env://SKM_DEMO_TOKEN"})

    def test_cyclic_data_is_refused_not_looped(self):
        data = {}
        data["self"] = data
        with self.assertRaises(ExtError) as caught:
            events.build_event("demo.thing.happened", data, source="demo")
        self.assertEqual(caught.exception.code, "EVENT_INVALID")


class TestEmit(TempCase):
    def test_emit_journals_and_returns_the_offset(self):
        first = events.emit("demo.thing.happened", {"n": 1}, source="demo", project=self.project, subject="A")
        second = events.emit("demo.thing.happened", None, source="demo", project=self.project)
        self.assertEqual((first.offset, second.offset > first.offset), (0, True))
        found, problems = events.read_events(self.project)
        self.assertEqual(problems, [])
        self.assertEqual([event.id for event in found], [first.id, second.id])
        self.assertEqual(found[0].data, {"n": 1})
        self.assertEqual(found[0].offset, 0)
        line = journal.journal_path(self.journal).read_bytes().splitlines()[0]
        self.assertEqual(json.loads(line), first.to_json())
        self.assertEqual(line, json.dumps(first.to_json(), sort_keys=True, separators=(",", ":"),
                                          ensure_ascii=False).encode())

    def test_machine_journal_without_project(self):
        event = events.emit("demo.thing.happened", source="demo", env=self.env)
        self.assertIsNotNone(event)
        self.assertTrue((self.tmp / "skm" / "state" / "events" / "events.jsonl").is_file())
        found, _ = events.read_events(None, env=self.env)
        self.assertEqual([item.id for item in found], [event.id])

    def test_delivery_argument_is_checked(self):
        started = []
        with mock.patch.object(delivery, "spawn_background", lambda *args, **kwargs: started.append(kwargs)):
            for mode in events.DELIVERY_MODES:
                self.assertIsNotNone(events.emit("demo.thing.happened", source="demo", project=self.project,
                                                 delivery=mode))
        self.assertEqual(len(started), 1)  # background starts a deliverer (not in this test), sync and off do not
        with self.assertRaises(ExtError):
            events.emit("demo.thing.happened", source="demo", project=self.project, delivery="later")
        with self.assertRaises(TypeError):
            events.emit("demo.thing.happened", source="demo", project=self.project, bogus=1)

    def test_caller_errors_raise_even_when_not_strict(self):
        with self.assertRaises(ExtError):
            events.emit("other.thing.happened", source="demo", project=self.project)
        with self.assertRaises(ExtError):
            events.emit("demo.thing.happened", {"k": "x" * 70000}, source="demo", project=self.project)
        self.assertEqual(journal.size(self.journal), 0)

    def test_unwritable_journal_warns_and_returns_none(self):
        if os.geteuid() == 0:
            self.skipTest("root ignores directory permissions")
        events.emit("demo.thing.happened", source="demo", project=self.project)
        path = journal.journal_path(self.journal)
        os.chmod(path, 0o400)
        self.addCleanup(os.chmod, path, 0o600)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            result = events.emit("demo.thing.happened", source="demo", project=self.project)
            again = events.emit("demo.thing.happened", source="demo", project=self.project)
        self.assertIsNone(result)
        self.assertIsNone(again)
        self.assertEqual(stderr.getvalue().count("JOURNAL_IO"), 1)  # one warning per process and code
        with self.assertRaises(ExtError) as caught:
            events.emit("demo.thing.happened", source="demo", project=self.project, strict=True)
        self.assertEqual(caught.exception.code, "JOURNAL_IO")

    def test_busy_lock_is_a_warning_not_an_error(self):
        import fcntl
        events.emit("demo.thing.happened", source="demo", project=self.project)
        fd = os.open(journal.lock_path(self.journal), os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX)
        real_append = journal.append
        journal.append = lambda jdir, line: real_append(jdir, line, lock_timeout_s=0.1)
        self.addCleanup(setattr, journal, "append", real_append)
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertIsNone(events.emit("demo.thing.happened", source="demo", project=self.project))
        self.assertIn("JOURNAL_LOCKED", stderr.getvalue())
        with self.assertRaises(ExtError) as caught:
            events.emit("demo.thing.happened", source="demo", project=self.project, strict=True)
        self.assertEqual(caught.exception.code, "JOURNAL_LOCKED")
        self.assertEqual(journal.LOCK_TIMEOUT_S, 10.0)

    def test_two_processes_emit_400_events(self):
        context = multiprocessing.get_context("fork")
        workers = [context.Process(target=_emitter, args=(str(self.project), label, 200)) for label in ("a", "b")]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(60)
            self.assertEqual(worker.exitcode, 0)
        found, problems = events.read_events(self.project)
        self.assertEqual(problems, [])
        self.assertEqual(len(found), 400)
        self.assertEqual(len({event.id for event in found}), 400)
        self.assertEqual(len({(event.data["w"], event.data["i"]) for event in found}), 400)


class TestReadEvents(TempCase):
    def fill(self):
        return [events.emit(kind, {"n": index}, source="demo", project=self.project)
                for index, kind in enumerate(["demo.thing.happened", "demo.other.done", "demo.thing.happened",
                                              "demo.other.done"])]

    def test_filters(self):
        stored = self.fill()
        found, _ = events.read_events(self.project, types=["demo.thing.*"])
        self.assertEqual([event.id for event in found], [stored[0].id, stored[2].id])
        found, _ = events.read_events(self.project, types=["demo.thing.*", "*.done"])
        self.assertEqual(len(found), 4)
        found, _ = events.read_events(self.project, types=["DEMO.*"])
        self.assertEqual(found, [])
        found, _ = events.read_events(self.project, since_id=stored[1].id)
        self.assertEqual([event.id for event in found], [stored[2].id, stored[3].id])
        found, _ = events.read_events(self.project, limit=2)
        self.assertEqual([event.id for event in found], [stored[2].id, stored[3].id])
        found, _ = events.read_events(self.project, limit=0)
        self.assertEqual(found, [])
        found, _ = events.read_events(self.project, types=["demo.thing.*"], since_id=stored[0].id, limit=5)
        self.assertEqual([event.id for event in found], [stored[2].id])
        with self.assertRaises(ExtError) as caught:
            events.read_events(self.project, since_id="f" * 32)
        self.assertEqual(caught.exception.code, "EVENT_NOT_FOUND")

    def test_unknown_extension_attributes_are_accepted(self):
        doc = events.build_event("demo.thing.happened", source="demo").to_json()
        doc["acmeflag"] = "yes"
        journal.append(self.journal, json.dumps(doc).encode())
        found, problems = events.read_events(self.project)
        self.assertEqual((len(found), problems), (1, []))
        self.assertEqual(found[0].extensions, {"acmeflag": "yes"})

    def test_broken_lines_are_reported_and_skipped(self):
        good = events.emit("demo.thing.happened", source="demo", project=self.project)
        valid = events.build_event("demo.thing.happened", source="demo").to_json()
        future = dict(valid, specversion="2.0")
        with_project = dict(valid, project="/x")
        path = journal.journal_path(self.journal)
        with open(path, "ab") as handle:
            for line in (b"not json\n", json.dumps(future).encode() + b"\n", json.dumps(with_project).encode() + b"\n",
                         b"[1]\n", b"\n", b"y" * (journal.MAX_LINE + 5) + b"\n", b"\xff\xfe\n"):
                handle.write(line)
        last = events.emit("demo.thing.happened", source="demo", project=self.project)
        found, problems = events.read_events(self.project)
        self.assertEqual([event.id for event in found], [good.id, last.id])
        self.assertEqual([problem["code"] for problem in problems],
                         ["EVENT_MALFORMED", "EVENT_VERSION_UNSUPPORTED", "EVENT_MALFORMED", "EVENT_MALFORMED",
                          "EVENT_MALFORMED", "EVENT_LINE_TOO_LONG", "EVENT_MALFORMED"])
        self.assertEqual(len({problem["offset"] for problem in problems}), 7)

    def test_torn_tail_gives_one_broken_line_and_later_events_survive(self):
        first = events.emit("demo.thing.happened", source="demo", project=self.project)
        with open(journal.journal_path(self.journal), "ab") as handle:
            handle.write(b'{"specversion":"1.0","id":')
        second = events.emit("demo.thing.happened", source="demo", project=self.project)
        found, problems = events.read_events(self.project)
        self.assertEqual([event.id for event in found], [first.id, second.id])
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["code"], "EVENT_MALFORMED")

    def test_incomplete_last_line_is_not_read_and_not_reported(self):
        first = events.emit("demo.thing.happened", source="demo", project=self.project)
        with open(journal.journal_path(self.journal), "ab") as handle:
            handle.write(json.dumps(events.build_event("demo.thing.happened", source="demo").to_json()).encode())
        found, problems = events.read_events(self.project)
        self.assertEqual(([event.id for event in found], problems), ([first.id], []))

    def test_missing_journal_and_negative_limit(self):
        self.assertEqual(events.read_events(self.project), ([], []))
        with self.assertRaises(ExtError):
            events.read_events(self.project, limit=-1)


if __name__ == "__main__":
    unittest.main()
