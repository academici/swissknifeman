# Research 01 — falsifiable причинная модель

## Итог

Подтверждённый инцидент нельзя честно свести к «мало памяти» или «нужно ещё
больше аудитов». Но `split-brain control plane` пока является рабочей
гипотезой, а не доказанной первопричиной.

```text
owner request + corrections
        │
        ├─ chat / mAInd memory
        ├─ AGENTS / CLAUDE
        ├─ plan / handoff / journal
        ├─ task commands
        └─ duplicated skills / hooks / installed plugins
                         │
       declarative controls не становятся
       единым checked transition contract
                         │
              cold start выбирает stale/ambiguous carrier
                         │
        ┌────────────────┼──────────────────┐
        │                │                  │
 asks approval      premature stop    wrong provider action
        │                │                  │
        └────── per-item restart / audit loop ──────┘
                         │
             context amplification + regressions
```

## Что наблюдается

1. Требования существовали в raw chat и mAInd.
2. Handoff/plan/task/skill при новом старте загружались как параллельные
   instructions.
3. В доступных traces не найден checked conflict-resolved Task Contract,
   применённый перед mutation/final response.
4. Stale exact-next carrier или incidental diagnostic был конкретнее и
   поэтому практически побеждал утверждённый scope.

Это совместимо с провалом retrieval/precedence/application, но P0.1 должен
отделить каждый механизм по selected session traces.

## Controls уже существовали

- `packages/task/commands/plan-audit.md:45-58` с 2026-07-14 уже разделял
  product defect и bookkeeping defect и задавал cap в два phase audits.
- `packages/skiller/skills/general/plan-protocol/SKILL.md:759-768` с
  2026-07-21 уже задавал context boundary и `same-session — item`.
- DUAL-PROVIDER P6 при этом дошёл до пяти audits; потеря launch carrier
  наблюдалась и внутри одной session.

Следовательно, план не должен повторно «изобрести» audit cap или same-session
прозой. Несущая гипотеза: декларативные controls не были compiled/enforced в
transition, pre-mutation, pre-final и public-acceptance points либо runtime
выбирал иной carrier. Какой именно механизм доминировал, не доказано до P0.

## Гипотезы о premature stop

- authority мог не компилироваться в checked task state;
- stale launch carrier мог выигрывать при resolution;
- duplicate command/skill identities могли усиливать ambiguity;
- fragmentation могла повышать частоту carrier reload.

Последние два пункта — усилители-гипотезы. Intra-session failures запрещают
называть fragmentation достаточной причиной.

## Гипотезы о regression loops

- Runtime outcome не соблюдал уже существовавшее declarative различие
  product defect, evidence defect и stale routing.
- Каждый RED мог переоткрыть item/phase, даже если product bytes были green.
- Audit cap существовал в canonical command, но не остановил фактический
  пятый audit; причина enforcement failure пока неизвестна.
- Каждая итерация часто получала fresh context и повторяла старую ошибку,
  но scope drift/забывание наблюдались и внутри одной session: fragmentation
  является усилителем, не единственной причиной.
- Review оптимизировал protocol completeness, а не user contour.
- GREEN мог основываться на внутренних generated artifacts без реального
  consumer/cold-start path.

## Почему имеющейся evidence недостаточно

- Journal почти не заполнял IDs/duration/turns/cost.
- Raw sessions содержали нужные events, но не ingest’ились в item trace.
- Не было fixed regression bank на реальные owner corrections.
- Hash/generator checks проверяли воспроизводимость артефакта, а не
  provider executability или outcome.

## Falsification plan

Гипотеза «просто слабая модель» предсказывала бы независимые ошибки даже при
одном чистом contract. Факты против неё:

- одинаковые требования повторно нарушались разными routed sessions;
- ошибки кластеризуются вокруг handoff/audit/provider carriers;
- durable owner memory присутствовала;
- короткий HONEST-HTTP control plan прошёл существенно чище;
- runtime содержит точные дубли и неверные provider paths.

P0.1 должен для каждого critical case показать: какой carrier был доступен,
какой выбран, какой check исполнился, где transition разошёлся и был ли сбой
intra-session. Если canonical control был выбран и enforced, но outcome всё
равно неверен, control-plane гипотеза ослабляется в пользу capability/contract
quality. Если duplicate removal не меняет paired outcome, duplicate identity
не является causal lever. Если single-session cases падают так же, session
fragmentation остаётся только cost amplifier.

P3 измеряет residual capability отдельно. Аудиты не удаляются: ранние P6
attempts нашли реальный fail-open defect. План добавляет executable
enforcement/conformance вокруг существующих правил, а не дублирует их прозой.
