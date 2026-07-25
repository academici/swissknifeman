# P2 design synthesis — deterministic artifact engine

**Дата:** 2026-07-19

**Основание:** `findings/P2-artifact-engine-recon-2026-07-19.md`,
`research/01-target-architecture-options.md`, `research/02-sequence-and-boundaries.md`,
`research/05-p1-provider-config-domain-design.md`, draft capability/artifact/config contracts.

## Целевая граница

P2 добавляет в flat stdlib-only `core` минимальный artifact kernel. Общий слой знает
stable provider/artifact/capability IDs, canonical bytes, provenance, lock и state
transitions. Он не знает semantic content skills/task/harness/mAInd, provider SDK и CLI.
Owning package передаёт explicit adapter sequence и semantic inputs; later phases сами
решают, какие native files и manifests производить.

Предлагаемая раскладка после frozen contracts:

1. `core/provider_artifact.py` — immutable artifact/render values, canonical bytes/hash,
   provenance envelope и pure render plan.
2. `core/provider_lock.py` — versioned lock, classify/plan/apply/repair primitives с
   explicit target root, containment и atomic writes.
3. `core/provider_registry.py` — explicit immutable catalog над P1 adapter protocols;
   capability gates без import-time discovery.

Три модуля — не framework layers, а плоские cohesive seams. Новый package/subpackage,
template DSL, DI container и provider branches не нужны.

## Рассмотренные альтернативы

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| Общий flat kernel в `core`, adapters в owning packages | одна state/hash semantics; current Rule of Three; dependency direction | требует proposal/ADR и additive public API | принять, D16 |
| Сделать harness центральным generator | reuse agent-packs | skiller/task/maind начинают зависеть от Claude-oriented package | отклонить |
| Оставить отдельные engines по packages | нет shared change | уже три разных lock/drift models; P3–P6 разойдутся ещё сильнее | отклонить |
| Global dynamic registry/import discovery | удобно «подключать» adapters | import-order/non-determinism, service locator, скрытые зависимости | отклонить, D17 |
| Core только pure planning, apply в каждом package | минимальный core I/O | повторит containment/atomic/repair semantics минимум трижды | отклонить; shared apply принимает только explicit root/plan |

## Item sequence

P2.1 проходит package contribution proposal/ADR и создаёт artifact/render/provenance API.
P2.2 на этом API строит lock/state/apply. P2.3 связывает P1 capability domain с explicit
adapter catalog и пишет adapter identity в render/lock. P2.4 доказывает весь contour на
synthetic adapters/TemporaryDirectory. Цепочка строго последовательна; workflow criterion
не срабатывает.

Package integration deliberately deferred:

- P3 — skiller skills/marketplaces/install/update adapters;
- P4 — task command/routing adapters;
- P5 — harness configs/hooks/permissions/MCP adapters;
- P6 — mAInd deployment/analytics consumers.

## Managed-boundary invariants

- Existing target без matching lock/provenance не становится managed автоматически.
- Plan/dry-run/doctor read-only; apply использует ровно тот же immutable plan.
- Local rendered drift и source change — разные states; обычный update не затирает local drift.
- Corrupt/newer lock fail closed; отсутствие lock не эквивалентно разрешению усыновить path.
- Paths target-relative и containment-checked; запись atomic; ordering stable.
- Provenance deterministic и timestamp-free; exact fields/enums приходят только из frozen
  artifact contract, draft placeholder не является API.

## Pre-mortem P2

| Отказ | Ранний сигнал | Mitigation | Owner/item |
|:--|:--|:--|:--|
| Core превращён в provider framework/service locator | import scanning, globals, package imports | proposal/ADR + explicit catalog + import grep | P2.1/P2.3 |
| Dry-run обещает одно, apply делает другое | отдельные render/classify paths | один immutable plan для preview/apply | P2.2/P2.4 |
| Repair затирает user edit | existing path усыновлён по hash или lock missing | unmanaged conflict + no implicit force/adoption | P2.2 |
| Output nondeterministic | timestamp/order/cwd меняет hash | canonical bytes, sorted structures, repeat tests | P2.1/P2.4 |
| Synthetic tests «зелёные», но реальный fleet затронут | target указывает на repo/fleet root | TemporaryDirectory-only + protected before/after snapshot | P2.4 |
| Draft P0 fields зашиты в API | P2 starts before frozen contracts | hard entry gate + D# escalation | P2.1–P2.3 |

## Verification

- Repo-grounding: read-only сверены `core.io/block`, `skiller.skillset`,
  `harness.agentpacks` и `maind health/doctor`; package code не исполнялся.
- mAInd memory использована только для проверки существующего checkpoint и не добавила
  нового load-bearing claim.
- Новых внешних capability/API claims не вводилось; P2 потребляет future-frozen P0/P1
  contracts, поэтому web/RAG повтор не нужен.
- Непроверенное → ПОВТОРНЫЙ ПРОХОД: exact lock/provenance/drift enums всё ещё draft;
  executor обязан читать frozen v1.0.0 и остановиться при несовпадении.
- [POSSIBLE-DEFECT]: P0/P1 спроектированы, но не исполнены; P2 design готов, execution
  остаётся fail-closed. FOREMAN/fleet не читались и не менялись.
