"""Owner-bound admission for one independent repeat of a terminal solo item."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from task import journal, plan_decisions, plan_item_state, plan_layout, plan_readiness

FIELDS = frozenset(('schema_version', 'plan_id', 'item_id', 'command', 'decision_id',
                    'design_fingerprint', 'spec_sha256', 'historical_terminal_sha256',
                    'phase_sha256', 'phase_terminal_heads', 'sibling_spec_hashes',
                    'owner_message_path', 'owner_message_sha256', 'attempt',
                    'session_id', 'run_id'))
TERMINAL = frozenset(('closed-green', 'closed-deviations'))


class RepeatError(ValueError):
    pass


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(record):
    return hashlib.sha256(json.dumps(record, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def _rows(root):
    return journal.read_authoritative_entries(root)


def _heads(root, rows):
    items = {p.stem for phase in plan_layout.phase_paths(root)
             for p in plan_layout.item_spec_paths(root, phase)}
    return {item: event for item in items if (event := plan_item_state.latest_execution_event(
        [row for row in rows if row.get('item_id') == item])) is not None}


def _event_sha(event):
    return digest(event)


def design_witness(plan_dir, record):
    """Authenticate the current execution gate, retaining legacy whole-plan grants."""
    root = Path(plan_dir)
    item = record['item_id']
    plan_readiness.validate_execution_design(root, (item,))
    try:
        whole = plan_readiness.design_snapshot(root)['fingerprint']
    except plan_readiness.ReadinessError:
        whole = None
    if whole == record['design_fingerprint']:
        return {'mode': 'whole-plan', 'fingerprint': whole}
    if not plan_readiness.design_audit_required(root):
        scoped = plan_readiness.design_snapshot(root, phase_ids=(item.split('.')[0],))['fingerprint']
        if scoped == record['design_fingerprint']:
            return {'mode': 'phase-scoped', 'fingerprint': scoped}
    raise RepeatError('REPEAT_DESIGN_STALE: design/spec changed')


def build(plan_dir, item_id, *, decision_id, owner_message_path, session_id,
          command='plan-run'):
    """Draft exact grant bytes; acceptance still requires the owner's decision marker."""
    root = Path(plan_dir)
    plan_readiness.validate_execution_design(root, (item_id,))
    rows = _rows(root)
    heads = _heads(root, rows)
    prior = heads.get(item_id, {})
    phase = item_id.split('.')[0]
    members = list(plan_layout.item_spec_paths(root, phase))
    if prior.get('result') not in TERMINAL or any(
            heads.get(p.stem, {}).get('result') not in TERMINAL for p in members):
        raise RepeatError('REPEAT_TARGET_NOT_TERMINAL: phase and item should be terminal')
    message = root / owner_message_path
    if message.resolve().is_relative_to(root.resolve()) is False or not message.is_file():
        raise RepeatError('REPEAT_OWNER_MESSAGE_INVALID: needed plan-local owner message')
    attempt = prior['attempt'] + 1
    return {'schema_version': 'repeat-admission/v1', 'plan_id': root.name,
            'item_id': item_id, 'command': command, 'decision_id': decision_id,
            'design_fingerprint': plan_readiness.design_snapshot(root, phase_ids=(
                None if plan_readiness.design_audit_required(root) else (phase,)))['fingerprint'],
            'spec_sha256': sha(plan_layout.carrier_path(root, 'item-spec', item_id=item_id)),
            'historical_terminal_sha256': _event_sha(prior),
            'phase_sha256': sha(plan_layout.phase_path(root, phase)),
            'phase_terminal_heads': {p.stem: _event_sha(heads[p.stem]) for p in members},
            'sibling_spec_hashes': {p.stem: sha(p) for p in members if p.stem != item_id},
            'owner_message_path': owner_message_path, 'owner_message_sha256': sha(message),
            'attempt': attempt, 'session_id': session_id,
            'run_id': journal.derive_run_id(plan_id=root.name, item_id=item_id,
                                           attempt=attempt, session_id=session_id)}


