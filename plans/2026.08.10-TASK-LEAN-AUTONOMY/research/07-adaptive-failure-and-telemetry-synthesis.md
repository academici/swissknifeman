# Adaptive failure handling and lean telemetry synthesis

Дата: 2026-08-11.

## Retrieval и verification

После cross-project telemetry обычный Perplexity Web получил семь узких запросов по
management-by-exception, resilient automation, actionable alerting и risk-based autonomy.
Четыре ответа содержали usable synthesis, три вернули `No answer found`; отсутствие ответа не
трактовалось как внешний факт. Load-bearing claims перепроверены по первичным official pages.
RAG:✅ 2026-08-11.

## Сходящиеся внешние правила

1. Google SRE рекомендует прерывать человека по urgent/actionable symptom, а причины хранить для
   диагностики; частые шумные alert'ы маскируют реальную проблему. Для Task аналогом symptom
   является воспроизведённый impact на current acceptance, а tool error — только cause signal.
2. Azure Retry pattern разделяет cancel, immediate retry и delayed retry, требует учитывать
   idempotency и советует ранние успешно восстановленные failures оставлять informational; only
   final failed attempt становится error. Это прямо поддерживает same-attempt recovery.
3. Azure Circuit Breaker прекращает повтор заведомо failing operation, но позволяет остальной
   системе продолжать/деградировать; для Task breaker keyed by failure fingerprint, не общий
   запрет на прогресс.
4. Kubernetes отделяет readiness (временно не готов/overload, процесс остаётся жив) от liveness
   (доказанная inability to progress). Future carrier, живой PID и временная dependency поэтому
   не должны автоматически становиться terminal product failure.
5. Claude Code официально предоставляет `CLAUDE_CODE_SESSION_ID` в Bash/PowerShell subprocess;
   вместе с `CODEX_THREAD_ID` это позволяет journal использовать observed provider identity, а
   не ручную строку.

## Единая decision table

| Signal class | Minimum evidence | Default action | Terminal? |
|:--|:--|:--|:--|
| `procedural` | wrong cwd/path, literal/note/date/view mismatch, route attestation | deterministic local repair/fallback, one focused rerun, continue same attempt | no |
| `transient` | timeout/temporary unavailable/429-like response; operation proven idempotent | bounded retry with changed timing/strategy and deadline | no |
| `dependency-not-ready` | future carrier absent, readiness false, process still running | wait/poll bounded condition or mark unknown; continue independent work | no |
| `unrelated-pre-existing` | failure exists on baseline or belongs to foreign scope | record exact baseline/delta, continue in-scope work; route follow-up to owner | no |
| `acceptance` | current diff reproducibly violates sealed product/validation contract | stop affected item, keep evidence and exact continuation | yes |
| `safety` | security/privacy/data-loss/unknown non-idempotent write outcome | fail closed; reconcile state before any retry | yes |
| `authority` | public/frozen semantics, irreversible action, missing grant/credential owner decision | owner gate with options/recommendation | yes |

Повтор одного fingerprint после одной изменённой тактики открывает scoped breaker: не продолжать
тот же вызов вслепую, но и не останавливать независимую работу. Один targeted review определяет
`repair-forward`, `degrade/continue`, либо доказанный terminal/no-progress. RAG:✅ 2026-08-11
(Azure Retry/Circuit Breaker; repo calibration in `findings/06-cross-project-execution-telemetry.md`).

## Lean observability contract

- один `session_id` берётся из observed provider environment;
- один deterministic `run_id` связывает start/terminal одного `(plan,item,attempt,session)`;
- report storage canonicalizes to repository git root while retaining actual cwd;
- decision evidence сохраняет `signal_class`, `scope_class`, `fingerprint`, `action` и
  `recovered`; обычный successful fallback не создаёт новый work event;
- повторный close идемпотентен и возвращает существующий terminal pointer;
- `ATTENTION` не сериализуется как `audit-red`;
- missing optional telemetry = coverage gap, не product RED; отсутствие required acceptance
  evidence остаётся RED/ADJUST;
- canary измеряет sessions, audit/retry/route stops, duplicate terminals, join rate и
  same-attempt recoveries, но не строит новую telemetry platform.

## Первичные источники

- Google SRE, *Monitoring Distributed Systems*:
  https://sre.google/sre-book/monitoring-distributed-systems/
- Microsoft Azure Architecture Center, *Retry pattern*:
  https://learn.microsoft.com/en-us/azure/architecture/patterns/retry
- Microsoft Azure Architecture Center, *Circuit Breaker pattern*:
  https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker
- Kubernetes, *Liveness, Readiness, and Startup Probes*:
  https://kubernetes.io/docs/concepts/workloads/pods/probes/
- Anthropic, *Claude Code environment variables*:
  https://code.claude.com/docs/en/env-vars

External ledger reconciliation остаётся owner-owned D9: эти четыре новые load-bearing source
classes добавляются в тот же единичный committed prerequisite, не создавая отдельного gate или
нового audit cycle. Confidence high для exact official behavior; перенос на Task является
явным проектным inference, проверяемым P1.1 regressions и P1.2 field canary.
