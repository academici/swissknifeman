"""A repeat is a fresh owner-bound run; it never rewrites terminal history."""
import copy
import json
import unittest
from pathlib import Path

try:
    from . import test_plan_work as work_fixture
except ImportError:
    import test_plan_work as work_fixture

from task import (journal, plan_delivery, plan_item_state, plan_readiness,
                  plan_recovery, plan_repeat, plan_work, terminal_policy, route_evidence)


class RepeatTests(unittest.TestCase):
    def setUp(self):
        fixture = work_fixture.PlanWorkTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.add_supporting_artifacts()
        self.plan, self.actual = fixture.plan, fixture.actual
        self.actual['invocation'] = 'task:plan-run WORK P1.1'
        snapshot = plan_readiness.design_snapshot(self.plan)
        for command, subject, result in [('plan-design', 'finish', 'no-op'),
                                         ('plan-audit', 'design', 'audit-green')]:
            journal.append(self.plan, journal.new_entry(
                plan_id='WORK', item_id=subject, command=command, actor='test',
                result=result, fingerprint=snapshot['fingerprint']))
        # Existing historical bytes intentionally predate the modern append policy.
        historical = journal.new_entry(plan_id='WORK', item_id='P1.1', command='plan-run',
                                       actor='migration', result='closed-green',
                                       note='Historical terminal import.')
        with (self.plan/'journal.jsonl').open('a') as stream:
            stream.write(json.dumps(historical) + '\n')
        plan_item_state.build_states(self.plan, item_id='P1.1', materialize_successor=False)
        (self.plan/'owner.md').write_text('Owner: repeat this item as a separate run.')
        self.record = plan_repeat.build(self.plan, 'P1.1', decision_id='D1',
                                        owner_message_path='owner.md', session_id='test-session')
        self.decision = self.plan/'decisions/D1-repeat.md'
        self.decision.parent.mkdir(exist_ok=True)
        self.decision.write_text(f'''---
id: D1
date: 2026-09-28
status: accepted
item: P1.1
items: [P1.1]
supersedes: []
superseded_by: null
---
# Repeat
## Решение
[REPEAT-ADMISSION:{plan_repeat.digest(self.record)}]
## Почему
Explicit owner instruction.
''')
        self.before = (self.plan/'journal.jsonl').read_bytes()

    def prepare(self, **kw):
        return plan_work.prepare(self.plan, 'P1.1', command='plan-run', actor='test',
                                 session_id='test-session', actual_route=self.actual, **kw)

    def test_ungranted_historical_repeat_stays_rejected(self):
        with self.assertRaisesRegex(plan_work.WorkError, 'BATCH_STALE'):
            self.prepare()
        self.assertEqual((self.plan/'journal.jsonl').read_bytes(), self.before)

    def test_valid_repeat_creates_attempt_two_and_preserves_route_and_history(self):
        started = self.prepare(repeat_admission=self.record)
        self.assertEqual(started['position']['attempt'], 2)
        self.assertTrue((self.plan/'journal.jsonl').read_bytes().startswith(self.before))
        receipt = route_evidence.run_receipt_from_journal(self.plan, started['position']['run_id'])
        self.assertEqual(receipt['evidence']['model_class'], 'implementation')
        resumed = self.prepare()
        self.assertEqual(started['position']['run_id'], resumed['position']['run_id'])

    def test_foreign_or_stale_record_never_mutates_journal(self):
        for field, value in [('plan_id', 'FOREIGN'), ('spec_sha256', '0'*64),
                             ('historical_terminal_sha256', '0'*64), ('session_id', 'foreign')]:
            with self.subTest(field=field):
                bad = dict(self.record, **{field: value})
                with self.assertRaises(ValueError):
                    self.prepare(repeat_admission=bad)
                self.assertEqual((self.plan/'journal.jsonl').read_bytes(), self.before)

    def test_revoked_grant_stays_rejected(self):
        self.decision.write_text(self.decision.read_text().replace('status: accepted','status: rejected'))
        with self.assertRaisesRegex(plan_repeat.RepeatError, 'REPEAT_OWNER_GRANT_MISSING'):
            self.prepare(repeat_admission=self.record)

    def test_route_gate_still_blocks_granted_repeat(self):
        self.actual['model_class']='economy'
        with self.assertRaisesRegex(plan_work.WorkError, 'ROUTE_UNDERSHOOT'):
            self.prepare(repeat_admission=self.record)
        self.assertEqual((self.plan/'journal.jsonl').read_bytes(), self.before)

    def test_consumed_grant_cannot_start_another_run(self):
        start = self.prepare(repeat_admission=self.record)
        decision=terminal_policy.build_decision(self.plan,'P1.1',result='closed-green',validation=[
            {'carrier':'local check','status':'green','evidence_ids':['test']}])
        journal.append(self.plan,journal.new_entry(plan_id='WORK',item_id='P1.1',command='plan-run',
                      actor='test',result='closed-green',run_id=start['position']['run_id'],
                      session_id='test-session',attempt=2,decision=decision))
        with self.assertRaisesRegex(plan_repeat.RepeatError, 'REPEAT_ALREADY_CONSUMED'):
            self.prepare(repeat_admission=self.record)
        # Repeat terminal handoff authenticates the original grant; no phase re-close.
        plan_item_state.build_states(self.plan,item_id='P1.1',materialize_successor=False)
        (self.plan/'handoff.md').write_text('''# HANDOFF — 2026-09-28 — after P1.1

**Next:** waiting: authorized repeat scope complete

| Параметр | Значение |
|:--|:--|
| Batch | — |
| Model | gpt-6-sol |
| Thinking | medium |
| Context | continue-root |
| Суть | Repeat done |

**Done:** repeat complete
**Remaining:** none
**Open risks:** none
''')
        receipt=plan_delivery.build_terminal_receipt(self.plan,'P1.1')
        self.assertEqual(receipt['journal']['run_id'],start['position']['run_id'])
        self.assertTrue((self.plan/'journal.jsonl').read_bytes().startswith(self.before))

    def test_changed_owner_provenance_is_rejected(self):
        (self.plan/'owner.md').write_text('Changed message')
        with self.assertRaisesRegex(plan_repeat.RepeatError, 'REPEAT_OWNER_MESSAGE_STALE'):
            self.prepare(repeat_admission=self.record)

    def test_repeat_keeps_phase_outcome_and_exposes_current_item_status(self):
        from task import plan_status
        self.prepare(repeat_admission=self.record)
        model = plan_status.status_model(self.plan)
        self.assertEqual(model['phases'][0]['status'], '🟢 Done')
        self.assertEqual(model['phases'][0]['items'][0]['status'], '🟡 In progress')
        self.decision.write_text(self.decision.read_text().replace('status: accepted', 'status: rejected'))
        with self.assertRaisesRegex(ValueError, 'REPEAT_OWNER_GRANT_MISSING'):
            plan_status.status_model(self.plan)

    def test_changed_phase_is_rejected(self):
        phase=self.plan/'phases/P1/P1.md'
        phase.write_text(phase.read_text()+'\nChanged contract.\n')
        with self.assertRaises(ValueError):
            self.prepare(repeat_admission=self.record)
        self.assertEqual((self.plan/'journal.jsonl').read_bytes(),self.before)