def validate(plan_dir, record, *, requested=None, session_id=None, allow_run=None,
             historical=False):
    root = Path(plan_dir)
    if not isinstance(record, dict) or set(record) != FIELDS or record['schema_version'] != 'repeat-admission/v1':
        raise RepeatError('REPEAT_CONTRACT_INVALID: closed schema repeat-admission/v1')
    item = record['item_id']
    if record['plan_id'] != root.name or (requested is not None and tuple(requested) != (item,)):
        raise RepeatError('REPEAT_SCOPE_MISMATCH: only one exact item')
    if session_id is not None and record['session_id'] != session_id:
        raise RepeatError('REPEAT_SESSION_MISMATCH: new grant for another session')
    if (record['command'] not in {'plan-run', 'plan-exec'}
            or not isinstance(record['attempt'], int) or isinstance(record['attempt'], bool)
            or record['attempt'] < 2
            or record['run_id'] != journal.derive_run_id(
                plan_id=root.name, item_id=item, attempt=record['attempt'], session_id=record['session_id'])):
        raise RepeatError('REPEAT_IDENTITY_INVALID: command/attempt/run identity')
    decisions = {d.identifier: d for d in plan_decisions.load_decisions(root)}
    owner = decisions.get(record['decision_id'])
    if (owner is None or owner.status != 'accepted' or owner.superseded_by is not None
            or item not in owner.items or f'[REPEAT-ADMISSION:{digest(record)}]' not in owner.body):
        raise RepeatError('REPEAT_OWNER_GRANT_MISSING: exact accepted owner marker')
    message = root / record['owner_message_path']
    if (not message.resolve().is_relative_to(root.resolve()) or not message.is_file()
            or sha(message) != record['owner_message_sha256']):
        raise RepeatError('REPEAT_OWNER_MESSAGE_STALE: owner provenance changed')
    rows = _rows(root)
    starts = [r for r in rows if (r.get('decision') or {}).get('repeat_admission') == record]
    if historical:
        # Reading a completed run cannot require a new admission for a later
        # authored phase. Authenticate its actual consumed grant and the GREEN
        # that preceded its start; unfinished runs retain current-design gates.
        run_rows = [r for r in rows if r.get('item_id') == item
                    and r.get('run_id') == record['run_id']]
        terminal = plan_item_state.latest_execution_event(run_rows)
        if (len(starts) != 1 or allow_run != record['run_id']
                or starts[0].get('result') != 'in-progress'
                or starts[0].get('run_id') != allow_run
                or terminal is None or terminal.get('result') not in TERMINAL):
            raise RepeatError('REPEAT_HISTORY_UNQUALIFIED: needs completed consumed run')
        witness = (starts[0].get('decision') or {}).get('repeat_design_gate')
        preceding = rows[:rows.index(starts[0])]
        finishes = [i for i, r in enumerate(preceding)
                    if r.get('command') == 'plan-design' and r.get('item_id') == 'finish'
                    and r.get('fingerprint') == record['design_fingerprint']]
        audits = [(i, r) for i, r in enumerate(preceding)
                  if r.get('command') == 'plan-audit' and r.get('item_id') == 'design'
                  and r.get('fingerprint') == record['design_fingerprint']]
        scoped = witness == {'mode': 'phase-scoped', 'fingerprint': record['design_fingerprint']}
        if not scoped and (not finishes or not audits or audits[-1][0] <= finishes[-1]
                           or audits[-1][1].get('result') != 'audit-green'):
            raise RepeatError('REPEAT_HISTORY_DESIGN_UNQUALIFIED: no GREEN to start')
    else:
        design_witness(root, record)
    if sha(plan_layout.carrier_path(root, 'item-spec', item_id=item)) != record['spec_sha256']:
        raise RepeatError('REPEAT_DESIGN_STALE: design/spec changed')
    phase = item.split('.')[0]
    members = list(plan_layout.item_spec_paths(root, phase))
    if (set(record['phase_terminal_heads']) != {p.stem for p in members}
            or record['sibling_spec_hashes'] != {p.stem: sha(p) for p in members if p.stem != item}
            or sha(plan_layout.phase_path(root, phase)) != record['phase_sha256']):
        raise RepeatError('REPEAT_PHASE_STALE: historical phase changed')
    if starts and (allow_run != record['run_id'] or any(r.get('run_id') != allow_run for r in starts)):
        raise RepeatError('REPEAT_ALREADY_CONSUMED: grant already used')
    completed_history = historical
    if starts:
        index = rows.index(starts[0])
        historical = _heads(root, rows[:index])
    else:
        historical = _heads(root, rows)
    if (record['phase_terminal_heads'] != {p.stem: _event_sha(historical.get(p.stem, {})) for p in members}
            or any(historical.get(p.stem, {}).get('result') not in TERMINAL for p in members)
            or _event_sha(historical.get(item, {})) != record['historical_terminal_sha256']
            or historical[item]['attempt'] + 1 != record['attempt']):
        raise RepeatError('REPEAT_HISTORY_STALE: terminal history changed')
    current = _heads(root, rows)
    if not completed_history and any(_event_sha(current.get(p.stem, {})) != record['phase_terminal_heads'][p.stem]
           for p in members if p.stem != item):
        raise RepeatError('REPEAT_SIBLING_STALE: sibling outcome changed')
    return record


def for_run(plan_dir, item_id, run_id):
    rows = [r for r in _rows(plan_dir) if r.get('item_id') == item_id and r.get('run_id') == run_id]
    starts = [r for r in rows if r.get('result') == 'in-progress'
              and (r.get('decision') or {}).get('repeat_admission') is not None]
    if not starts:
        return None
    if len(starts) != 1:
        raise RepeatError('REPEAT_START_AMBIGUOUS: need one durable start')
    record = starts[0]['decision']['repeat_admission']
    event = plan_item_state.latest_execution_event(rows)
    validate(plan_dir, record, requested=[item_id], allow_run=run_id,
             historical=event is not None and event.get('result') in TERMINAL)
    return record


def aggregate_statuses(plan_dir, statuses):
    """Keep historical phase outcomes; item tables still show the current run."""
    root = Path(plan_dir)
    result = dict(statuses)
    if not (root / journal.FILENAME).is_file():
        return result
    # Ordinary and legacy plans keep their existing projection policy. Only
    # the additive repeat carrier requires the strict authoritative reader.
    if '"repeat_admission"' not in (root / journal.FILENAME).read_text():
        return result
    rows = _rows(root)
    heads = _heads(root, rows)
    for item, event in heads.items():
        if item not in result:
            continue
        starts = [row for row in rows if row.get('item_id') == item
                  and row.get('run_id') == event.get('run_id')
                  and (row.get('decision') or {}).get('repeat_admission') is not None]
        if not starts:
            continue
        record = for_run(root, item, event.get('run_id'))
        index = rows.index(starts[0])
        prior = _heads(root, rows[:index])[item]
        result[item] = {'closed-green': '🟢 Done',
                        'closed-deviations': '🟠 Done with deviations'}[prior['result']]
    return result
