# Индекс — 2026.07.23-FLEET-DUAL-PROVIDER

**Обновлён:** 2026-07-23

## Карта директорий

| Путь | Назначение |
|:--|:--|
| `plan.md` | мастер-план и статусы |
| `phases/` | исполнимые фазы |
| `handoff.md` | rolling-указатель следующего шага |
| `journal.jsonl` | append-only история plan-операций |
| `open-questions.md` | точный Owner Approval tracker для заблокированного P2.2 |
| `brief/` | исходный запрос владельца |
| `findings/` | dry-run evidence |
| `research/` | синтез rollout-механизма |

## Провенанс

| Источник | Слой | Питает | Суть |
|:--|:--|:--|:--|
| `findings/00-fleet-dry-run-2026-07-23.md` | findings | `P0` | наблюдаемый Codex connect blocker и безопасные границы |
| `research/00-rollout-design.md` | research | `P0.1` | последовательность fix-forward rollout |
| `findings/P2.2-rollout.md` | findings | `P2.2` | committed zero D7 apply-set и consumer-owned blocker classes |
| `findings/P2.2-azguard-remediation-diagnosis.md` | findings | `P2.2` | exact preimage и D13 provider-context automation defect |
| `findings/P2-audit-remediation.md` | findings | `P2 terminal` | plan-only reconciliation шести audit evidence/accounting findings |
| `research/02-p2.2-remediation-boundary.md` | research | `P2.2` | exact owner-gated `azguard` diagnosis boundary без consumer access |
