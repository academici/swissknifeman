# 2026.09.22-№1-TASK-AUDIT-REMEDIATION — План №1 — Перепроверка и устранение дефектов Task trust chain

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.09.22-№1-TASK-AUDIT-REMEDIATION |
| Short ID | PLAN2 |
| Title | План №1 — Перепроверка и устранение дефектов Task trust chain |
| Layout | v2 |
| Document Type | Executable Master Plan |
| Authoring Model | gpt-5.6-sol/high |
| Repository | swissknifeman |
| Related Packages | task · skiller · harness |
| Execution Mode | six serial, separately launched iterations |
| Target Operator Classes | P1/P6: frontier/high; P2–P5: implementation/medium |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| Design Passes | one complete design pass; all P1–P6 items detailed before execution |
| visibility | private |
| Paused By | — |

## 1. Context

Perplexity-аудит `audits/2026-09-22-perplexity.md` заявляет 17 дефектов
N-01…N-17 в Task contract, context transport, owner authority, journal, privacy,
portability, projection durability и CI. Отчёт привязан к текущему `HEAD`
`8ee2f718d130876ef4eb05088a622d594b7bcebd`, но ни его severity, ни предложенные
исправления не считаются доказанными до P1. Каждый claim проходит
три независимые линии: локальный code/reproduction, новый Perplexity-запрос,
обычный web search с открытием первичных источников.

План делит работу на шесть вертикальных итераций: verified baseline;
false-green/context/batch/CI; owner trust/authority; journal/durability;
privacy/portability; затем prompt/docs/policy reconciliation и полевая
проверка. Некодовая правка попадает в кандидат только при цепочке
`воспроизведённый дефект → механизм → изменяемое поведение`; её
эффективность проверяется только на реальных задачах реальных consumer-проектов.

## 2. Execution Rules

- P1–P6 детализированы сразу, но каждая итерация запускается отдельно; successor начинается только после GREEN predecessor evidence.
- P1 не принимает аудит за доказательство: все N-01…N-17 получают `confirmed|partly-confirmed|not-reproduced|superseded` только после local reproduction.
- Для каждого N-ID обязательны Perplexity evidence ID и ordinary-search evidence ID; несущие выводы ссылаются на открытую primary specification/documentation, а не на search snippet или LLM summary.
- Недоступный Perplexity/search — `capability-missing`: P1 не закрывается и не подменяет канал памятью модели.
- P2–P5 изменяют только `confirmed|partly-confirmed` строки verified matrix и не копируют предложенный audit patch без проверки API, threat model и compatibility.
- Каждый security fix доказывает negative path и обычный valid path; test не считается GREEN, если он просто повторяет ту же caller-controlled declaration.
- До наличия provider trust channel owner-gate не называется security boundary. Если provider не может дать недоступную agent principal attestation, режим fail-closed или честная деградация в workflow guard выбирается явно.
- Некодовые prompt/docs/policy changes не получают synthetic benchmark. Структурные lint/tests проверяют только форму; behavioral acceptance дают paired runs реальных задач в изолированных worktree реальных проектов.
- Consumer trees не изменяются: baseline/candidate runs идут в temporary worktrees от pinned commit; ни checkout, ни stash, ни clean в исходных corex/agentools/edufy не допускаются.
- Любая новая public schema/CLI семантика требует compatibility note и миграцию; silent weakening и тестовое ослабление запрещены.
- Existing dirty worktree принадлежит владельцу: исполнитель фиксирует baseline, не откатывает и не перезаписывает unrelated edits, а overlap разрешает по owning item.
- Каждая итерация закрывает focused checks и `bash packages/task/scripts/validate.sh`; P6 добавляет full affected-package/integration checks.
- Release, push, deployment, branch-protection changes и consumer rollout вне scope без отдельного owner action.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| solo | P1.1 | frontier/high | manual | light | recommended: все 17 claims требуют одного repository/Perplexity/web evidence context и security triage; product writes запрещены |
| solo | P2.1 | implementation/medium | plan-exec | light | recommended: bounded false-green/context/batch/CI implementation с конкретными regression tests |
| solo | P3.1 | implementation/medium | plan-exec | light | recommended: implement the smallest honest trust/replay boundary, then test it on the real Agentools task |
| solo | P4.1 | implementation/medium | plan-exec | light | recommended: journal/decision/projection transaction и crash semantics замыкаются в одном package boundary |
| solo | P5.1 | implementation/medium | plan-exec | light | recommended: privacy и portability делят path/containment policy и один bundle gate |
| solo | P6.1 | implementation/medium | plan-exec | light | recommended: reconcile the three already-run project smokes, keep only behaviorally useful changes and close the release contract |

## 5. Decision Log

Каталог решений: `decisions/`; собрать:
`python3 packages/task/scripts/plan-views.py decisions --plan-dir plans/2026.09.22-№1-TASK-AUDIT-REMEDIATION`.
