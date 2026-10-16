"""gui.core.events: seq, replay by cursor and epoch, snapshot_required, overflow, coalescing, heartbeats, filters."""
import asyncio
import unittest

from gui import contracts
from gui.core import events
from gui.core.events import EventHub, Meta

RUN_A = "run-" + "a" * 32
RUN_B = "run-" + "b" * 32


def run_doc(run_id, project="p-1"):
    return {"run_id": run_id, "owner": "xdemo", "context": {"project_id": project}}


def event_doc(type_, subject=None, n=0):
    doc = {"specversion": "1.0", "id": f"{n:032x}", "source": "urn:swissknifeman:module:planner", "type": type_,
           "time": "2026-10-16T12:00:00Z"}
    if subject:
        doc["subject"] = subject
    return doc


def drain(subscription):
    found = []
    while True:
        frame = subscription.get_nowait()
        if frame is None:
            return found
        found.append(frame)


class HubCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.hub = EventHub("epoch-0001", ring_frames=20, queue_frames=10)

    def log(self, run_id=RUN_A, chunk=0, project="p-1"):
        return self.hub.publish_log(run_doc(run_id, project), "stdout", chunk, f"line {chunk}\n", False)


class TestSequence(HubCase):
    async def test_seq_is_monotonic_and_frames_are_valid(self):
        subscription = self.hub.subscribe("all", {}, None, None)
        seqs = [self.log(chunk=i) for i in range(3)]
        seqs.append(self.hub.publish_run(run_doc(RUN_A), {"run_id": RUN_A, "state": "running"}))
        seqs.append(self.hub.publish_event(event_doc("planner.item.started"), "p-1"))
        self.assertEqual([1, 2, 3, 4, 5], seqs)
        frames = drain(subscription)
        self.assertEqual(seqs, [frame["seq"] for frame in frames])
        for frame in frames:
            self.assertEqual([], contracts.validate(frame, "stream"), frame)
            self.assertEqual("all", frame["sub"])

    async def test_get_waits_for_the_next_frame(self):
        subscription = self.hub.subscribe("w", {}, None, None)
        waiter = asyncio.create_task(subscription.get())
        await asyncio.sleep(0)
        self.log()
        frame = await asyncio.wait_for(waiter, 1)
        self.assertEqual("log", frame["kind"])


class TestReplay(HubCase):
    async def test_replay_after_a_cursor_without_gaps_or_duplicates(self):
        first = self.hub.subscribe("s", {}, None, None)
        for i in range(5):
            self.log(chunk=i)
        seen = drain(first)[:2]
        self.hub.unsubscribe(first)
        for i in range(5, 7):
            self.log(chunk=i)
        again = self.hub.subscribe("s", {}, seen[-1]["seq"], "epoch-0001")
        self.log(chunk=7)
        chunks = [frame["chunk"] for frame in drain(again)]
        self.assertEqual(list(range(2, 8)), chunks)

    async def test_cursor_at_the_end_replays_nothing(self):
        self.log()
        subscription = self.hub.subscribe("s", {}, self.hub.seq, "epoch-0001")
        self.assertEqual([], drain(subscription))

    async def test_expired_cursor_and_other_epoch(self):
        for i in range(30):
            self.log(chunk=i)
        for cursor, epoch in ((2, "epoch-0001"), (25, "epoch-other"), (999, "epoch-0001")):
            with self.subTest(cursor=cursor, epoch=epoch):
                subscription = self.hub.subscribe("s", {}, cursor, epoch)
                frames = drain(subscription)
                self.assertEqual([{"$schema": events.CONTRACT, "kind": "snapshot_required", "sub": "s",
                                   "reason": "cursor_expired"}], frames)
                self.assertEqual([], contracts.validate(frames[0], "stream"))
                self.hub.unsubscribe(subscription)

    async def test_cursor_without_epoch_is_not_a_stream_frame(self):
        frame = {"$schema": events.CONTRACT, "kind": "subscribe", "id": "s", "filter": {}, "cursor": 3, "epoch": None}
        self.assertNotEqual([], contracts.validate(frame, "stream"))


class TestFlow(HubCase):
    async def test_overflow_drops_the_queue_and_keeps_the_subscription(self):
        subscription = self.hub.subscribe("slow", {}, None, None)
        for i in range(15):
            self.log(chunk=i)
        frames = drain(subscription)
        self.assertEqual("snapshot_required", frames[0]["kind"])
        self.assertEqual("overflow", frames[0]["reason"])
        self.assertEqual([11, 12, 13, 14], [frame["chunk"] for frame in frames[1:]])  # 10 overflowed
        self.assertIn(subscription, self.hub.subscriptions)

    async def test_progress_events_coalesce(self):
        subscription = self.hub.subscribe("p", {}, None, None)
        for n in range(4):
            self.hub.publish_event(event_doc("orch.run.progress", "run-1", n), "p-1")
        self.hub.publish_event(event_doc("orch.run.progress", "run-2", 9), "p-1")
        self.hub.publish_event(event_doc("orch.run.finished", "run-1", 10), "p-1")
        frames = drain(subscription)
        self.assertEqual([("orch.run.progress", "run-1", f"{3:032x}"), ("orch.run.progress", "run-2", f"{9:032x}"),
                          ("orch.run.finished", "run-1", f"{10:032x}")],
                         [(f["event"]["type"], f["event"]["subject"], f["event"]["id"]) for f in frames])

    async def test_progress_after_the_window_is_kept(self):
        now = [0.0]
        subscription = events.Subscription("p", {}, 10, clock=lambda: now[0])
        subscription.offer({"kind": "event", "seq": 1, "event": event_doc("x.y.progress", "s", 1)})
        now[0] = 1.0
        subscription.offer({"kind": "event", "seq": 2, "event": event_doc("x.y.progress", "s", 2)})
        self.assertEqual(2, subscription.pending())

    async def test_heartbeat_has_a_seq_and_no_sub(self):
        listener = self.hub.listen()
        self.log()
        seq = self.hub.heartbeat()
        frame = drain(listener)[0]
        self.assertEqual(("heartbeat", seq), (frame["kind"], frame["seq"]))
        self.assertNotIn("sub", frame)
        self.assertEqual([], contracts.validate(frame, "stream"))
        for _ in range(10):
            self.hub.heartbeat()
        self.assertLessEqual(listener.pending(), listener.limit)


class TestFilters(HubCase):
    async def test_filters(self):
        cases = {"projects": ({"projects": ["p-2"]}, 1), "runs": ({"runs": [RUN_B]}, 1),
                 "owners": ({"owners": ["planner"]}, 1), "types": ({"types": ["planner.*"]}, 1),
                 "logs": ({"types": ["gui.log"]}, 2), "and": ({"projects": ["p-1"], "types": ["gui.*"]}, 1)}
        subscriptions = {name: self.hub.subscribe(name, spec, None, None) for name, (spec, _) in cases.items()}
        self.log(RUN_A, project="p-1")
        self.log(RUN_B, project="p-2")
        self.hub.publish_event(event_doc("planner.item.done"), "p-3")
        for name, (_, expected) in cases.items():
            with self.subTest(filter=name):
                self.assertEqual(expected, len(drain(subscriptions[name])))
        self.assertTrue(events.matches({}, Meta()))


if __name__ == "__main__":
    unittest.main()
