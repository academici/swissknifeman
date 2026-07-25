# P3 design synthesis — dual skill publication и marketplaces

**Дата:** 2026-07-19

**Основание:** `findings/P3-skiller-publication-recon-2026-07-19.md`,
`research/01-target-architecture-options.md`, `research/02-sequence-and-boundaries.md`,
`research/06-p2-deterministic-artifact-engine-design.md`, draft capability/artifact/config
contracts и owner refinement `brief/01-refinements.md`.

## Целевая граница

P3 вводит package-owned semantic publication catalog над `skills.json` и два независимых
renderer adapter'а: Claude Code и Codex. Catalog описывает skill identity, bucket/core/meta
publication units, source paths, versions, provenance и capability requirements; он не содержит
provider file names или settings keys. Claude renderer сохраняет текущие manifests byte-compatible,
Codex renderer создаёт `.codex-plugin/plugin.json` и `.agents/plugins/marketplace.json` по
first-party contract. Оба используют P2 render/lock/provenance primitives и P1 provider selection.

Предлагаемая package-local раскладка после frozen contracts:

1. `lib/skiller/publication.py` — immutable semantic catalog + Claude/Codex adapter descriptors;
   без I/O discovery, global registration и provider SDK.
2. `registry.py` — scan canonical sources, передача catalog в adapters, write/check generated
   artifacts через P2 engine.
3. `connect.py`/`skillset.py`/`update.py` — provider loop: сначала общий read-only plan всех
   selected providers, затем explicit apply; provider failure не превращается в частично
   записанный «успех».

## Publication modes и ownership

| Mode | Claude Code | Codex | Ownership |
|:--|:--|:--|:--|
| Marketplace catalog | `.claude-plugin/marketplace.json` + per-plugin manifest | `.agents/plugins/marketplace.json` + `.codex-plugin/plugin.json` | generated from one catalog; provider manifests не переводятся друг из друга |
| Direct bucket plugin | canonical bucket root | canonical bucket root | skill content остаётся canonical; только provider manifest generated |
| Curated/discontiguous bundle | Claude advanced marketplace `skills[]` | generated self-contained plugin bundle | bundle derived/provenance-locked; cache не зависит от внешних путей |
| Project-local self-host | existing Claude surface | thin `.agents/skills` adapter, если canonical source есть в repo | adapter не копирует канон |
| Vendor consumer | managed rendered skill copy | managed rendered skill copy under provider target | copy generated/locked; ручная правка = drift, не новый SSOT |
| Plugin install/enable | existing project settings behavior | explicit native install operation after catalog registration | user-global install не выполняется обычным render/update молча |

`skm` является P3-owned management surface: Claude command plugin сохраняется, а Codex получает
skill adapter над тем же skiller CLI intent. Task-команды и их `$ task:…`/`/task:…` invocation
mapping остаются P4; P3 лишь гарантирует, что соответствующий skill/plugin identity может быть
опубликован без копии канонической команды.

## Рассмотренные альтернативы

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| Один semantic catalog + два renderer adapter'а | SSOT, native formats, общий parity set | требует явного contract/versioning | принять |
| Генерировать Codex JSON из Claude marketplace JSON | быстрый старт | Claude fields становятся скрытым каноном; provider gaps теряются | отклонить |
| Поддерживать `.agents/skills` полной ручной копией | сразу видно Codex | второй канон, drift, нарушает AGENTS.md | отклонить |
| Symlink все outputs | минимум bytes | plugin cache/vendor/archive и provider transforms ненадёжны | только optional local dev после contract gate |
| Автоматически ставить Codex plugins при любом update | меньше ручных шагов | меняет user-global state и trust boundary из project command | отклонить; install только explicit |

## Item sequence

P3.1 запечатывает owner-approved skill-publication contract: identities, bundle/version rules,
mode matrix и activation evidence. P3.2 выделяет catalog seam и доказывает byte-compatible Claude
adapter. P3.3 добавляет Codex manifests/marketplace/self-contained curated bundle. P3.4 проводит
оба adapter'а через connect/vendor/install/update/doctor, сохраняя legacy defaults. P3.5 выполняет
exhaustive inventory/parity/idempotence/no-write matrix. Цепочка последовательна через общие files
и deliverables; orchestration criterion не срабатывает.

## Compatibility и fail-closed invariants

- Legacy config без providers даёт только `claude-code`; Codex не включается молча.
- Existing Claude manifest bytes/plugin names/settings keys не меняются без отдельного D# и
  SemVer consequence.
- Один full semantic set сравнивается с каждым provider projection; count-снапшот не хардкодится.
- Unknown capability, corrupt/newer lock, unmanaged target или missing install prerequisite дают
  structured diagnostic; обычный update не усыновляет и не затирает path.
- Dry-run/doctor используют тот же plan, что apply; subprocess/native install отсутствует без
  explicit install action и fake runner в tests.
- `SKILL.ru.md`, evals, upstream service files и foreign provider manifests не попадают в consumer
  bundles, если frozen publication contract явно не разрешает их.

## Pre-mortem P3

| Отказ | Ранний сигнал | Mitigation | Owner/item |
|:--|:--|:--|:--|
| Claude compatibility сломана при refactor registry | diff current marketplace/plugin bytes | pre-refactor golden + byte equality gate | P3.2 |
| Codex plugin cache теряет thin external links | installed bundle ссылается за plugin root | self-contained curated bundle + containment test | P3.3 |
| Inventory parity зелёный на одинаково неполных sets | expected set выведен из renderer output | expected строится из independent semantic catalog/skills.json | P3.5 |
| Update оставляет Claude записанным, Codex красным | apply идёт provider-by-provider без общего plan | preflight all providers + explicit partial-failure diagnostic/repair | P3.4 |
| `~/.codex` меняется обычным project update | subprocess/install action без явного flag | install отдельный explicit action; dry-run no subprocess | P3.4 |
| Bootstrap `.agents/skills` принят за канон | adapter редактируют вместо packages/* source | provenance header + drift gate + P7 self-host regeneration | P3.3/P3.5 |
| P3 зашивает task invocation syntax | task command body/launch mapping появляется в publication | hard Scope Excluded + P4 handoff | P3.1–P3.5 |

## Verification

- Repo-grounding: read-only сверены skiller registry/connect/vendor/skillset/update/install,
  current tests/docs и bootstrap `.agents/skills`; package code не исполнялся.
- External: fresh official Codex manual подтвердил plugin/marketplace/skills paths, cache и native
  install surfaces; источники сохранены в P3 finding и уже каталогизированы в `docs/reference.md`.
- Непроверенное → ПОВТОРНЫЙ ПРОХОД: exact frozen P0–P2 enums/API и P3 contract version ещё не
  существуют; каждый implementation item имеет hard terminal/frozen gate.
- `[POSSIBLE-DEFECT]`: task invocation syntax provider-specific и текущая ChatGPT surface расходится
  с generic manual examples; P4 получает прямое owner refinement, P3 не расширяет scope.
