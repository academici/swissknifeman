"""Delivery through aicore: the subscription brain:plan-notes, redelivery by the cursor, dead letters, replay (R06).

The events are journaled in a throwaway project and delivered synchronously; the subscriber is the real
``bin/brain note`` run by aicore with its cleaned environment. No background process is started.
"""
import json
import os
import unittest

import aicore
from aicore.ext import delivery, emit, journal, read_events
from aicore.ext import settings as ext_settings
from aicore.ext import units

from brain import frontmatter
from tests.support import MODULE_ROOT, TempCase, load_event

AICORE_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(aicore.__file__))))
SUBSCRIPTION = "brain:plan-notes"
PLAN = "2026.10.07-№1-SKM-ECOSYSTEM"


class SubscriptionCase(TempCase):
    def setUp(self):
        super().setUp()
        self.env.update(PATH=os.environ.get("PATH", ""), SKM_UNITS_PATH=str(MODULE_ROOT), AICORE_ROOT=AICORE_ROOT)
        self.claim_project(self.project)
        self.configure()
        self.jdir = journal.journal_dir(str(self.project), env=self.env, home=self.home)

    def configure(self, extra="", vault=True):
        vault_line = f'[brain]\nvault_path = "{self.vault}"\n' if vault else ""
        self.machine_config('[aicore.events]\ndelivery = "off"\n' + vault_line + extra)

    def closed(self, plan_id=PLAN, mode="sync", **data):
        payload = dict(load_event("valid-full")["data"], plan_id=plan_id, **data)
        return emit("planner.plan.closed", payload, source="planner", subject=plan_id, project=self.project,
                    delivery=mode, env=self.env, home=self.home)

    def deliver(self):
        return delivery.deliver(self.jdir, project=self.project, env=self.env, home=self.home)

    def row(self):
        status = delivery.delivery_status(self.jdir, project=self.project, env=self.env, home=self.home)
        return [item for item in status["subscriptions"] if item["id"] == SUBSCRIPTION][0]

    def notes(self):
        return sorted(p for p in self.vault.rglob("*.md") if p.name != "Demo.md")

    def note_event_ids(self):
        return sorted(frontmatter.read(p).get("event_id") for p in self.notes())

    def created(self):
        found, problems = read_events(self.project, types=["brain.note.created"], env=self.env, home=self.home)
        self.assertEqual([], problems)
        return found

    def fail_until_dead_letter(self):
        for _ in range(ext_settings.load(self.project, env=self.env, home=self.home).max_attempts + 1):
            if self.row()["dead_letters"]:
                return
            self.deliver()
        self.assertEqual(1, self.row()["dead_letters"])


class TestDeclaration(SubscriptionCase):
    def test_aicore_reads_the_subscription_from_unit_json(self):
        found, problems = delivery.resolve_subscriptions(
            ext_settings.load(self.project, env=self.env, home=self.home), units.discover_units(self.env), self.project)
        self.assertEqual([], problems)
        (subscription,) = [s for s in found if s.id == SUBSCRIPTION]
        self.assertEqual(("planner.plan.closed",), subscription.on)
        self.assertEqual(30, subscription.timeout_seconds)
        self.assertEqual((str(MODULE_ROOT / "bin" / "brain"), "note", "--event", "-"), subscription.run)
        self.assertTrue(subscription.enabled)


