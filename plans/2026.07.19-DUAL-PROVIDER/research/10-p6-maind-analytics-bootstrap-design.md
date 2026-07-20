# P6 design synthesis — mAInd deployment, neutral analytics и cold restart

**Дата:** 2026-07-19

**Основание:** `brief/00-brief.md`, `brief/01-refinements.md`,
`research/01-target-architecture-options.md`, `research/02-sequence-and-boundaries.md`,
`research/09-p5-harness-provider-surfaces-design.md`, draft
`root/contracts/provider-{capability,config,harness}-contract.md`, D1–D7/D9/D13–D18/
D28–D32 и read-only recon текущих `maind`/`analyst`/`core` seams.

## Текущее состояние и граница P6

`maind.provision.deploy` сейчас сам выбирает Claude/Cursor/VS Code MCP-файлы через
`MCP_FILES`, а `workspace.py`, `health.py`, `sync.py` и `onboard.py` напрямую пишут
`.claude`/`CLAUDE.md`. `analyst.sessions`, `token_report`, `digest`, `lessons` и
`core.runs.find_run_report` так же считают `.claude` источником transcript/run/lesson
storage. Это рабочая Claude compatibility surface, но не provider-neutral contract.
RAG:— (repo-grounded: `packages/maind/lib/maind/{mcpconfig,health}.py`,
`packages/maind/lib/maind/provision/{deploy,sync,onboard,workspace}.py`,
`packages/analyst/lib/analyst/{sessions,token_report,digest,lessons}.py`, `core/runs.py`)

P6 не создаёт второй renderer и не переписывает низкоуровневые provider keys. mAInd
владеет project/provider loop, semantic server inventory, sequencing и provider-tagged
result aggregation; frozen P5 harness adapters владеют target paths, trust/hooks/context
и serialization. Analyst владеет normalized analytics contract/readers, а `core` получает
только минимальный общий lookup/envelope primitive, который нужен и analyst, и maind.
RAG:— (repo-grounded: D2/D14/D17/D28–D31, `research/01-target-architecture-options.md`)

## Deployment alternatives

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| Добавить `codex` в `MCP_FILES` и размножить `if provider` по maind | малый стартовый diff | maind дублирует P5 paths/trust и делает Claude JSON скрытым каноном | отклонить |
| Передать весь project loop в harness | один renderer-владелец | harness начинает владеть fleet selection, memory scope и deploy sequencing | отклонить |
| mAInd loop + semantic inventory, P5 projection registry + P2 artifact plan | сохраняет bounded contexts, native outputs и единый managed-boundary gate | требует provider-tagged results и compatibility shim | принять |

Effective providers вычисляются один раз P1 resolver'ом для operation/project; каждый
provider получает независимый plan/check/apply result. Плоский GREEN запрещён, если любой
required provider завершился `failed`, `unsupported`, `untrusted` или `drift-conflict`.
Existing `--targets` и Claude bytes остаются compatibility adapter, но не участвуют в
semantic provider selection. Full access не выводится из provider presence/defaults.

## Analytics alternatives и рекомендуемый contract

| Вариант | Плюсы | Минусы | Вердикт |
|:--|:--|:--|:--|
| Оставить `.claude` общей схемой и переводить Codex raw events в Claude JSON | минимум consumer-правок | provider raw format становится скрытым общим API; теряется provenance | отклонить |
| Два независимых normalized stores/readers у каждого provider | native ingestion | аналитика и retention расходятся, cross-provider сравнение ненадёжно | отклонить |
| Neutral envelope/store + explicit provider readers + legacy fallback | единая аналитика, raw остаётся локальным, миграция обратима | нужен owner-gated schema и controlled migration | принять как baseline P6.3 |

Рекомендуемый canonical normalized home — `<project>/.swissknife/analytics/`:
`runs/<provider-id>/<session-id>.json`, append-only `events.ndjson`,
`usage-trend.ndjson` и metadata/retention.
Analyst state переезжает в `<project>/.swissknife/analyst/`. Raw transcript/log никогда
не копируется туда: reader пишет только normalized fields и provenance reference/hash,
без raw body и secret values. Старые `.claude/runs`, `.claude/analyze` и `.claude/analyst`
читаются через explicit `legacy-claude-v2` adapter; новые записи идут только в neutral home.
Миграция — copy/verify/idempotent с сохранением legacy source до отдельного cleanup decision.
RAG:— (repo-grounded: `brief/00-brief.md`, current paths above, analyst LOCAL-only/human-gate
in `packages/analyst/CLAUDE.md`)

