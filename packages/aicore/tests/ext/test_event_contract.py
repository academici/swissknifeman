"""The event contract as a consumer sees it (E44): what a reader must keep, ignore and refuse.

A subscriber, a plugin or another tool reads ``events.jsonl`` and trusts these rules, so they are pinned with fixtures
of their own: one round trip, one additive change that must not break readers, and the malformed lines that must be
reported without losing the events around them. ``v1`` is the first version of the contract: there is no earlier
shape to upcast.
"""
import json

from aicore.ext import events, journal

from tests.ext.support import TempCase

TYPE = "demo.thing.happened"


class TestEventContract(TempCase):
    def valid(self, **changes):
        doc = events.build_event(TYPE, {"n": 1}, source="demo", subject="PLAN/P1").to_json()
        doc.update(changes)
        return doc

    def append(self, doc):
        journal.append(self.journal, json.dumps(doc).encode("utf-8"))

    def test_emit_then_read_returns_the_same_event(self):
        stored = events.emit(TYPE, {"b": [1, {"c": None}], "a": True}, source="demo", subject="PLAN/P1",
                             project=self.project, delivery="off", strict=True, correlationid="run-7")
        found, problems = events.read_events(self.project)
        self.assertEqual(problems, [])
        self.assertEqual(len(found), 1)
        event = found[0]
        for name in ("id", "source", "type", "time", "subject", "data", "correlationid"):
            self.assertEqual(getattr(event, name), getattr(stored, name), name)
        self.assertEqual(event.to_json(), stored.to_json())
        self.assertEqual(event.offset, stored.offset)

    def test_an_unknown_extension_attribute_is_ignored_and_the_event_is_kept(self):
        self.append(self.valid(acmeflag="yes", acmecount=3))
        found, problems = events.read_events(self.project)
        self.assertEqual(problems, [])
        self.assertEqual([event.type for event in found], [TYPE])
        self.assertEqual(found[0].extensions, {"acmecount": 3, "acmeflag": "yes"})
        self.assertEqual(found[0].data, {"n": 1})

    def test_malformed_lines_are_reported_and_never_lose_the_events_around_them(self):
        first = events.emit(TYPE, source="demo", project=self.project, delivery="off", strict=True)
        no_id = self.valid()
        del no_id["id"]
        cases = [
            ("EVENT_VERSION_UNSUPPORTED", self.valid(specversion="0.3")),
            ("EVENT_MALFORMED", no_id),
            ("EVENT_MALFORMED", self.valid(data_base64="eyJuIjogMX0=")),
            ("EVENT_MALFORMED", self.valid(data="not an object")),
        ]
        for _code, doc in cases:
            self.append(doc)
        last = events.emit(TYPE, source="demo", project=self.project, delivery="off", strict=True)
        found, problems = events.read_events(self.project)
        self.assertEqual([event.id for event in found], [first.id, last.id])
        self.assertEqual([problem["code"] for problem in problems], [code for code, _doc in cases])
        self.assertEqual(len({problem["offset"] for problem in problems}), len(cases))

    def test_each_refusal_names_the_offending_line_only(self):
        for code, doc in (("EVENT_VERSION_UNSUPPORTED", self.valid(specversion="0.3")),
                          ("EVENT_MALFORMED", self.valid(data="text"))):
            with self.subTest(code=code):
                offset = journal.append(self.journal, json.dumps(doc).encode("utf-8"))
                _found, problems = events.read_events(self.project)
                self.assertEqual(problems[-1]["offset"], offset)
                self.assertEqual(problems[-1]["code"], code)
