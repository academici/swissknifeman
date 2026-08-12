# Root causes финального RED P1 — 2026-08-11

## Reproduction loop

Минимальный cross-package loop из repository root:

```bash
PYTHONPATH=packages/harness/lib:. python3 -m unittest -v \
  packages.harness.tests.test_review_gate.TestPlanCitationsCheck.test_broken_citation_caught \
  packages.harness.tests.test_run_plan_reader \
  packages.harness.tests.test_run_cli
```

На текущем anchor он стабильно завершается примерно за три секунды пятью failures. Полные Task
и Harness validators остаются final acceptance, но этот loop даёт быстрый red→green feedback.

## Подтверждённые причины

| Finding | Root cause | Owner | Evidence / required correction |
|:--|:--|:--|:--|
| clean-checkout docs-sync | `scripts/docs-sync.sh --check` считает отсутствие gitignored aggregate cache stale output | Task | missing destination должен проверять воспроизводимость сборки и проходить; существующий stale destination обязан падать |
| historical Context enum | `plan-audit.md` и `plan-exec.md` всё ещё печатают значения вне layout-v2 enum | Task | оставить только `continue-root`, `isolated-child-return`, `cold-start-root`; regenerate provider artifacts |
| v2 write-site lint gap | `_parse_phase_v2()` подставляет пустой `Updated`, поэтому forward-only policy пропускает все v2 terminal items | Task | переиспользовать journal-derived item update из `plan_status.status_model()`, добавить red-first v2 test |
| missing phase citations | verifier ловит ImportError resolver'а и возвращает пустой список фаз | Task | resolver unavailable — явная fail-closed diagnostic; phase citation нельзя молча пропускать |
| three Harness routing failures | synthetic v1 plans не несут обязательный `Last Updated`, поэтому Task lint прекращает чтение раньше driver assertions | Harness | исправить fixtures; после одного meta row ожидаемые `ROUTING-INCONSISTENT` и drivable/manual outcomes воспроизводятся |
| citation integration fixture | temp repo копирует verifier, но не `packages/task/lib/task`, создавая не реальный missing-citation case, а resolver absence | Harness | копировать Task runtime для integration path и отдельно проверять fail-closed absence |
| v2 Next ownership | `plan_reader.py` ищет `**Next:**` в `P<n>.<m>.state.md`, хотя v2 item-state имеет ровно пять result fields | Harness | driver/owner boundary читает semantic `handoff.md`; state остаётся schema-pure |
| canary truth gap | P1.2 исключил observed blocked rows и не заполнил обязательные scorecard rows | root evidence | новый P2.3 window классифицирует каждый event и печатает `same_attempt_recovery`/`material_stop_preserved` |

## Falsified hypotheses

- Runtime routing classifier не является причиной трёх Harness outcomes: добавление единственного
  обязательного `Last Updated` восстанавливает ожидаемые результаты без product-code change.
- Broken-citation matcher не является причиной fail-open: перенос Task runtime в temp fixture
  немедленно даёт exit 2 и точную missing citation diagnostic.
- Bundle/status generator не должен добавлять `Next` в item state: это нарушило бы layout-v2
  schema и смешало executor result carrier с owner orchestration carrier.

## Immutable provenance

Material scope drift и ложные terminal claims P1.1/P1.2 остаются findings финального audit и не
переписываются. P2 исправляет продукт и повторяет evidence на новом anchor; P1 journal/state/audit
не используются как зелёное доказательство.
