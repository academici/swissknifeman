# HANDOFF — 2026-08-09 — after P4.4

**Next:** manual: implementation/high

## Provider-neutral plan-protocol launch-block

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | high |
| Capabilities | — |
| Context | continue (/clear) — manual item |
| Суть | Исполнить D142 remediation P4.6: event-scoped judgement reducer и acceptance из item tree |
| Команда | `—` |

```text
$ task:plan-run 2026.08.07-PLAN-ECONOMY P4.6
РЕЖИМ: remediation по D142, не redesign замороженных контрактов
ВХОД: phases/P4/P4.md → Audit P4 — 2026-08-08; затем phases/P4/P4.6.md и research/21-p4-audit-reopen-2026-08-08.md
СКОУП: current-event judgement selection, полный event-scoped owner packet, непротиворечивая policy matrix и acceptance в committed P4.6 tree
НЕ ТРОГАТЬ: frozen fingerprint tuple/namespace, same_return_max=2, journal schema/исторические строки, P5/P6, packages/artifex, baseline/corpus ради подгонки 8 != 7
```

## Native Codex launch-block

```bash
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-terra -c 'model_reasoning_effort="high"' -a never -s danger-full-access '$ task:plan-run 2026.08.07-PLAN-ECONOMY P4.6
РЕЖИМ: remediation по D142, не redesign замороженных контрактов
ВХОД: phases/P4/P4.md → Audit P4 — 2026-08-08; затем phases/P4/P4.6.md и research/21-p4-audit-reopen-2026-08-08.md
СКОУП: current-event judgement selection, полный event-scoped owner packet, непротиворечивая policy matrix и acceptance в committed P4.6 tree
НЕ ТРОГАТЬ: frozen fingerprint tuple/namespace, same_return_max=2, journal schema/исторические строки, P5/P6, packages/artifex, baseline/corpus ради подгонки 8 != 7'
```

**Done:** P4.4 D142 remediation committed in `2dba3164`: a focused test-double proves that
`engine.lint_plan()` calls `plan_gates.lint_return_loop()` exactly once with the current plan,
layout and diagnostics. The product write-site remains unchanged because it was already correct.

**Remaining:** исполнить P4.6, затем штатно закрыть P4 и повторить audit. P5/P6 остаются вне
remediation scope.

**Sources of truth:** `phases/P4/P4.md` → `Audit P4 — 2026-08-08` ·
`research/21-p4-audit-reopen-2026-08-08.md` · `decisions/D142-p4-audit-reopen.md` ·
`phases/P4/P4.6.md` · `root/contracts/return-fingerprint-v1.md` ·
`root/contracts/return-loop-v1.md` · `root/contracts/return-judgement-v1.md`.

**Open risks:** bare `cd packages/task && python3 -m unittest discover -s tests` lacks the root
`PYTHONPATH` required for `core`; `validate.sh` and discovery with `PYTHONPATH=../..` are green.
Historical baseline intentionally differs from current measurement (0 vs 7 over-cap subjects); no
baseline/corpus changes are permitted. Six live-plan lint WARN remain outside D142.

**Workarounds/Deferred/Open questions:** `—`.
