---
id: D13
date: 2026-08-11
status: accepted
item: P0.1
items: [P0.1, P1.1, P1.2]
supersedes: []
superseded_by: null
actor: repository-owner (accepted via explicit logs/telemetry investigation directive)
model: gpt-5.6-sol/xhigh (semantic plan-audit/research route; effort self-attested)
evidence: RAG:✅ 2026-08-11 findings/06-cross-project-execution-telemetry.md + research/07-adaptive-failure-and-telemetry-synthesis.md
---

## Решение

Lifecycle становится идемпотентным и коррелируемым без нового telemetry platform:

- новые run-report'ы пишутся в repository git root независимо от launch cwd, сохраняя actual
  cwd в payload; non-git fallback остаётся текущий cwd;
- journal start/terminal одного execution используют observed provider `session_id` и один
  deterministic `run_id` для `(plan,item,attempt,session)`; доступные metrics join'ятся по
  identity, а не дублируются заранее как fake values;
- повторный terminal close того же fingerprint не append'ит второй `closed-green`, а возвращает
  pointer на существующий event;
- routing/preflight reject до product work не считается attempt и не мутирует item status;
- `ATTENTION` хранится отдельно от `audit-red`; decision evidence различает signal class,
  scope/delta, fingerprint, действие и recovered/terminal outcome;
- historical journal/run bytes не мигрируются; missing optional telemetry фиксируется как
  coverage gap, но не становится product RED.

P1.2 сравнивает новый path с историческим baseline: sessions/cold starts, audits, retries,
routing stops, duplicate terminals, same-attempt recovery и journal↔run join. Никаких daemon,
database, background supervisor или обязательного workflow-carrier не добавляется.

В существующий единичный D9 committed-ledger prerequisite входят также load-bearing official
URLs этого решения; это не отдельный gate:

- `https://sre.google/sre-book/monitoring-distributed-systems/`
- `https://learn.microsoft.com/en-us/azure/architecture/patterns/retry`
- `https://kubernetes.io/docs/concepts/workloads/pods/probes/`
- `https://code.claude.com/docs/en/env-vars`

## Почему

Agelto и Swiss Knife Man имеют нулевой join journal↔run, пустые `run_id`/duration/turns и raw
reports в 6/8 cwd-dependent directories. Из-за неидемпотентного close reconciliation выглядела
как новая работа. Один identity и root storage дают измеримость без превращения наблюдаемости в
новый control plane. RAG:✅ 2026-08-11 (`findings/06-cross-project-execution-telemetry.md`,
`research/07-adaptive-failure-and-telemetry-synthesis.md`).
