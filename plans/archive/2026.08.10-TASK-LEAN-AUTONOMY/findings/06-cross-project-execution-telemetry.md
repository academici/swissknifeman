# Cross-project execution telemetry — Agelto + Swiss Knife Man

Дата среза: 2026-08-11.

## Покрытие и ограничения

Исследованы все доступные plan-carriers, journal events и локальные run-report'ы двух проектов:

| Проект | Plan coverage | Journal coverage | Run-report coverage |
|:--|:--|:--|:--|
| Agelto (`/home/vostrikov/projects/agelto/agelto`) | 10 carriers: 5 master plans с journal, 2 legacy directory plans, 3 flat historical plans | 775 canonical events | 46 unique JSON в 6 `**/.claude/runs` directories |
| Swiss Knife Man | 21 canonical plans, из них 12 с journal | 1,412 events | 43 unique JSON в 8 `**/.claude/runs` directories |

Run-report'ы игнорируются git и имеют локальную retention: это доступный срез, не полная
история. Запуск из вложенного cwd раскладывал отчёты по package/plan/phase directories; после
архивации Agelto часть отчётов переместилась вместе с планом. Поэтому числа годятся как lower
bound и сравнительная диагностика, но не как billing ledger. RAG:— (repo-local telemetry;
Agelto root указан выше).

## Наблюдаемая цена control plane

| Сигнал | Agelto | Swiss Knife Man | Интерпретация |
|:--|--:|--:|:--|
| audit events | 38: 21 RED, 13 ATTENTION, 4 GREEN | 103: 86 RED, 16 GREEN, 1 escalated | ATTENTION исторически смешивался с `audit-red`; повторные раунды доминируют |
| repeated audit rounds | 18 сверх первого по 10/20 scopes; max 5 | 84/103 audit events по уже аудированному target; ARTIFEX design — 10 | status/ritual, а не новый material trigger, часто запускал новый root |
| blocked | 10, из них 9 routing-only | 33, минимум 23 procedural; 22 routing-only | dispatch/preflight ошибочно менял product status |
| escalated | 39, минимум 7 future/carrier/control-plane cases | 81, минимум 23 carrier/form/protocol cases | producer и готовый diff блокировались несуществующим consumer или формой evidence |
| retry friction | 37 | 119 | повтор часто чинил carrier/route, не продукт |
| duplicate terminal close | 45 лишних close-записей у 29 item/phase pairs | многочисленные reconciliation/backfill; 266 unmatched historical starts | lifecycle неидемпотентен и смешивает work с bookkeeping |
| journal ↔ run join | 0 пересечений session id; 0/775 `run_id`/duration/turns | 0 пересечений; 0/1,412 `run_id`/duration/turns | система не умеет измерить цену собственного stop/retry решения |

Agelto run-report'ы содержат 6,267 turns, `usage.out=5,388,259`, 3,765 tool calls и 134
tool failures в 39/46 sessions; `error_loops=[]` во всех 46. В Swiss Knife Man 43 отчёта
содержат 73 tool failures, но также ноль `error_loops`, `workflow_relaunch` и фактического
`devloop`. Сам факт tool failure поэтому не является terminal outcome: это сырой diagnostic
signal, который нужно связать с diff, process state и acceptance. RAG:— (repo-local
`**/.claude/runs/*.json` aggregate).

## Конкретные причинные кейсы

