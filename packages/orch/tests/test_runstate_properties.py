"""Property tests of the RunState reducer: stdlib ``random.Random`` with fixed seeds, no external library."""
from __future__ import annotations

import copy
import json
import random
from unittest import mock
import unittest

from orch import contracts
from orch.port import PortError, RunState

RUN = "prop-run"
NOISE = ("model_wait", "output", "tool", "check")
TERMINAL_KINDS = ("completed", "failed", "timeout", "quota_block", "auth_block", "unknown_outcome", "cancelled")
RETRYABLE_KINDS = ("failed", "timeout", "quota_block", "auth_block", "unknown_outcome")
SEEDS = range(200)


def lifecycles(rng):
    """Per stage a correct list of (stage, attempt, kind), in order, with retries after retryable ends."""
    cycles = {}
    for number in range(rng.randint(1, 3)):
        stage, attempt, steps = f"stage-{number}", 1, []
        while True:
            steps.append((stage, attempt, "started"))
            steps += [(stage, attempt, rng.choice(NOISE)) for _ in range(rng.randint(0, 3))]
            end = rng.choice(TERMINAL_KINDS)
            steps.append((stage, attempt, end))
            if end in RETRYABLE_KINDS and attempt < 3 and rng.random() < 0.5:
                attempt += 1
                continue
            break
        cycles[stage] = steps
    return cycles


def interleave(rng, cycles):
    """A random merge that keeps the order inside each stage."""
    queues = [list(steps) for steps in cycles.values()]
    merged = []
    while any(queues):
        queue = rng.choice([q for q in queues if q])
        merged.append(queue.pop(0))
    return merged


def build(steps, rng, epoch=1):
    """Run-events with gapped seq, monotone ts, event_id evt-r-<seq> and one owner epoch."""
    events, seq = [], 0
    for stage, attempt, kind in steps:
        seq += rng.randint(1, 3)
        events.append({
            "$schema": "urn:swissknifeman:orch:exec:run-event:v1", "contract_version": "exec/v1",
            "run_id": RUN, "stage_id": stage, "attempt": attempt, "seq": seq,
            "ts": f"2026-10-05T{seq // 3600:02d}:{seq // 60 % 60:02d}:{seq % 60:02d}Z", "kind": kind,
            "event_id": f"evt-r-{seq}", "owner_epoch": epoch,
        })
    return events


def fold(events):
    state = RunState(RUN)
    for doc in events:
        state.apply(doc)
    return state


def summary(state):
    return {stage: (v["status"], v["attempt"], v["errors"], v["route_observed"])
            for stage, v in state.stages().items()}


_REAL_VALIDATE = contracts.validate
_validated: dict[str, list] = {}


def memoized_validate(doc, kind, registry=None):
    """Every distinct document is validated for real once; the 200 seeds repeat the same events many times."""
    key = kind + json.dumps(doc, sort_keys=True, default=repr)
    if key not in _validated:
        _validated[key] = _REAL_VALIDATE(doc, kind, registry)
    return list(_validated[key])


def setUpModule():
    global _patch
    _patch = mock.patch.object(contracts, "validate", memoized_validate)
    _patch.start()


def tearDownModule():
    _patch.stop()


def rejected(case, code, state, doc):
    before = (state.stages(), state.foreign())
    with case.assertRaises(PortError) as caught:
        state.apply(doc)
    case.assertEqual(caught.exception.code, code)
    case.assertEqual((state.stages(), state.foreign()), before)


class RunStatePropertyTests(unittest.TestCase):
    def cases(self):
        for seed in SEEDS:
            rng = random.Random(seed)
            cycles = lifecycles(rng)
            yield seed, rng, cycles, build(interleave(rng, cycles), rng)

    def test_p1_replay_gives_equal_state(self):
        for seed, _, _, events in self.cases():
            with self.subTest(seed=seed):
                self.assertEqual(fold(events).stages(), fold(copy.deepcopy(events)).stages())

    def test_p2_identical_copies_later_change_nothing(self):
        for seed, rng, _, events in self.cases():
            with self.subTest(seed=seed):
                expected, state, pending = fold(events).stages(), RunState(RUN), []
                for doc in events:
                    state.apply(doc)
                    pending.append(doc)
                    for _ in range(rng.randint(0, 2)):
                        state.apply(copy.deepcopy(rng.choice(pending)))
                self.assertEqual(state.stages(), expected)

    def test_p3_interleavings_agree_per_stage(self):
        for seed in SEEDS:
            rng = random.Random(seed)
            cycles = lifecycles(rng)
            first = fold(build(interleave(random.Random(seed + 1000), cycles), random.Random(seed)))
            second = fold(build(interleave(random.Random(seed + 2000), cycles), random.Random(seed + 7)))
            with self.subTest(seed=seed):
                self.assertEqual(summary(first), summary(second))

    def test_p4_seq_gaps_do_not_change_the_result(self):
        for seed in SEEDS:
            rng = random.Random(seed)
            steps = interleave(rng, lifecycles(rng))
            with self.subTest(seed=seed):
                self.assertEqual(summary(fold(build(steps, random.Random(1)))),
                                 summary(fold(build(steps, random.Random(2)))))

    def test_p5_changed_event_of_an_ended_attempt_is_after_terminal(self):
        for seed, rng, cycles, events in self.cases():
            with self.subTest(seed=seed):
                state = fold(events)
                stage = rng.choice(sorted(cycles))
                last = max(doc["attempt"] for doc in events if doc["stage_id"] == stage)
                top = events[-1]["seq"]
                late = dict(copy.deepcopy(events[0]), stage_id=stage, attempt=last, seq=top + 1,
                            kind=rng.choice(NOISE + TERMINAL_KINDS), event_id="evt-late")
                rejected(self, "AFTER_TERMINAL", state, late)

    def test_p6_foreign_version_events_leave_the_state_alone(self):
        for seed, rng, _, events in self.cases():
            with self.subTest(seed=seed):
                mixed, foreign = [], []
                for doc in events:
                    if rng.random() < 0.3:
                        stray = dict(copy.deepcopy(doc), contract_version="exec/v2", extra=rng.random())
                        foreign.append(stray)
                        mixed.append(stray)
                    mixed.append(doc)
                state = fold(mixed)
                self.assertEqual(state.stages(), fold(events).stages())
                self.assertEqual(state.foreign(), foreign)

    def test_p7_older_epoch_after_newer_is_stale(self):
        for seed, rng, _, events in self.cases():
            with self.subTest(seed=seed):
                cut = rng.randint(1, len(events))
                state = fold([dict(doc, owner_epoch=2) for doc in events[:cut]])
                stale = dict(copy.deepcopy(events[-1]), owner_epoch=1, seq=events[-1]["seq"] + 1, event_id="evt-stale")
                rejected(self, "STALE_EPOCH", state, stale)

    def test_p8_same_event_id_with_other_content_is_conflict(self):
        for seed, rng, _, events in self.cases():
            with self.subTest(seed=seed):
                state = fold(events)
                original = rng.choice(events)
                changed = dict(copy.deepcopy(original), summary=f"changed {seed}")
                rejected(self, "EVENT_CONFLICT", state, changed)


if __name__ == "__main__":
    unittest.main()
