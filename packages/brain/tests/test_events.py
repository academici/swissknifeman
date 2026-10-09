"""planner.plan.closed: the contract fixtures of the consumer and the parser's rules."""
import copy
import datetime
import unittest

from brain import errors, events
from brain.errors import BrainError
from tests.support import EVENTS, load_event

PLAN = "2026.01.15-DEMO-PLAN"


class TestFixtures(unittest.TestCase):
    def test_every_fixture_is_covered_here(self):
        covered = {"valid-minimal", "valid-full", "valid-additive", "other-type", "invalid-no-plan-id",
                   "invalid-data-not-object", "invalid-specversion"}
        self.assertEqual(covered, {path.stem for path in EVENTS.glob("*.json")})

    def test_valid_minimal(self):
        plan, reason = events.parse_plan_closed(load_event("valid-minimal"))
        self.assertIsNone(reason)
        self.assertEqual((PLAN, "Ecosystem split", "a1b2c3d4e5f60718293a4b5c6d7e8f90"),
                         (plan.plan_id, plan.title, plan.event_id))
        self.assertEqual((None, None, None, None, None, (), ()),
                         (plan.short_id, plan.status, plan.goal, plan.closed_at, plan.repository, plan.phases,
                          plan.counts))
        self.assertEqual("2026-10-09T09:15:30.250Z", plan.closed)  # the event time stands in for closed_at

    def test_valid_full(self):
        plan, _ = events.parse_plan_closed(load_event("valid-full"))
        self.assertEqual(("PLAN3", "done_with_deviations", "swissknifeman", "2026-10-09T09:59:41Z"),
                         (plan.short_id, plan.status, plan.repository, plan.closed_at))
        self.assertEqual("Split the monolith into independent modules.", plan.goal)
        self.assertEqual(["P6", "P7", "P8"], [p.id for p in plan.phases])
        self.assertEqual("Pipes | cells", plan.phases[2].title)
        self.assertEqual((("items", 12), ("done", 9), ("done_with_deviations", 2), ("cancelled", 1)), plan.counts)
        self.assertEqual("urn:swissknifeman:module:planner", plan.event_source)

    def test_valid_additive_ignores_unknown_fields_on_every_level(self):
        plan, reason = events.parse_plan_closed(load_event("valid-additive"))
        self.assertIsNone(reason)
        self.assertEqual("demo-additive", plan.plan_id)
        self.assertEqual((("items", 1), ("done", 1)), plan.counts)
        self.assertEqual(1, len(plan.phases))
        self.assertEqual(datetime.datetime(2026, 10, 9, 11, 30, tzinfo=datetime.timezone.utc), plan.closed_utc())

    def test_other_type_is_ignored(self):
        self.assertEqual((None, events.IGNORED), events.parse_plan_closed(load_event("other-type")))

    def test_invalid_fixtures_are_refused(self):
        for name in ("invalid-no-plan-id", "invalid-data-not-object", "invalid-specversion"):
            with self.subTest(fixture=name):
                with self.assertRaises(BrainError) as caught:
                    events.parse_plan_closed(load_event(name))
                self.assertEqual(errors.EVENT_DATA_INVALID, caught.exception.code)
                self.assertEqual(65, errors.exit_status(caught.exception.code))


class TestRules(unittest.TestCase):
    def with_data(self, **changes):
        doc = copy.deepcopy(load_event("valid-full"))
        for key, value in changes.items():
            if value is KeyError:
                doc["data"].pop(key, None)
            else:
                doc["data"][key] = value
        return doc

    def refused(self, doc):
        with self.assertRaises(BrainError) as caught:
            events.parse_plan_closed(doc)
        self.assertEqual(errors.EVENT_DATA_INVALID, caught.exception.code)
        return caught.exception.message

    def test_required_fields(self):
        self.assertIn("title", self.refused(self.with_data(title=KeyError)))
        self.assertIn("title", self.refused(self.with_data(title="   ")))
        self.assertIn("plan_id", self.refused(self.with_data(plan_id="")))

    def test_wrong_types_of_known_fields(self):
        for key, value in (("plan_id", 7), ("title", ["x"]), ("short_id", 3), ("status", {}), ("goal", 1),
                           ("repository", False), ("closed_at", 5), ("phases", {}), ("counts", []),
                           ("artifacts", "x")):
            with self.subTest(field=key):
                self.assertIn(key, self.refused(self.with_data(**{key: value})))

    def test_wrong_types_inside_phases_and_counts(self):
        self.refused(self.with_data(phases=["P1"]))
        self.refused(self.with_data(phases=[{"id": 1, "title": "t", "status": "s"}]))
        self.refused(self.with_data(counts={"items": -1}))
        self.refused(self.with_data(counts={"done": "3"}))
        self.refused(self.with_data(counts={"done": True}))

    def test_closed_at_must_be_rfc3339(self):
        for text in ("2026-10-09", "yesterday", "2026-13-01T00:00:00Z", "2026-10-09T10:00:00"):
            with self.subTest(text=text):
                self.refused(self.with_data(closed_at=text))

    def test_null_optional_fields_count_as_absent(self):
        plan, _ = events.parse_plan_closed(self.with_data(goal=None, phases=None, counts=None, closed_at=None))
        self.assertEqual((None, (), ()), (plan.goal, plan.phases, plan.counts))

    def test_envelope_problems_are_data_errors(self):
        self.refused([])
        self.refused({})
        doc = load_event("valid-minimal")
        del doc["id"]
        self.refused(doc)
        doc = load_event("valid-minimal")
        doc["source"] = "planner"
        self.refused(doc)

    def test_specversion_other_than_1_0_is_refused_even_for_other_types(self):
        doc = load_event("other-type")
        doc["specversion"] = "0.3"
        self.assertIn("specversion", self.refused(doc))

    def test_parse_time_forms(self):
        utc = datetime.timezone.utc
        self.assertEqual(datetime.datetime(2026, 1, 2, 3, 4, 5, 123000, tzinfo=utc),
                         events.parse_time("2026-01-02T03:04:05.123Z", "t"))
        self.assertEqual(datetime.datetime(2026, 1, 1, 22, 30, tzinfo=utc),
                         events.parse_time("2026-01-02T04:00:00+05:30", "t"))
        self.assertEqual(datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=utc),
                         events.parse_time("2026-01-02t03:04:05z", "t"))


if __name__ == "__main__":
    unittest.main()
