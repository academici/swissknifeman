# Finding 07 — design audit RED, attempt 1

**Вердикт:** RED. **Дата:** 2026-07-24. **Scope:** pre-exec design.

## Blockers

1. Routing не использовал neutral model class/effort, содержал несуществующий
   `Exec=plan-run` и незакрытые Review values.
2. Roadmap имел неканоническую таблицу и намеренно не содержал готовые
   launch-blocks будущих групп, хотя protocol требует их для каждой
   batch/workflow/solo-группы.
3. `Design Passes: 3/3`, D18 и Update Log выдавали несколько проходов одной
   outcome-session за три fresh passes. Следующим шагом ошибочно был P0.1.
4. RCA называл отсутствующими controls, которые уже существовали:
   `packages/task/commands/plan-audit.md:45-58` с 2026-07-14 разделял
   product/bookkeeping verdict и ограничивал phase audit двумя заходами;
   `packages/skiller/skills/general/plan-protocol/SKILL.md:759-768` с
   2026-07-21 определял context boundary и `same-session — item`.
5. Raw audit и field evidence не имели cold-start source manifest; P0.1 не
   называл exact seven journals, selected session manifest или реальный
   extractor path.
6. Items содержали wildcard/dynamic Files, mixed/invalid RAG markers и
   prose validation без точных commands.
7. P0 менял hook behavior до freeze acceptance/bank.
8. P3 canary не определял disposable worktree, commits, cleanup и rollback.

## Causal correction

Наблюдаемый факт: declarative controls существовали, но DUAL P6 всё равно
дошёл до пяти audits, а stale/missing launch carrier возникал и внутри одной
session. Поэтому рабочая гипотеза для P0/P2:

> Controls не компилировались в один transition/pre-mutation/pre-final
> contract и не имели executable conformance gate. Duplicate identities и
> session fragmentation могли усиливать сбой, но их причинный вклад не
> доказан до selected traces P0.1.

Pass 2 обязан исправить схему и handoff; Pass 3 — свежо проверить coverage,
RAG, routing↔roadmap, exact Files/Validation, Owner gates и DoR. P0 до этого
не исполняется.
