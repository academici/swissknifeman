"""Real temporary-repository operations; no caller-supplied executed evidence.

The scenario chooses an order; it is not an additional production workflow engine.
"""
import hashlib
import contextlib
import io
import json
import subprocess
import runpy
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fixtures import write_valid_plan, write_v2_carriers
from task import (journal, plan_bundle, plan_closure, plan_context, plan_delivery, plan_evidence,
                  plan_gates, plan_item_state, plan_lifecycle, plan_projection,
                  plan_repair, plan_status, task_contract, terminal_policy)
from task.plan_lint_checks.common import _lint_audit_terminal_policy
from task.plan_lint import Diagnostics
from test_plan_repair import record

ROOT = Path(__file__).resolve().parents[3]


class LifecycleScenarios(unittest.TestCase):
    def test_real_low_risk_operations_and_interrupted_projection_recovery(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commands = []

            def run(*argv):
                started = time.monotonic()
                result = subprocess.run(argv, cwd=root, text=True, capture_output=True)
                commands.append((argv, result.returncode, time.monotonic() - started))
                self.assertEqual(result.returncode, 0, result.stderr)
                return result.stdout.strip()

            run('git', 'init', '-q')
            run('git', 'config', 'user.email', 'scenario@example.invalid')
            run('git', 'config', 'user.name', 'Scenario')
            plan = write_valid_plan(root, 'SCENARIO', layout='v2')
            spec = plan / 'phases/P1/P1.1.md'
            phase = plan / 'phases/P1/P1.md'
            phase.write_text(phase.read_text() +
                             '\n> **Phase Assurance | v1.**\n'
                             '> Impact: internal-integration\n'
                             '> Integration Seams: successor-closure-carrier\n'
                             '> Live or Irreversible: no\n'
                             '> Audit Intent: required\n'
                             '> Rationale: legacy required must remain advisory\n\n'
                             '> **Контракт фазы | v1.**\n'
                             '> Produce one validated result for the successor.\n')
            # Product is distinct from digest inputs: no synthetic collision waiver.
            product = root / 'result.txt'
            product.write_text('before\n')
            spec.write_text(spec.read_text().replace('**Files:** lib/pkg/config.py',
                                                     '**Files:** `result.txt`').replace('**Validation:** bash scripts/test.sh — зелёный.',
                                                     '**Validation:** `python3 validate.py`'))
            successor_spec = spec.read_text().replace('P1.1', 'P2.1').replace(
                '**Inputs:** `lib/pkg/config.py`.',
                '**Inputs:** `phases/P1/P1.closed.md`.').replace(
                '**Required Reads:** 1) lib/pkg/config.py',
                '**Required Reads:** 1) `phases/P1/P1.closed.md`')
            write_v2_carriers(
                plan, phase_id='P2', item_id='P2.1', item_spec=successor_spec,
                item_state=(
                    '**Status:** ⬜ Not started\n'
                    '**Completion Notes:** —\n'
                    '**Pending Work:** —\n'
                    '**Known Deviations:** —\n'
                    '**Escalation Needed:** —\n'),
                refresh_views=False,
            )
            plan_status.build_status(plan)
            plan_bundle.build(plan, 'P1.1')
            handoff = plan / 'handoff.md'
            handoff.write_text(handoff.read_text().replace(
                '/task:plan-run SCENARIO P1.1', '/task:plan-run SCENARIO P2.1'))
            (plan / 'journal.jsonl').write_text('')
            plan_item_state.build_states(plan, item_id='P1.1')
            (root / 'validate.py').write_text("from pathlib import Path; assert Path('result.txt').read_text() == 'after\\n'\n")
            run('git', 'add', '.')
            run('git', 'commit', '-qm', 'fixture')
            before = int(run('git', 'rev-list', '--count', 'HEAD'))
            prepared = json.loads(run(sys.executable, str(ROOT / 'packages/task/scripts/plan-session.py'),
                                     'prepare', '--plan-dir', str(plan), '--item', 'P1.1', '--risk', 'none'))
            self.assertEqual(prepared['advice']['review'], 'none')
            self.assertEqual(prepared['evidence_graph']['collisions'], [])
            product.write_text('after\n')
            validation = ('python3', 'validate.py')
            run(*validation)
            evidence = [{'carrier': 'python3 validate.py', 'status': 'green',
                         'evidence_ids': ['actual-subprocess:exit-0']}]
            decision = terminal_policy.build_decision(plan, 'P1.1', result='closed-green', validation=evidence)
            journal.append(plan, journal.new_entry(
                plan_id=plan.name, item_id='P1.1', command='plan-run',
                actor='implementation/high', result='in-progress',
                session_id='scenario', run_id='scenario-run'))
            event = journal.new_entry(plan_id=plan.name, item_id='P1.1', command='plan-run',
                                      actor='implementation/high', result='closed-green',
                                      session_id='scenario', run_id='scenario-run', decision=decision,
                                      fingerprint=hashlib.sha256(product.read_bytes()).hexdigest())
            _, _, appended = journal.append_idempotent_terminal(plan, event)
            self.assertTrue(appended)
            # Crash before projection: a terminal journal alone cannot deliver GREEN.
            with self.assertRaises(plan_delivery.DeliveryError):
                plan_delivery.build_terminal_receipt(plan, 'P1.1')
            with patch.object(plan_projection.os, 'replace', wraps=plan_projection.os.replace) as writes:
                plan_item_state.build_states(plan, item_id='P1.1')
                self.assertEqual(writes.call_count, 1)
                candidate = plan_gates.phase_candidate_fingerprint(plan, 'P1')
                policy = plan_gates.phase_audit_policy(
                    plan, 'P1', candidate_snapshot=candidate['snapshot'])
                self.assertEqual(policy['next_kind'], 'close')
                self.assertTrue(policy['close_allowed'])
                self.assertFalse(policy['audit_required'])
                self.assertTrue(plan_gates.phase_close_gate(
                    plan, 'P1', candidate_fingerprint=candidate['fingerprint'],
                    candidate_snapshot=candidate['snapshot'])['allow'])
                plan_status.build_status(plan)
                plan_closure.build_closure(plan, 'P1')
                journal.append(plan, journal.new_entry(
                    plan_id=plan.name, item_id='P1', command='plan-close',
                    actor='implementation/high', result='in-progress',
                    session_id='scenario', run_id='scenario-phase-run'))
                journal.append(plan, journal.new_entry(
                    plan_id=plan.name, item_id='P1', command='plan-close',
                    actor='implementation/high', result='closed-green',
                    session_id='scenario', run_id='scenario-phase-run',
                    fingerprint=candidate['fingerprint']))
                plan_bundle.build(plan, 'P2.1')
                receipt = plan_delivery.build_terminal_receipt(plan, 'P1.1')
                _, _, appended = journal.append_idempotent_terminal(plan, event)
                self.assertFalse(appended)
                writes_before_rebuild = writes.call_count
                plan_item_state.build_states(plan, item_id='P1.1')
                self.assertEqual(writes.call_count, writes_before_rebuild)
                self.assertEqual(receipt['next_exact'], '/task:plan-run SCENARIO P2.1')
                self.assertIsNotNone(receipt['digests']['closure'])
            run('git', 'add', '.')
            run('git', 'commit', '-qm', 'fix: результат и evidence')
            self.assertTrue(plan_delivery.verify_receipt(plan, receipt))
            self.assertEqual(int(run('git', 'rev-list', '--count', 'HEAD')) - before, 1)
            self.assertEqual(sum(argv == validation for argv, _, _ in commands), 1)
            events = [json.loads(line) for line in (plan / 'journal.jsonl').read_text().splitlines()]
            self.assertEqual(len(events), 4)
            self.assertFalse(any(event['command'] == 'plan-audit' for event in events))
            self.assertEqual(events[-1]['item_id'], 'P1')
            self.assertEqual(run('git', 'status', '--porcelain'), '')
            spec.write_text(spec.read_text() + '\nchanged acceptance input\n')
            with self.assertRaises((plan_delivery.DeliveryError, journal.JournalValidationError)):
                journal.append_idempotent_terminal(plan, event)

    def test_reviewer_returns_product_defect_through_journal_lint_and_delivery(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = write_valid_plan(Path(temporary), 'AUDIT-RETURN', layout='v2')
            phase = plan / 'phases/P1/P1.md'
            next_exact = 'run-items: task:plan-run AUDIT-RETURN P1.1'
            phase.write_text(phase.read_text() + '\n## Audit P1 — 2026-09-10\n\n'
                             '**Вердикт: ATTENTION**\n\n### Что запускать\n\n'
                             f'Semantic Next: `{next_exact}`.\n\n'
                             '| Batch | Model | Thinking | Context | Суть | Команда |\n'
                             '|:--|:--|:--|:--|:--|:--|\n'
                             '| solo | implementation | high | `continue-root` | repair | '
                             '`$ task:plan-run AUDIT-RETURN P1.1` |\n')
            event = journal.new_entry(plan_id=plan.name, item_id='P1', command='plan-audit',
                actor='frontier/xhigh', result='audit-attention', fingerprint='a' * 64,
                decision={'signal_class': 'acceptance', 'scope_class': 'P1.1',
                          'action': 'return-owning-continuation', 'terminal': False,
                          'recovered': False, 'reason_code': 'REPRODUCED_PRODUCT_DEFECT',
                          'evidence_ids': ['test:repro'], 'continuation': next_exact})
            journal.append(plan, event)
            diag = Diagnostics()
            _lint_audit_terminal_policy(phase.read_text().splitlines(), phase, plan, plan.name, 'P1', diag)
            self.assertEqual(diag.errors, [])
            self.assertEqual(plan_delivery.build_handoff_receipt(plan, 'P1')['next_exact'], next_exact)
            self.assertFalse(plan_gates.phase_close_gate(plan, 'P1', candidate_fingerprint='a' * 64)['allow'])
            # Executor repair and actual delta verification precede the reviewer GREEN.
            product = plan / 'lib/pkg/config.py'
            product.write_text("VALUE = 'repaired'\n")
            result = subprocess.run([sys.executable, '-c', "from pathlib import Path; assert 'repaired' in Path('lib/pkg/config.py').read_text()"], cwd=plan)
            self.assertEqual(result.returncode, 0)
            journal.append(plan, journal.new_entry(plan_id=plan.name, item_id='P1.1', command='plan-run',
                                                  actor='implementation/high', result='local-repair'))
            fingerprint = hashlib.sha256(product.read_bytes()).hexdigest()
            journal.append(plan, journal.new_entry(plan_id=plan.name, item_id='P1', command='plan-audit',
                                                  actor='frontier/xhigh', result='audit-green', fingerprint=fingerprint))
            self.assertTrue(plan_gates.phase_close_gate(plan, 'P1', candidate_fingerprint=fingerprint)['allow'])
            self.assertFalse(plan_gates.phase_close_gate(plan, 'P1', candidate_fingerprint='c' * 64)['allow'])

    def test_four_files_and_authorized_product_delta_are_execution(self):
        value = record(baseline={'reproduced': False, 'carrier': None})
        value['material_surface']['product'] = True
        value['bounded_diff']['files_changed'] = 4
        value['affected_paths'] = [{'path': f'file{n}.py', 'owner_item': 'P2.1', 'declared_file': False} for n in range(4)]
        self.assertEqual(plan_repair.evaluate(value)['action'], 'repair-in-current-attempt')
        value['material_surface']['authority'] = True
        self.assertEqual(plan_repair.evaluate(value)['action'], 'gather-evidence')
        value['design'] = {'decision_question': 'new Acceptance?', 'evidence_gap': 'owner choice',
                           'alternatives': ['keep', 'change'], 'expected_artifact': 'D1'}
        self.assertEqual(plan_repair.evaluate(value)['action'], 'design-required')

    def test_foreign_baseline_intersection_is_gating(self):
        for owned, blocks in ((set(), False), ({'old'}, True)):
            result = plan_gates.baseline_delta(current_failures={'old'}, baseline_failures={'old'}, owned_failures=owned)
            self.assertEqual(result['blocks'], blocks)
            self.assertEqual(result['pre_existing'], ('old',))

    def test_installed_probe_detects_actual_stale_and_missing_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            source, installed = Path(temporary) / 'source', Path(temporary) / 'installed'
            source.mkdir(); installed.mkdir()
            (source / 'SKILL.md').write_text('canonical')
            (installed / 'SKILL.md').write_text('stale')
            argv = [sys.executable, str(ROOT / 'packages/task/scripts/plan-session.py'),
                    'installed', '--source', str(source), '--installed', str(installed)]
            result = subprocess.run(argv, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(len(json.loads(result.stdout)['mismatches']), 1)
            (installed / 'SKILL.md').write_text('canonical')
            result = subprocess.run(argv, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0)
            report = json.loads(result.stdout)
            self.assertEqual(report['source_digest'], report['installed_digest'])
            (installed / 'stale.sh').write_text('obsolete')
            result = subprocess.run(argv, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)['mismatches'][0]['path'], 'stale.sh')

    def test_old_repair_record_remains_readable_but_new_append_uses_current_policy(self):
        value = record(baseline={'reproduced': False, 'carrier': None})
        value['material_surface']['product'] = True
        entry = journal.new_entry(plan_id='OLD', item_id='P2.1', command='plan-run',
                                  actor='implementation/high', result='local-repair')
        entry.update(repair_decision=value, repair_digest=plan_repair.digest(value),
                     repair_action='gather-evidence')
        journal.validate_entry(entry)
        with self.assertRaises(journal.JournalValidationError):
            journal.validate_append_policy(entry)

    def test_material_repair_requires_actual_declared_owner_scope(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = write_valid_plan(Path(temporary), 'MATERIAL', layout='v2')
            value = record(plan_id=plan.name, item_id='P1.1', baseline={'reproduced': False, 'carrier': None})
            value['material_surface']['security'] = True
            value['candidate'] = {'delta_proved': True, 'evidence_ids': ['test:impact']}
            value['affected_paths'] = [{'path': 'lib/pkg/config.py', 'owner_item': 'P1.1', 'declared_file': True}]
            self.assertEqual(plan_repair.evaluate(value)['action'], 'gather-evidence')
            self.assertEqual(plan_repair.evaluate(value, plan_dir=plan)['action'], 'repair-in-current-attempt')
            entry = journal.new_entry(plan_id=plan.name, item_id='P1.1', command='plan-run',
                                      actor='implementation/high', result='local-repair')
            entry.update(repair_decision=value, repair_digest=plan_repair.digest(value),
                         repair_action='repair-in-current-attempt')
            journal.append(plan, entry)
            value['affected_paths'][0]['owner_item'] = 'P1.2'
            self.assertEqual(plan_repair.evaluate(value, plan_dir=plan)['action'], 'gather-evidence')
            value['affected_paths'][0].update(owner_item='P1.1', path='outside.py')
            self.assertEqual(plan_repair.evaluate(value, plan_dir=plan)['action'], 'gather-evidence')

    def test_audit_nonexistent_or_wrong_owner_is_rejected_before_append(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = write_valid_plan(Path(temporary), 'BAD-RETURN', layout='v2')
            for scope, target in (('P1.999', 'P1.999'), ('P1.2', 'P1.1')):
                entry = journal.new_entry(plan_id=plan.name, item_id='P1', command='plan-audit',
                    actor='frontier/xhigh', result='audit-attention',
                    decision={'signal_class': 'acceptance', 'scope_class': scope,
                              'action': 'return-owning-continuation', 'terminal': False,
                              'recovered': False, 'reason_code': 'PRODUCT_DEFECT',
                              'evidence_ids': ['test:repro'],
                              'continuation': f'run-items: task:plan-run {plan.name} {target}'})
                before = (plan / 'journal.jsonl').read_bytes()
                with self.assertRaises(journal.JournalValidationError):
                    journal.append(plan, entry)
                self.assertEqual((plan / 'journal.jsonl').read_bytes(), before)

    def test_prepare_repairs_stale_selected_state_before_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = write_valid_plan(Path(temporary), 'STALE-PREPARE', layout='v2')
            journal.append(plan, journal.new_entry(plan_id=plan.name, item_id='P1.1', command='plan-run',
                                                  actor='implementation/high', result='in-progress'))
            argv = [sys.executable, str(ROOT / 'packages/task/scripts/plan-session.py'), 'prepare',
                    '--plan-dir', str(plan), '--item', 'P1.1', '--risk']
            repaired = subprocess.run([*argv, 'none'], capture_output=True, text=True)
            self.assertEqual(repaired.returncode, 0, repaired.stderr)
            self.assertIn('"snapshot_sha256"', repaired.stdout)
            unknown = subprocess.run([*argv, 'security_auth'], capture_output=True, text=True)
            self.assertEqual(unknown.returncode, 1)
            self.assertIn('ERROR:', unknown.stderr)

    def test_prepare_rechecks_state_after_concurrent_journal_append(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = write_valid_plan(Path(temporary), 'RACING-PREPARE', layout='v2')
            capture = plan_context.capture

            def concurrent_capture(*args, **kwargs):
                journal.append(plan, journal.new_entry(plan_id=plan.name, item_id='P1.1',
                    command='plan-run', actor='implementation/high', result='in-progress'))
                return capture(*args, **kwargs)

            command = runpy.run_path(str(ROOT / 'packages/task/scripts/plan-session.py'))
            errors = io.StringIO()
            argv = ['plan-session.py', 'prepare', '--plan-dir', str(plan),
                    '--item', 'P1.1', '--risk', 'none']
            with patch.object(sys, 'argv', argv), patch.object(plan_context, 'capture', concurrent_capture), contextlib.redirect_stderr(errors):
                self.assertEqual(command['main'](), 1)
            self.assertIn('ERROR:', errors.getvalue())

    def test_two_orders_and_ready_subset_preserve_historical_required_group(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan = write_valid_plan(Path(temporary), 'ORDER', layout='v2')
            write_v2_carriers(plan, item_id='P1.2', refresh_views=False)
            core = plan / 'plan.md'
            core.write_text(core.read_text().replace('## 3. Routing\n\n',
                '## 3. Routing\n\n| Batch | Items | Model class/effort | Exec | Review | Почему |\n'
                '|:--|:--|:--|:--|:--|:--|\n'
                '| B1 | P1.1–P1.2 | implementation/high | run | light | recommended: independent |\n'))
            (plan / 'journal.jsonl').write_text('')
            for item in ('P1.1', 'P1.2'):
                plan_item_state.build_states(plan, item_id=item)
                plan_bundle.build(plan, item)
            for order in (('P1.1',), ('P1.1', 'P1.2')):
                self.assertEqual(task_contract.admit_batch(plan, order)['verdict'], 'ALLOW')
            self.assertEqual(task_contract.admit_batch(plan, ('P1.2', 'P1.1'))['verdict'],
                             'BATCH_REQUIRED')
            closed = terminal_policy.build_decision(plan, 'P1.1', result='closed-green',
                validation=[{'carrier': 'fixture', 'status': 'green', 'evidence_ids': ['test:done']}])
            journal.append(plan, journal.new_entry(plan_id=plan.name, item_id='P1.1', command='plan-run',
                actor='implementation/high', result='closed-green', decision=closed))
            plan_item_state.build_states(plan, item_id='P1.1')
            self.assertEqual(task_contract.admit_batch(plan, 'P1.1')['verdict'], 'BATCH_STALE')
            # An unready typed producer blocks its consumer even if its file exists.
            producer_spec = plan / 'phases/P1/P1.1.md'
            original = producer_spec.read_text()
            producer_spec.write_text(original.replace('**Deliverables:**',
                '**Deliverables:** `producer-readiness/v1`: consumer=P1.2; modes=nonempty-candidates|empty-by-decision.'))
            self.assertEqual(task_contract.admit_batch(plan, 'P1.2')['verdict'], 'BATCH_STALE')
            producer_spec.write_text(original)
            core.write_text(core.read_text().replace('recommended: independent', 'required: atomic'))
            self.assertEqual(task_contract.admit_batch(plan, 'P1.1')['verdict'], 'BATCH_REQUIRED')
            core.write_text(core.read_text().replace('required: atomic', 'historical'))
            self.assertEqual(task_contract.admit_batch(plan, ('P1.2', 'P1.1'))['verdict'], 'BATCH_REQUIRED')
