"""plan.py followups: open follow_up / owner_decision entries of result.pending, closed by a follows_up link."""
import unittest

from planner.plan import ops, query, schema

try:
    from . import test_envelope, test_lifecycle
except ImportError:
    import test_envelope
    import test_lifecycle

PENDING = ["follow_up(write_set): widen the write set of later items", "owner_decision(docs): pick the wording",
           "polish names later", "follow_up(broken: no class", "follow_up(other): second leftover"]


class FollowupsTests(test_lifecycle.LifeCase):
    def finished(self, pending=PENDING):
        self.start("P1.1")
        self.finish("P1.1", pending=pending)

    def rows(self, **kwargs):
        found = query.followups(self.load(), **kwargs)
        self.assertEqual(schema.validate(found, "read-followups"), [])
        return found["followups"]

    def test_pending_entries_with_an_outcome_prefix_are_listed_with_their_class(self):
        self.finished()
        rows = self.rows()
        self.assertEqual([(r["item"], r["kind"], r["class"], r["status"]) for r in rows],
                         [("P1.1", "follow_up", "write_set", "open"), ("P1.1", "owner_decision", "docs", "open"),
                          ("P1.1", "follow_up", "other", "open")])
        self.assertEqual(rows[0]["text"], "widen the write set of later items")
        self.assertEqual(rows[0]["entry"], PENDING[0])
        self.assertEqual((rows[0]["phase"], rows[0]["resolved_by"]), ("P1", []))

    def test_an_item_without_pending_and_an_open_item_list_nothing(self):
        self.assertEqual(self.rows(), [])
        self.finished(pending=["only a plain pending"])
        self.assertEqual(self.rows(), [])

    def test_a_follows_up_link_from_another_item_closes_the_origin(self):
        self.finished()
        self.assertEqual(len(self.rows(open_only=True)), 3)
        ops.link(self.root, "P1.2", "P1.1", kind="related", relation="follows_up", note="resolves the follow-up")
        rows = self.rows()
        self.assertEqual({(r["status"], tuple(r["resolved_by"])) for r in rows}, {("resolved", ("P1.2",))})
        self.assertEqual(self.rows(open_only=True), [])

    def test_other_relations_and_directions_do_not_close(self):
        self.finished()
        ops.link(self.root, "P1.2", "P1.1", kind="related", relation="informs")
        ops.link(self.root, "P1.1", "P1.2", kind="related", relation="follows_up")
        self.assertEqual({r["status"] for r in self.rows()}, {"open"})


class FollowupsCliTests(test_envelope.EnvelopeCase):
    def test_the_verb_prints_a_json_envelope_and_filters_open(self):
        self.start("P1.1")
        self.finish("P1.1", pending=PENDING[:2])
        plan = str(self.root)
        self.assertEqual(len(self.envelope("followups", plan, code=0)["data"]["followups"]), 2)
        ops.link(self.root, "P1.2", "P1.1", kind="related", relation="follows_up")
        self.assertEqual(self.envelope("followups", plan, "--open", "--json", code=0)["data"]["followups"], [])
        self.assertEqual(len(self.envelope("followups", plan, code=0)["data"]["followups"]), 2)

    def test_the_verb_is_in_the_catalog_with_its_data_schema(self):
        self.assertIn("followups", test_envelope.verbs())
        rows = {row["name"]: row for row in self.envelope("schema", "--verbs", code=0)["data"]["verbs"]}
        self.assertEqual((rows["followups"]["mode"], rows["followups"]["data_kind"]), ("read", "read-followups"))


if __name__ == "__main__":
    unittest.main()