class TestDelivery(SubscriptionCase):
    def test_emit_writes_the_note_and_the_cursor_is_caught_up(self):
        event = self.closed()
        (note,) = self.notes()
        self.assertEqual(self.vault / "05-Projects" / "03-Packages" / "Demo" / "Ecosystem" / "Plans", note.parent)
        self.assertEqual(event.id, frontmatter.read(note)["event_id"])
        row = self.row()
        self.assertEqual((0, None, 0), (row["lag"], row["pending"], row["dead_letters"]))
        (announced,) = self.created()
        self.assertEqual(event.id, announced.causationid)
        self.assertEqual("urn:swissknifeman:module:brain", announced.source)
        self.assertEqual(note.relative_to(self.vault).as_posix(), announced.data["note"])

    def test_replay_from_the_start_does_not_duplicate(self):
        event = self.closed()
        delivery.replay(self.jdir, SUBSCRIPTION, from_start=True, project=self.project, env=self.env, home=self.home)
        delivery.replay(self.jdir, SUBSCRIPTION, from_start=True, project=self.project, env=self.env, home=self.home)
        self.assertEqual([event.id], self.note_event_ids())
        self.assertEqual(1, len(self.created()))
        self.assertEqual(0, self.row()["lag"])

    def test_two_plans_give_two_notes(self):
        first, second = self.closed("2026.10.01-№1-FIRST"), self.closed("2026.10.02-№1-SECOND")
        self.assertEqual(sorted([first.id, second.id]), self.note_event_ids())
        self.assertEqual(2, len(self.created()))

    def test_without_a_vault_the_event_is_skipped_and_the_cursor_moves(self):
        self.configure(vault=False)
        self.closed()
        self.assertEqual([], self.notes())
        row = self.row()
        self.assertEqual((0, None, 0), (row["lag"], row["pending"], row["dead_letters"]))
        self.assertIsNotNone(row["offset"])
        self.assertEqual([], self.created())

    def test_a_switched_off_subscription_writes_nothing(self):
        self.configure(f'[aicore.subscriptions."{SUBSCRIPTION}"]\nenabled = false\n')
        self.closed()
        self.assertEqual([], self.notes())

    def test_notes_disabled_skips_and_moves_the_cursor(self):
        self.configure('[brain.notes]\nenabled = false\n')
        self.closed()
        self.assertEqual([], self.notes())
        self.assertEqual((0, None), (self.row()["lag"], self.row()["pending"]))

    def test_other_plan_events_are_not_delivered(self):
        emit("planner.plan.opened", load_event("valid-minimal")["data"], source="planner", project=self.project,
             delivery="sync", env=self.env, home=self.home)
        self.assertEqual([], self.notes())


@unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
class TestFailureAndRetry(SubscriptionCase):
    def lock_notes_folder(self):
        folder = self.vault / "05-Projects" / "03-Packages" / "Demo" / "Ecosystem" / "Plans"
        folder.mkdir(parents=True, exist_ok=True)
        folder.chmod(0o555)
        self.addCleanup(folder.chmod, 0o755)
        return folder

    def test_a_failure_keeps_the_cursor_and_the_next_delivery_writes_the_note(self):
        """R06: the event is not lost when the vault cannot be written; the same event is delivered again."""
        first = self.closed("2026.10.01-№1-FIRST")
        folder = self.lock_notes_folder()
        second = self.closed("2026.10.02-№1-SECOND")
        row = self.row()
        self.assertEqual(second.id, row["pending"]["event_id"])
        self.assertEqual(1, row["pending"]["attempts"])
        self.assertEqual(1, row["lag"])
        self.assertEqual([first.id], self.note_event_ids())
        folder.chmod(0o755)
        self.deliver()
        self.assertEqual(sorted([first.id, second.id]), self.note_event_ids())
        row = self.row()
        self.assertEqual((0, None, 0), (row["lag"], row["pending"], row["dead_letters"]))
        self.assertEqual({first.id, second.id}, {e.causationid for e in self.created()})
        self.assertEqual([], [p for p in self.vault.rglob("*") if ".tmp-" in p.name])

    def test_after_the_last_attempt_the_event_is_a_dead_letter_and_replay_delivers_it(self):
        folder = self.lock_notes_folder()
        event = self.closed()
        self.fail_until_dead_letter()
        row = self.row()
        self.assertEqual((0, None, 1), (row["lag"], row["pending"], row["dead_letters"]))
        self.assertEqual([], self.notes())
        folder.chmod(0o755)
        delivery.replay(self.jdir, SUBSCRIPTION, event_id=event.id, project=self.project, env=self.env, home=self.home)
        self.assertEqual([event.id], self.note_event_ids())
        self.assertEqual(0, self.row()["dead_letters"])

    def test_bad_event_data_is_never_written_and_ends_in_the_dead_letters(self):
        emit("planner.plan.closed", {"title": "No plan id"}, source="planner", subject=PLAN, project=self.project,
             delivery="sync", env=self.env, home=self.home)
        self.fail_until_dead_letter()
        self.assertEqual([], self.notes())
        records = [json.loads(line) for line in delivery.deliveries_path(self.jdir).read_text(encoding="utf-8").splitlines()]
        self.assertTrue(any(r.get("exit") == 65 for r in records), records)


if __name__ == "__main__":
    unittest.main()