| Кейс | Что реально произошло | Почему возникла тягомотина | Предотвращение |
|:--|:--|:--|:--|
| Future consumer | Agelto P1.1 был закрыт, затем через 53 секунды escalated из-за 20 ещё не созданных consumer validations (`repo:agelto/plans/2026.08.09-RELEASE-READINESS/journal.jsonl:71-74`) | downstream gate счёл `unavailable` равным RED текущего producer | future/unmaterialized carrier = `dependency-not-ready/unknown`; он не меняет producer status |
| Routing mismatch | Agelto P1.7 получил `blocked`, затем в той же session high-effort продолжился и закрылся (`repo:agelto/plans/2026.08.09-RELEASE-READINESS/journal.jsonl:104-106`); ARTIFEX P2.5 позже признал preflight не execution attempt (`plans/2026.08.03-ARTIFEX-SUPERVISOR/journal.jsonl:62-65`) | dispatch correction записывалась как product failure и увеличивала attempt | route correction происходит до start journal; fingerprint дедуплицируется, item остаётся not-started |
| Проверка процесса | FINAL-ACCEPTANCE объявил Arm B `NOT-RUN`, хотя PID был жив; следующий event дождался того же процесса и получил GREEN (`plans/archive/2026.08.10-PLAN-ECONOMY-FINAL-ACCEPTANCE/journal.jsonl:2-4`) | команда/таймаут был принят за outcome без проверки PID/output/state | перед terminalization сделать bounded reconcile фактического процесса; не запускать retry, пока исход первого запуска неизвестен |
| Literal/carrier mismatch | `green` вместо frozen `ok` вызвал escalation и design cycle (`plans/2026.08.03-ARTIFEX-SUPERVISOR/journal.jsonl:139-141`); note >300 chars дал отдельный цикл (`plans/archive/2026.08.07-PLAN-ECONOMY/journal.jsonl:129-131`) | форма evidence смешалась с product semantics | deterministic local normalization + one rerun в том же attempt; material meaning отдельно |
| Unrelated/pre-existing red | ARTIFEX признал, что unrelated dirty Task lint не был evidence пункта, и продолжил (`plans/2026.08.03-ARTIFEX-SUPERVISOR/journal.jsonl:133`); Agelto L13/Pest5 принимал unchanged baseline и сам чинил три новые проблемы (`repo:agelto/plans/archive/2026.08.01-L13-PEST5.md:638-672`) | общий tree/test status использовался без delta и ownership | gate оценивает in-scope regression относительно baseline; inherited red фиксируется, но не блокирует независимый diff |
| Audit loop | Agelto CRAWL P3 прошёл audit→reopen→close три раза (`repo:agelto/plans/archive/2026.08.06-CRAWL-HARDEN/journal.jsonl:58-72`); текущий LEAN до исполнения уже имел три RED design-audit (`journal.jsonl:2`, `:5`, `:9`) | ATTENTION и bookkeeping не отделялись от material defect; status сам становился trigger | один broad audit, затем только targeted recheck по новому material fingerprint; прежний verdict переиспользуется |
| Duplicate close | Agelto RELEASE P1.1 закрыт пять раз (`repo:agelto/plans/2026.08.09-RELEASE-READINESS/journal.jsonl:71-74`, `:90-100`, `:109-116`) | reconciliation писала новый terminal work event | close идемпотентен: повтор возвращает pointer на существующий terminal event без append |
| Бытовой tool noise | Agelto: 34 permission denies, 21 wrong cwd, 15 oversized reads; Swiss Knife Man: 18 wrong path/cwd, 16 oversized reads, 12 permission denies | любой tool error визуально выглядел как «прогон плохой» | deterministic fallbacks: repo-root resolution, `rg`/pagination, safe alternative; затем проверить acceptance delta |
| Разорванная телеметрия | все journal `run_id`/duration/turns пусты, session ids не join'ятся с run report; raw reports разложены по 6/8 cwd roots | capture path зависит от текущего cwd, а lifecycle writers не используют один identity | новые reports пишутся в git root с сохранением actual cwd; journal start/terminal несут один observed session id и deterministic run id |

## Настоящие стопы, которые сохраняются

Гибкость не означает «всё зелёное». Fail-closed остаются:

- подтверждённый security/data-loss/product-contract defect: Agelto Gemini accounting занизил
  расходы примерно `$12 → $2.30`, а историю нельзя было восстановить
  (`repo:agelto/plans/archive/2026.07.26-EST-TRAIN/phases/P6.md:575-581`);
- frozen acceptance red (`plans/archive/2026.08.07-PLAN-ECONOMY/journal.jsonl:223`, `:238`);
- live-state ownership conflict без безопасного rollback
  (`plans/archive/2026.07.19-DUAL-PROVIDER/journal.jsonl:219`, `:277`);
- secrets/security validation на contaminated upstream
  (`plans/archive/2026.07.31-SKM-LEAN/journal.jsonl:99`);
- exhausted owner grant после real provider nonzero
  (`plans/2026.08.03-ARTIFEX-SUPERVISOR/journal.jsonl:179`);
- необратимое действие с неизвестным outcome, authority change или изменение frozen/public
  acceptance.

## Вывод для этого плана

Нужен не новый supervisor, а короткий цикл `observe → reproduce → classify → act → verify`,
закрытая stop taxonomy, idempotent lifecycle и корреляция уже существующих journal/run-report
carriers. Решения D12/D13 и P0.1/P0.2/P1.1/P1.2 ниже реализуют этот вывод без нового daemon,
database, универсального workflow или миграции historical bytes. RAG:— (синтез evidence выше).