P6.3 замораживает минимум: schema/version negotiation; stable provider/session/project IDs;
event envelope; normalized run-report; usage/workflow/tool/file/retrieval/devloop/maind slices;
provenance и redaction; raw boundary; storage/retention; reader registry; unknown/corrupt
diagnostics; legacy compatibility/migration; human promotion invariant; golden examples и
Approval Owner. Exact Codex/Claude raw keys не входят в common schema: их P6.4 берёт только
из terminal P5.3/P5.5 projections/fixtures. `[UNVERIFIED]` до этого gate: конкретная форма
будущего Codex transcript/hook payload — P6 её не угадывает.

## Item sequence и session boundary

1. P6.1 вводит provider-aware MCP/deploy plan поверх frozen P1/P2/P5 APIs.
2. P6.2 переводит onboard/sync/workspace/health intents на тот же provider loop.
3. P6.3 owner-gated замораживает analytics contract без package code.
4. P6.4 внедряет neutral store/readers/migration и переводит maind/analyst consumers.
5. P6.5 собирает integrated conformance и durable pre-restart checkpoint.
6. P6.6 выполняется только в новой сессии и доказывает disk+memory cold recovery.

Все items последовательны: каждый потребляет deliverable предыдущего. P6.5 и P6.6
разделены обязательным cold-restart gate; это не autonomous workflow, а явный owner/session
boundary. Поэтому workflow criterion не срабатывает.

## Pre-mortem P6

| Отказ | Ранний сигнал | Mitigation | Owner/item |
|:--|:--|:--|:--|
| Provider loop перезаписывает foreign MCP/settings | repair diff выходит за managed paths | P2 plan/check + user-owned conflict tests + temp targets | P6.1–P6.2 |
| Один provider упал, общий sync заявил GREEN | result не несёт `provider_id` или aggregate скрывает failure | provider-tagged rows + required-provider fail-closed aggregate | P6.1–P6.2 |
| Trust/approval/sandbox снова схлопнулись в `full access` | default/fleet выбирает danger projection | только P5 security intent; explicit trusted operation; negative inheritance cases | P6.2 |
| Analytics contract копирует Claude raw schema | common fields содержат `.claude` event/path names | neutral envelope + named readers + schema grep gate | P6.3–P6.4 |
| Raw transcript/secret попал в shared store | fixture находит prompt/token/env value | allowlisted normalized fields + redaction + raw-reference-only invariant | P6.3–P6.4 |
| Legacy данные потеряны миграцией | move/delete до parity proof | dual-read/single-write, copy+verify, source never deleted in P6 | P6.4 |
| Cold restart «доказан» продолжением старого чата | evidence ссылается на session context | P6.5 checkpoint → отдельный P6.6 cold-start read/recall | P6.5–P6.6 |
| Design/exec задевает FOREMAN или fleet | protected-path delta | temp projects + swissknifeman-only probes; zero delta gate | каждый item |

## Verification

- Repo-grounding: полностью прочитаны package guides; релевантные maind deploy/sync/onboard/
  workspace/health и analyst run/session/trend/lesson consumers просмотрены read-only.
- External: новых capability claims не получено; mAInd recall использован только как
  checkpoint-контекст и не является основанием нового provider API.
- Package code/scripts в design-заходе не исполнялись.
- Непроверенное → ПОВТОРНЫЙ ПРОХОД: exact frozen P1/P2/P5 APIs и raw provider payloads ещё
  не существуют; P6.1–P6.4 держат terminal/frozen entry gates и запрещают guessing.
- `[POSSIBLE-DEFECT]`: current `core/runs.py` и analyst/maind consumers жёстко читают
  `.claude`; current maind trust/health provisioners напрямую пишут Claude surfaces.
  Это предмет P6, а не основание править package code в design-сессии.
