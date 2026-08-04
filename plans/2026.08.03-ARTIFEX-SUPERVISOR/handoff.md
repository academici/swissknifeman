# HANDOFF — 2026-08-04 — after P2.1

**Next:** design-item: task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P2.1

| Параметр | Значение |
|:--|:--|
| Model | frontier |
| Thinking | high — frozen contract/interface reconciliation |
| Context | NEW SESSION — шаг-не-item |
| Суть | Разрешить процессные границы P2.1 без Markdown-парсера или второго status carrier. |
| Команда | `task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P2.1` |

**Done:** 2026.08.03-ARTIFEX-SUPERVISOR P2.1 is `🔴 Blocked` before candidate-artifact writes.
The terminal P0/P1 validator fan-in and Task Contract pre-mutation gate are green, but the
required process-bound source projections cannot materialize a conforming allow manifest.

**Remaining:** P2.1 needs a D#-backed design repair before P2.2–P6.4. Do not start successor
items while P2.1 remains blocked.

**Sources of truth:** `phases/P2.md` P2.1 escalation; `root/contracts/slice-manifest-v1.md`;
`artifacts/P1/slice-manifest-cases-v1.json`; `packages/harness/lib/harness/run/plan_reader.py`;
`packages/task/lib/task/task_contract.py`; live `harness run ... P2 --dry-run --json` output.

**Open risks:** (1) `slice-manifest-v1` requires non-empty ordered `scope.files`, but
`task.task_contract build` exports neither files nor a structured validation list; copying or
re-parsing them would violate P2.1. (2) the handoff's legacy `ЗАПУСК ВРУЧНУЮ` form causes Harness
to return `NEXT-FORM-UNSUPPORTED`, so P2.1 cannot cross-check live item route/Exec. (3) source
versions are absent from the Harness dry-run envelope. The existing Codex hook `stale-source`
warning remains deferred to P4.4.

**Workarounds/Deferred/Open questions:**

- workarounds: none — a fixture-only compiler would not satisfy the required live-process boundary;
- deferred: plan-design must decide the owner and versioned public projections, then update frozen
  contracts only through their declared D#/SemVer path;
- open_questions: whether Task Contract gains an additive scope carrier, Harness gains a bounded
  source projection, or P2.1's frozen consumer contract is revised.

```text
codex -C /home/vostrikov/projects/packages/swissknifeman -m gpt-5.6-sol -c model_reasoning_effort="high" -a never -s danger-full-access

$ task:plan-design 2026.08.03-ARTIFEX-SUPERVISOR P2.1

РЕЖИМ: design remediation for blocked P2.1; do not implement P2.1/P2.2
ВХОД: plans/2026.08.03-ARTIFEX-SUPERVISOR/phases/P2.md P2.1; handoff.md; frozen slice-manifest-v1 contract/cases; Task Contract and Harness public process boundaries
СКОУП: add a D# and reconcile the minimal process-bound, versioned source projection needed for route/Exec and ordered scope/files/validation; preserve no-Markdown-parser/no-second-status-carrier and frozen-contract governance
НЕ ТРОГАТЬ: P2.2–P6.4; candidate implementation; package/root CLI promotion; unrelated dirty worktree; hook repair
```
