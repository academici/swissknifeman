# Brief — Slice A: Task phase-close fast path

**Дата:** 2026-08-14
**Источник:** запрос владельца `$ task:design`

Спроектировать исполнимую реализацию Slice A из
`roadmap/2026.08.14-task-phase-close-fast-path.md` внутри `packages/task`:

1. ввести `Phase Assurance | v1` как handwritten phase contract;
2. унифицировать `phase-audit-subject/v1`, сохранив чтение legacy `Pn — режим фазы`;
3. заменить аудит по `Review`/числу items на assurance- и evidence-driven policy;
4. разрешить direct close только доказанно isolated зелёным фазам;
5. штатно закрыть `2026.08.02-PROVIDER-CONTRACT-LOCALE P1`, переиспользовав
   существующий GREEN audit без второго audit и без повтора Validation P1.1–P1.3.

Slice A не вводит `audit-impact/v1`, diff/dependency graph, `validation-receipt/v2`,
repeat-full budget или новый product scope для целевой P1.
