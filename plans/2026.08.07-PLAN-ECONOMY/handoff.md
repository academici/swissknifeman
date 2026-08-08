# HANDOFF — 2026-08-08 — after P4.2

**Next:** manual: implementation/high

## Provider-neutral plan-protocol launch-block

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — manual item |
| Суть | Исполнить D142 remediation P4.4: закрепить declared `engine.py` write-site и дифференцирующий test одного вызова |
| Команда | `—` |

```text
$ task:plan-run 2026.08.07-PLAN-ECONOMY P4.4
РЕЖИМ: remediation по D142, не redesign контракта
ВХОД: phases/P4/P4.md → Audit P4 — 2026-08-08 finding 5; затем phases/P4/P4.4.md и research/21-p4-audit-reopen-2026-08-08.md §1, §4
СКОУП: declared `packages/task/lib/task/plan_lint_checks/engine.py` write-site и дифференцирующий test ровно одного `lint_return_loop()`; без no-op product edit
НЕ ТРОГАТЬ: frozen return-loop/fingerprint contracts, same_return_max=2, journal schema/исторические строки, включение gate, P5/P6, packages/artifex, baseline/corpus ради подгонки 8 != 7
```

## Native Codex launch-block

| Параметр | Значение |
|:--|:--|
| Model | `gpt-5.6-terra` |
| Thinking | `high` |
| Cwd | `/home/vostrikov/projects/packages/swissknifeman` |
| Approval/Sandbox | `-a never -s danger-full-access` |
| Context | `continue (/clear) — manual item` |
| Суть | Исполнить D142 remediation P4.4 после committed P4.2 fixture |

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.07-PLAN-ECONOMY P4.4
РЕЖИМ: remediation по D142, не redesign контракта
ВХОД: phases/P4/P4.md → Audit P4 — 2026-08-08 finding 5; затем phases/P4/P4.4.md и research/21-p4-audit-reopen-2026-08-08.md §1, §4
СКОУП: declared `packages/task/lib/task/plan_lint_checks/engine.py` write-site и дифференцирующий test ровно одного `lint_return_loop()`; без no-op product edit
НЕ ТРОГАТЬ: frozen return-loop/fingerprint contracts, same_return_max=2, journal schema/исторические строки, включение gate, P5/P6, packages/artifex, baseline/corpus ради подгонки 8 != 7'
```

**Done:** P4.2 D142 remediation committed in `48e87961`: history events now expose
plan-local `journal.jsonl:<physical-line>` IDs outside the frozen fingerprint, and the P4.2 item
tree contains durable event-scoped judgement carriers. Focused tests, the 664-test package suite,
and `validate.sh` passed.

**Remaining:** последовательно исполнить P4.4 → P4.6, затем штатно закрыть P4 и повторить audit.
P5/P6 остаются вне remediation scope.

**Sources of truth:** `phases/P4/P4.md` → `Audit P4 — 2026-08-08` ·
`research/21-p4-audit-reopen-2026-08-08.md` · `decisions/D142-p4-audit-reopen.md` ·
`phases/P4/P4.2.md` · `phases/P4/P4.4.md` · `phases/P4/P4.6.md` ·
`root/contracts/return-fingerprint-v1.md` · `root/contracts/return-loop-v1.md` ·
`root/contracts/return-judgement-v1.md`.

**Open risks:** historical baseline intentionally differs from current measurement (baseline has no
`classified_share` and 0 vs 7 over-cap subjects); P4.2 did not change baseline/corpus. Six existing
live-plan lint WARN remain outside D142; `P4.closed.md` is a stale generated historical snapshot and
must be regenerated only by `plan-close` after repeat terminality.
