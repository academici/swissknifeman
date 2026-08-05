# P5 last-pass generation gate and execution cadence

## Источники

- `brief/22-p5-last-pass-fast-track.md` — владелец завершает routine design-loop и требует
  сначала исполнить все P5 items, затем анализировать фазу целиком.
- `findings/P5.1-terminal-validator-conflict-2026-08-05.md` — воспроизводимый stale literal
  исторического P4.8 leaf-validator.
- `artifacts/P5/business-grant-request-v1.json` — уже замороженный конечный 14-dispatch request.

## Синтез

P5 не должен повторно оценивать terminal snapshot как current-tree contract. Для каждого
предшественника применяется один режим:

1. historical leaf — воспроизводится на owning commit;
2. current successor — проверяется на текущем tree;
3. P5 consumer — пинит current successor hash и отказывает на drift.

Для P4.8 owning snapshot — `124df816`; для текущего P5 consumer — G2 assurance,
provenance self-test, terminal P4 status/deviation carriers и exact package digest. Это тот же
generation-aware принцип, который план уже применяет к G1/G2 и P1.6/P3 successor evidence.

Скорость достигается не снятием gate'ов, а устранением повторов: P5.1 закрывает generation
reconcile и materializes все 14 owner-bound admissions; P5.2/P5.3 запускают только свой
predecessor/current-surface fan-in; P5.4 один раз выполняет полный фазовый fan-in и readiness
adjudication. Между P5 items нет design/audit checkpoint. RAG:— (repo-grounded: D81/D89/D99,
`roadmap.md`, P5 producer chain).
