# Реопен P4 после RED-аудита — синтез remediation (2026-08-08)

**Слой 2 (авторский синтез).** Стоит на repo-grounded входах:
`phases/P4/P4.md` → `## Audit P4 — 2026-08-08`, `research/06-p4-loop-limiter-design.md`,
frozen `root/contracts/return-loop-v1.md` и `return-judgement-v1.md`, текущем
`packages/task/lib/task/plan_returns.py`, тестах P4 и git-фактах коммитов `f3b21406`,
`8f2cacd2`, `df6d098b`, `22e2dc98`. Внешних факт-классов в решении нет.

## 1. Граница реопена

Аудит дал пять Major-находок, но они образуют одну последовательную remediation-цепочку и не
требуют расфриза трёх контрактов P4:

1. P4.2 возвращает durable identity каждому return event и закрепляет объявленный fixture на
   собственном item tree.
2. P4.4 делает фактический integration write-site `plan_lint_checks/engine.py` частью объявленного
   capsule и добавляет дифференцирующий тест вызова; бессодержательная правка уже правильной строки
   ради попадания пути в новый diff запрещена.
3. P4.6 редуцирует judgement строго по event identity, собирает все event-scoped judgements в owner
   packet, завершает обязательный isolated review согласованным policy state и заново коммитит
   двусоставную acceptance до bookkeeping.

P4.1/P4.3/P4.5 остаются терминальными; их frozen deliverables не меняются. P5/P6,
`packages/artifex`, исторический corpus и baseline не являются remediation-поверхностью.

## 2. Event identity без изменения fingerprint

`return_event_id` уже обязателен в frozen `return-judgement` v1, но reducer его не связывает с
конкретным событием. Для v1 plan-local identity выводится из неизменяемого физического адреса
события: `journal.jsonl:<N>`, где `<N>` — one-based physical line `plan-design` return event.
RAG:— (repo-grounded: `journal.jsonl` append-only; `return-fingerprint-v1.md:20-30` уже признаёт
physical line вторым ключом total order).

Этот id добавляется в history event и в тестовые judgement records, но НЕ входит в
`fingerprint_tuple`, digest input или namespace. Следовательно, frozen grouping identity,
`same_return_max=2` и исторические counts остаются байт-в-байт прежними.

Reducer сканирует immutable carriers в каноническом порядке и группирует schema-valid records по
точному `return_event_id`. Для каждого event действует существующее правило first-valid: первая
schema-valid self-judgement отвергает event и не разрешает поздний retry; запись другого event не
может завершить текущий review. В owner packet входят все принятые event-scoped judgements этого
fingerprint в порядке history events, а policy текущего gate использует только judgement текущего
return event.

## 3. Согласованный policy state после isolated review

Admission и verdict сравниваются при одинаковом `review_completed`, как требует frozen
`return-judgement-v1.md:56-70`. Итоговая матрица:

| Состояние | action | blocks | continue_allowed | stop_required |
|:--|:--|:--|:--|:--|
| required review без валидной записи текущего event | `isolated-review` | `true` | `false` | `false` |
| review завершён, `JUSTIFIED`/`INSUFFICIENT_EVIDENCE`, ниже cap | `return-to-root` | `false` | `true` | `false` |
| review завершён, строгий verdict, ниже cap | `judgement-stop` | `true` | `false` | `true` |
| выше cap при любом verdict | `owner-gate` | `true` | `false` | `true` |

Ни один outcome не может одновременно печатать `blocks=true` и `continue_allowed=true`.
`review_completed` не авторизует continuation выше cap и не меняет count/fingerprint/namespace.

## 4. Evidence и commit boundary

- **P4.2:** item commit обязан содержать реальный diff под
  `packages/task/tests/data/plan-v2/`: три durable return events и event-scoped judgement carriers;
  временная копия внутри unittest не считается Deliverable. D140 остаётся immutable historical
  provenance, а D142 назначает P4.2 владельцем нового remediation fixture; diff `8f2cacd2` сохраняется.
- **P4.4:** `packages/task/lib/task/plan_lint_checks/engine.py` добавляется в `Files`; focused test
  обязан доказать ровно один вызов `plan_gates.lint_return_loop()` через `lint_plan`. Completion
  Notes нового закрытия называют, что старый item commit `8f2cacd2` менял этот путь вне Files.
- **P4.6:** `artifacts/P4/acceptance-report.md` и `historical-detect.json` входят в item commit до
  state/handoff/status bookkeeping. После item commit detached/read-only replay по его hash обязан
  видеть оба файла и выполнять опубликованные команды. Самореферентный hash внутрь acceptance
  artifact не записывается; якорь дерева живёт в P4.6 state/handoff после существования коммита.

Старые journal bytes не переписываются. Append-only `plan-design/in-progress` records реоткрывают
P4.2/P4.4/P4.6; terminal records нового исполнения затем честно фиксируют исход и исторические
deviations. Сгенерированный `P4.closed.md` не правится руками: для live P4 он исключён из live path,
а `plan-close` перегенерирует его после повторной терминальности.

## 5. Почему не новый P4.7

Отдельный P4.7 сохранил бы ложную producer-карту: fixture по-прежнему числился бы Deliverable P4.2,
integration write-site — изменением P4.4, а acceptance — P4.6. Реопен именно этих трёх items оставляет
ownership рядом с исходным ТЗ и даёт append-only state history вместо маскирующего successor-item.

## 6. DoR и остановка

- Три items последовательны: P4.2 производит event ids/fixture; P4.4 фиксирует lint capsule; P4.6
  потребляет оба и выполняет финальную acceptance. Orchestration criterion не срабатывает.
- Каждый item сохраняет существующий маршрут `implementation/high`, `Exec=manual`.
- Маркеров незакрытого уточнения нет; owner choice не требуется; решения полностью следуют audit
  findings и frozen contracts.
- Стоп: focused tests + package validation зелёные, P4.6 item tree содержит acceptance artifacts,
  detached replay проходит, foreign plans read-only, plan-lint не получает новых ERROR/WARN.

## Проверка (verification status)

- RAG: не запускался — все decision-bearing facts repo-grounded чтением контрактов, кода, тестов и
  git trees на 2026-08-08.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: ничего.
- Обходки/[POSSIBLE-DEFECT]: нет; stale `P4.closed.md` сохраняется только как generated historical
  snapshot вне live path и будет заменён штатным `plan-close`.
