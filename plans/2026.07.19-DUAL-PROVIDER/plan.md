# 2026.07.19-DUAL-PROVIDER — Claude Code + Codex provider-neutral ecosystem

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.19-DUAL-PROVIDER |
| Title | Dual-provider foundation: общий канон и нативные adapters для Claude Code и Codex |
| Version | 1.3.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | Codex gpt-5.6-sol/high |
| Last Updated | 2026-07-20 |
| Repository | swissknifeman |
| Related Packages | core, skiller, task, harness, maind, analyst |
| Execution Mode | phase-first · contract-first design |
| Target Operator Models | GPT-5.6 Terra/medium implementation floor · Terra/high for prescribed contracts/security · GPT-5.6 Sol/high–xhigh design/audit |
| Approval Owner | Dmitry Vostrikov |
| Home | repo:/home/vostrikov/projects/packages/swissknifeman |
| Paused By | — |
| Design Passes | 3/3 — ecosystem core, 8 фаз/40 items, публичные contracts и высокий cross-package coupling; post-exec prerequisite remediation добавила P0.5 без переписывания terminal P0.1 |

## 1. Context

Swissknifeman сейчас публикует skills, task-команды, harness-конфиги, MCP и аналитику
преимущественно через Claude Code surfaces. Владелец хочет одинаково полно работать в
Claude Code и ChatGPT/Codex, сохранив единый semantic source и используя нативные функции
каждого провайдера. RAG:— (repo-grounded: `findings/repository-baseline-2026-07-19.md`)
показывает шесть связанных package seams и 25 downstream projects. RAG:✅ 2026-07-19
(`findings/provider-capabilities-2026-07-19.md`) подтверждает, что оба provider'а имеют
skills/plugins/hooks/MCP, но разные форматы, trust и permission semantics. План сначала
запечатывает capability/artifact contracts, затем providerizes delivery surfaces и
самохостит swissknifeman. FOREMAN остаётся paused до release gate P7.4; массовый fleet
rollout выполняется отдельной волной после FOREMAN.
Owner refinement после RED-аудита: root и package-level `AGENTS.md` являются
семантическими Codex-аналогами `CLAUDE.md`; оба provider-представления строятся из
одного common instruction canon с явно отделёнными provider extensions.

## 2. Execution Rules

- Полный протокол — `plan-protocol`; один item за раз, phase-first, статусы синхронно.
- Все P0–P7 детализированы до DoR; exec запрещён до GREEN `/task:plan-audit <ID> design`.
- Contract-first: P0 запечатывает capability/artifact contracts до package implementation.
- Provider-specific outputs — adapters над общим contract; ручной dual maintenance запрещён.
- Root/package `CLAUDE.md` и `AGENTS.md` — managed projections одного common instruction
  contract; common semantic IDs паритетны, provider-specific extensions явны и не отменяют common rules.
- Claude Code compatibility является hard gate; существующие `.claude*`, `CLAUDE.md` и команды не удалять.
- `.agents/skills` — thin adapters; canonical content не переносить из skiller/task.
- Python changes stdlib-only; новые runtime dependencies требуют отдельного owner decision.
- Внешние capability claims — только current first-party sources; upstream README не заменяет verification.
- Generated artifacts обязаны нести provenance/hash и проверяться drift-gate до массовой записи.
- Security/permission profiles fail closed; full-access доступен только как явно выбранный provider-native профиль.
- До P7.4 не исполнять `plans/2026.07.18-FOREMAN` и не менять fleet projects массово.
- Посторонние пользовательские изменения в dirty worktree сохранять и не включать в plan commits.
- План разошёлся с кодом/контрактом → не импровизировать, эскалировать через plan-design.
- После каждого item/фазы обновлять handoff и journal; после bootstrap boundary сохранять mAInd checkpoint.
- Required Reads конечны и упорядочены: path либо существует до старта item, либо является Deliverable более раннего item; догадки по repo запрещены.

## 3. Routing

| Items | Model/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|
| P0.1 | gpt-5.6-terra/medium | plan-exec | full | deterministic repo inventory с check-mode; top-tier design decisions отсутствуют |
| P0.5 | gpt-5.6-terra/medium | plan-exec | full | deterministic correction scan пяти explicit roots; semantic owner freeze остаётся в P0.2 |
| P0.2 | gpt-5.6-sol/high | manual | full | cross-package ubiquitous language и owner-approved capability semantics |
| P0.3 | gpt-5.6-sol/xhigh | manual | full | load-bearing frozen public contracts + ADR; необратимая цена semantic ошибки |
| P0.4 | gpt-5.6-sol/high | manual | full | ecosystem migration/FOREMAN/fleet gate contract и pre-mortem reconciliation |
| P1.1 | gpt-5.6-sol/xhigh | manual | full | freeze публичного provider-config contract: необратимая semantic цена ошибки; effort high+ MANDATORY |
| P1.2 | gpt-5.6-terra/high | manual | full | prescribed public core API против frozen contracts; effort high+ MANDATORY |
| P1.3 | gpt-5.6-terra/high | manual | full | cross-package precedence/provenance/diagnostics; effort high+ MANDATORY |
| P1.4 | gpt-5.6-terra/medium | plan-exec | full | deterministic compatibility fixtures и no-write evidence без открытых design-решений |
| P2.1 | gpt-5.6-terra/high | manual | full | prescribed additive shared `core` API против frozen artifact contract; effort high+ MANDATORY |
| P2.2 | gpt-5.6-terra/high | manual | full | managed-boundary/repair semantics с риском чужих файлов; effort high+ MANDATORY |
| P2.3 | gpt-5.6-sol/high | manual | full | explicit capability-aware catalog: открытое public design decision |
| P2.4 | gpt-5.6-terra/medium | plan-exec | full | deterministic synthetic conformance/doctor/no-write evidence без новых design-решений |
| P3.1 | gpt-5.6-sol/high | manual | full | owner-gated public skill/publication contract и необратимые identity/install semantics |
| P3.2 | gpt-5.6-terra/medium | plan-exec | full | prescribed Claude adapter refactor с byte-compat golden и без новых design-решений |
| P3.3 | gpt-5.6-terra/high | manual | full | новый native Codex plugin/marketplace contract + cache-contained generated bundles; effort high+ MANDATORY |
| P3.4 | gpt-5.6-terra/high | manual | full | cross-channel ownership, explicit native install и partial-failure/repair semantics; effort high+ MANDATORY |
| P3.5 | gpt-5.6-terra/medium | plan-exec | full | deterministic independent inventory/parity/no-write conformance без новых design-решений |
| P4.1 | gpt-5.6-sol/xhigh | manual | full | freeze публичного command/routing contract: необратимая semantic цена ошибки; effort high+ MANDATORY |
| P4.2 | gpt-5.6-terra/high | manual | full | новый native Codex adapter/catalog против frozen contract и P3 publication API; effort high+ MANDATORY |
| P4.3 | gpt-5.6-terra/medium | plan-exec | full | deterministic Claude byte/literal compatibility projection без открытых design-решений |
| P4.4 | gpt-5.6-sol/high | manual | full | canon-the-fleet-follows: neutral plan routing/Next/orchestration и provider invocation semantics |
| P4.5 | gpt-5.6-terra/medium | plan-exec | full | independent inventory/parity/no-write conformance и generated operator docs |
| P5.1 | gpt-5.6-sol/high | manual | full | public harness/security contract и owner-gated provider boundary |
| P5.2 | gpt-5.6-terra/high | manual | full | prescribed shared catalog + security projections против frozen contract; effort high+ MANDATORY |
| P5.3 | gpt-5.6-terra/high | manual | full | provider-native lifecycle/trust/context activation; effort high+ MANDATORY |
| P5.4 | gpt-5.6-terra/high | manual | full | protected MCP/agent-pack projection и provenance/lock compatibility; effort high+ MANDATORY |
| P5.5 | gpt-5.6-terra/medium | plan-exec | full | independent deterministic parity/doctor/docs gate без открытых design-решений |
| P5.6 | gpt-5.6-sol/xhigh | manual | full | freeze публичного common instruction contract и semantic parity/managed-boundary semantics |
| P5.7 | gpt-5.6-terra/high | manual | full | prescribed root/package catalog+renderer+provenance implementation против frozen P5.6; effort high+ MANDATORY |
| P6.1 | gpt-5.6-terra/high | manual | full | provider deploy/managed-boundary integration против frozen P1/P2/P5 contracts; effort high+ MANDATORY |
| P6.2 | gpt-5.6-terra/high | manual | full | trust/security + cross-package onboard/sync orchestration; effort high+ MANDATORY |
| P6.3 | gpt-5.6-sol/xhigh | manual | full | owner-gated public analytics contract: открытый storage/reader/migration freeze с необратимой semantic ценой |
| P6.4 | gpt-5.6-terra/high | manual | full | prescribed multi-package readers/storage migration против frozen P6.3 contract; effort high+ MANDATORY |
| P6.5 | gpt-5.6-terra/medium | plan-exec | full | deterministic integrated conformance и pre-restart checkpoint без новых design-решений |
| P6.6 | gpt-5.6-terra/medium | plan-exec | full | deterministic cold-session proof по committed checkpoint; package source changes запрещены |
| P7.1 | gpt-5.6-terra/medium | plan-exec | full | deterministic generated docs/exact-set gate против frozen catalogs |
| P7.2 | gpt-5.6-terra/high | manual | full | live self-host install/update/repair с rollback и security gates; effort high+ MANDATORY |
| P7.3 | gpt-5.6-terra/high | manual | full | provenance-backed destructive cleanup/release assembly; effort high+ MANDATORY |
| P7.4 | gpt-5.6-sol/xhigh | manual | full | adversarial release verdict и owner-gated FOREMAN reconcile |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P0 | Evidence, vocabulary и запечатанные provider contracts | 3/5 | 🟡 In progress |
| P1 | Provider config/domain и backward-compatible resolution | 0/4 | ⬜ Not started |
| P2 | Deterministic adapters, provenance, lock и drift engine | 0/4 | ⬜ Not started |
| P3 | Dual skills publication и marketplaces | 0/5 | ⬜ Not started |
| P4 | Task-command parity и provider-neutral model routing | 0/5 | ⬜ Not started |
| P5 | Harness: permissions, hooks, MCP, native features и instruction projections | 0/7 | ⬜ Not started |
| P6 | mAInd deployment, memory и provider-neutral analytics | 0/6 | ⬜ Not started |
| P7 | Docs, self-hosting validation и FOREMAN release gate | 0/4 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-19 | Первая поддерживаемая матрица — `claude-code` + `codex`; provider IDs внутренние и стабильные. | RAG:— (repo-grounded: `brief/00-brief.md`) — это явная цель владельца; aliases/UI names не должны проникать в contracts. |
| D2 | 2026-07-19 | Архитектура — canonical semantic source + deterministic provider adapters; symlink только optional dev mode. | RAG:— (repo-grounded: `research/01-target-architecture-options.md`) — сохраняет SSOT и допускает нативные transformations. |
| D3 | 2026-07-19 | Capability manifest является источником README matrix, adapter gates и diagnostics. | RAG:— (repo-grounded: `research/01-target-architecture-options.md`) — запрещает отдельную ручную таблицу, которая дрейфует. |
| D4 | 2026-07-19 | Codex command parity реализуется thin skills/adapters над `packages/task/commands`, не deprecated custom prompts. | RAG:✅ 2026-07-19 (`findings/provider-capabilities-2026-07-19.md`) — текущая Codex surface рекомендует skills. |
| D5 | 2026-07-19 | Provider-native возможности описываются extensions/capabilities и не выравниваются до lowest common denominator. | RAG:✅ 2026-07-19 (`findings/provider-capabilities-2026-07-19.md`) — hooks/trust/permission/package semantics различаются. |
| D6 | 2026-07-19 | Migration self-hosts только swissknifeman; fleet rollout остаётся отдельной волной после FOREMAN. | RAG:— (repo-grounded: `research/02-sequence-and-boundaries.md`) — ограничивает blast radius и сохраняет заданную последовательность. |
| D7 | 2026-07-19 | FOREMAN paused на текущем checkpoint до P7.4; он потребит provider execution contract после migration audit. | RAG:— (repo-grounded: `AGENTS.md`, `brief/00-brief.md`) — hard sequencing gate владельца. |
| D8 | 2026-07-19 | Design budget — 3 прохода; этот проход создаёт evidence, contracts placeholders и 34 item skeletons. | RAG:— (repo-grounded: `research/02-sequence-and-boundaries.md`) — ecosystem core/high uncertainty по plan-protocol. |
| D9 | 2026-07-19 | Coupling hotspots: provider IDs/capabilities, precedence, artifact provenance, command routing и analytics schema; менять их только через P0/P1 contracts и D-log. | RAG:— (repo-grounded: `findings/repository-baseline-2026-07-19.md`) — эти поверхности потребляют минимум две фазы. |
| D10 | 2026-07-19 | P0 исполняется строго P0.1→P0.2→P0.3→P0.4 без workflow orchestration. | RAG:— (repo-grounded: `research/03-p0-design-and-premortem.md`) — каждый следующий item потребляет deliverables предыдущего; параллелизм создал бы гонку при contract freeze. |
| D11 | 2026-07-19 | Уточнение D7 (supersedes формулировку «provider execution contract»): FOREMAN после P7.4 потребляет bundle P0 capability/artifact/migration-gate contracts + P4 command/routing contract + P7 release evidence; P0 не замораживает будущий P4 contract. | RAG:— (repo-grounded: `research/03-p0-design-and-premortem.md`) — устраняет undefined contract без преждевременного решения P4. |
| D12 | 2026-07-19 | `frozen` contracts и migration gates требуют явного Approval Owner D#; текущий Codex bootstrap не является release evidence, FOREMAN/fleet остаются fail-closed. | RAG:— (repo-grounded: `brief/00-brief.md`, `research/03-p0-design-and-premortem.md`) — pre-mortem выявил bootstrap-as-release как главный blast-radius риск. |
| D13 | 2026-07-19 | Provider config precedence: operation override → project `.swissknife.json` → fleet `projects[].providers` → fleet `providers.defaults` → legacy implicit `claude-code`; missing ≠ explicit disable. | RAG:— (repo-grounded: `research/05-p1-provider-config-domain-design.md`, `packages/skiller/lib/skiller/{config,update}.py`) — сохраняет project ownership и существующий flags/project/fleet precedence без молчаливой fleet-подмены. |
| D14 | 2026-07-19 | `core` владеет immutable provider domain + pure resolver/diagnostics; `skiller` и `maind` сохраняют file I/O/schema ownership своих carriers, provider renderers остаются downstream adapters. | RAG:— (repo-grounded: `research/01-target-architecture-options.md`, `research/05-p1-provider-config-domain-design.md`, `core/__init__.py`) — единая semantics без service-locator/I/O rebloat общего пакета. |
| D15 | 2026-07-19 | P1 исполняется строго P1.1→P1.2→P1.3→P1.4 после terminal P0.3/P0.4; workflow orchestration не создаётся. | RAG:— (repo-grounded: `phases/P1.md`, `research/05-p1-provider-config-domain-design.md`) — каждый item потребляет frozen contract/API/evidence предыдущего и не является независимым scope. |
| D16 | 2026-07-19 | P2 создаёт minimal flat artifact kernel в `core` через proposal/ADR gate; package-specific semantic adapters и CLI остаются P3–P6. | RAG:— (repo-grounded: `findings/P2-artifact-engine-recon-2026-07-19.md`, `research/06-p2-deterministic-artifact-engine-design.md`) — `skiller`, `harness` и `maind` уже дают три current consumers, но dependency direction запрещает сделать один из них центральным generator. |
| D17 | 2026-07-19 | Adapter registry — explicit immutable catalog, собранный caller'ом; global registration, import/filesystem discovery и provider-name branching запрещены. | RAG:— (repo-grounded: `research/06-p2-deterministic-artifact-engine-design.md`, D3/D5/D14) — capability contract остаётся единственным gate, а output не зависит от import order/environment. |
| D18 | 2026-07-19 | P2 исполняется строго P2.1→P2.2→P2.3→P2.4 после terminal/frozen P0–P1 gate; workflow orchestration не создаётся. | RAG:— (repo-grounded: `phases/P2.md`, `research/06-p2-deterministic-artifact-engine-design.md`) — каждый item потребляет API/evidence предыдущего и не имеет независимого scope. |
| D19 | 2026-07-19 | В текущих ChatGPT/Codex launch-block'ах task workflow вызывается как `$ task:…` с пробелом после `$`; semantic command ID сохраняется, долговечный mapping проектирует P4. | RAG:— (owner-grounded: `brief/01-refinements.md`) — Claude-форма `/task:…` в текущей surface даёт «команда не найдена». |
| D20 | 2026-07-19 | P3 вводит frozen `provider-skill-publication-contract`: один semantic catalog; direct plugin читает канон, self-host adapter thin, vendor/cache bundle является generated locked copy, а не новым SSOT. | RAG:— (repo-grounded: `AGENTS.md`, `research/07-p3-dual-skill-publication-design.md`) — mode-specific ownership сохраняет канон и допускает изолированный plugin cache. |
| D21 | 2026-07-19 | Claude и Codex manifests рендерятся независимо из semantic catalog; перевод одного provider JSON в другой запрещён. Claude output/name/settings остаются byte-compatible gate. | RAG:— (repo-grounded: `findings/P3-skiller-publication-recon-2026-07-19.md`, D2/D3) — provider format не становится скрытым каноном и existing consumers не ломаются. |
| D22 | 2026-07-19 | Codex repo catalog — `.agents/plugins/marketplace.json`, plugin manifest — `.codex-plugin/plugin.json`; project render и user-global native install являются разными operations, install только explicit. | RAG:✅ 2026-07-19 (`findings/P3-skiller-publication-recon-2026-07-19.md`) — current first-party manual отделяет marketplace discovery, cached installation и enabled state. |
| D23 | 2026-07-19 | P3 исполняется строго P3.1→P3.2→P3.3→P3.4→P3.5 после terminal/frozen P0–P2 gate; workflow orchestration не создаётся. | RAG:— (repo-grounded: `phases/P3.md`, `research/07-p3-dual-skill-publication-design.md`) — items последовательно меняют общий publication seam; независимых deterministic scopes меньше трёх. |
| D24 | 2026-07-19 | P4 вводит frozen `provider-command-routing-contract`: stable command IDs, semantic metadata, neutral model classes/effort/capabilities и provider invocation/mapping projections. | RAG:— (repo-grounded: `research/08-p4-task-command-routing-design.md`, D4/D19) — общий workflow contract не должен зависеть от Claude model names или UI prefix. |
| D25 | 2026-07-19 | Routing vocabulary — `economy < implementation < frontier` с независимой `low < medium < high < xhigh` effort axis; provider mapping explicit/versioned, unknown/ambiguous/undershoot fail closed. | RAG:— (repo-grounded: `research/08-p4-task-command-routing-design.md`, plan-protocol §9) — стабильная semantic ось допускает native selectors без молчаливого downgrade. |
| D26 | 2026-07-19 | Canonical command bodies остаются в `packages/task/commands`; Claude slash commands и Codex `$ task:…` skills являются независимыми deterministic projections одного catalog, bootstrap `.agents/skills` не канон. | RAG:— (repo-grounded: `AGENTS.md`, `brief/00-brief.md`, `brief/01-refinements.md`) — сохраняет Claude compatibility и owner-observed Codex invocation без второго ручного command tree. |
| D27 | 2026-07-19 | P4 исполняется строго P4.1→P4.2→P4.3→P4.4→P4.5 после terminal/frozen P0–P3 gate; workflow orchestration не создаётся. | RAG:— (repo-grounded: `phases/P4.md`, `research/08-p4-task-command-routing-design.md`) — items последовательно меняют общий command/routing/golden seam и потребляют результат предыдущего. |
| D28 | 2026-07-19 | P5 вводит frozen `provider-harness-contract`: semantic profile/surface catalog + explicit Claude/Codex projections; `configs/claude-code` перестаёт быть скрытым общим contract, но сохраняется named compatibility surface. | RAG:— (repo-grounded: `findings/P5-harness-recon-2026-07-19.md`, `research/09-p5-harness-provider-surfaces-design.md`) — общий intent не должен копировать provider paths/events, а Claude behavior нельзя ломать. |
| D29 | 2026-07-19 | Security intent разделяет approval, sandbox и trust; workspace-contained autonomy fail-closed, а full access доступен только explicit trusted operation и не наследуется через defaults/project/fleet. | RAG:✅ 2026-07-19 (`findings/provider-capabilities-2026-07-19.md`) — отсутствие approval prompts не расширяет sandbox; implicit danger fallback нарушил бы цель владельца о безопасных профилях. |
| D30 | 2026-07-19 | Common lifecycle catalog хранит intent/capability/support state; hook event, matcher, payload, activation layer и context carrier принадлежат provider projection, unsupported не эмулируется молча. | RAG:— (repo-grounded: `research/09-p5-harness-provider-surfaces-design.md`, D5) — native hook/trust semantics различаются и lowest-common emulation создаёт ложный parity. |
| D31 | 2026-07-19 | MCP/agents/agent-packs получают common semantic identity/content requirements и независимые provider projections; secrets остаются references, а current provenance/lock/upgrade/user-owned semantics обязательны для обоих outputs. | RAG:— (repo-grounded: `packages/harness/lib/harness/{mcp,agentpacks}.py`, `research/09-p5-harness-provider-surfaces-design.md`) — второй ручной manifest tree потерял бы drift/repair и мог утечь secret value. |
| D32 | 2026-07-19 | P5 исполняется строго P5.1→P5.2→P5.3→P5.4→P5.5 после terminal/frozen P0–P4 gate; workflow orchestration не создаётся. | RAG:— (repo-grounded: `phases/P5.md`, `research/09-p5-harness-provider-surfaces-design.md`) — items последовательно меняют один profile/catalog/render/managed-boundary seam и потребляют результат предыдущего. |
| D33 | 2026-07-19 | mAInd владеет effective-provider project loop, semantic server inventory и provider-tagged aggregation; target paths/serialization/trust делегируются frozen P5 adapters, а existing `--targets` остаётся compatibility shim. | RAG:— (repo-grounded: `research/10-p6-maind-analytics-bootstrap-design.md`, `packages/maind/lib/maind/provision/deploy.py`) — прямое расширение `MCP_FILES` сделало бы maind вторым provider renderer. |
| D34 | 2026-07-19 | Onboard/sync/health работают по одному provider-aware ProjectContext; required-provider failure делает aggregate non-green, full access не наследуется, memory scope/graph остаются общими. | RAG:— (repo-grounded: `research/10-p6-maind-analytics-bootstrap-design.md`, D13/D29) — плоский fan-out иначе скрывает partial failure и смешивает provider trust с memory semantics. |
| D35 | 2026-07-19 | Analytics baseline — neutral normalized home `.swissknife/analytics` + explicit provider readers/provenance; raw logs local-only, legacy Claude data dual-read/single-write и copy+verify без удаления; freeze owner-gated в P6.3. | RAG:— (repo-grounded: `research/10-p6-maind-analytics-bootstrap-design.md`, current `core/runs.py`/analyst paths) — общий store не должен копировать Claude raw schema или терять историю. |
| D36 | 2026-07-19 | Cold restart разделён на P6.5 pre-restart checkpoint и P6.6 post-restart proof в новой сессии; P7 не стартует без terminal GREEN P6.6. | RAG:— (repo-grounded: `brief/00-brief.md`, plan-protocol cold-start discipline) — продолжение старого chat не доказывает durable bootstrap. |
| D37 | 2026-07-19 | P6 исполняется строго P6.1→P6.2→P6.3→P6.4→P6.5→restart→P6.6 после terminal/frozen P0–P5 gate; workflow orchestration не создаётся. | RAG:— (repo-grounded: `phases/P6.md`, `research/10-p6-maind-analytics-bootstrap-design.md`) — items последовательно потребляют один deploy/sync/analytics/checkpoint seam, а restart является явным session gate. |
| D38 | 2026-07-19 | Executor Routing всего плана использует current ChatGPT/Codex family: GPT-5.6 Sol для design/contracts/audit, GPT-5.6 Terra для prescribed/deterministic implementation; Luna не используется на release-critical path. | RAG:✅ 2026-07-19 (`findings/P7-openai-model-routing-2026-07-19.md`) — официальный OpenAI catalog называет Sol flagship для complex reasoning/coding, Terra — balance tier, Luna — cost-sensitive high-volume tier. |
| D39 | 2026-07-19 | P7 исполняется строго P7.1→P7.2→P7.3→P7.4 после terminal GREEN P6.6; isolated E2E предшествует live self-host, cleanup требует provenance/replacement proof, workflow не создаётся. | RAG:— (repo-grounded: `research/11-p7-self-host-release-design.md`) — каждый item потребляет terminal evidence предыдущего, independent scopes для orchestration отсутствуют. |
| D40 | 2026-07-19 | Только literal GREEN P7.4 + explicit Approval Owner D# открывает отдельный FOREMAN reconcile; ATTENTION/RED, draft/uncommitted evidence или protected delta сохраняют pause. | RAG:— (repo-grounded: `AGENTS.md`, D7/D11/D12, `research/11-p7-self-host-release-design.md`) — self-host executor не утверждает собственный release и donor plan не меняется в P7. |
| D41 | 2026-07-19 | `[POSSIBLE-DEFECT]` До исправления plan-lint handoff для следующего `plan-design <ID> finish` объявляет допустимую manual Next-форму, сохраняя фактическую Codex-команду finish в launch block. | RAG:— (repo-grounded: plan-lint 2026-07-19 вернул ERROR для `Next: /task:plan-design 2026.07.19-DUAL-PROVIDER finish`, тогда как plan-design mode 5 требует именно finish) — package code вне scope P7 design и не меняется. |
| D42 | 2026-07-19 | Design pass 3/3 завершает cross-phase freeze: P0→P7 contract chain, producer-before-consumer reads, per-item Routing и owner gates согласованы; execution остаётся закрытым до GREEN design audit. | RAG:— (repo-grounded: `research/12-final-cross-phase-reconcile.md`) — finish не исполняет package code и не меняет FOREMAN/fleet. |
| D43 | 2026-07-19 | Shared-package/live-mutation gates имеют явных carriers: P1.2 и P6.4 создают contribution-review artifacts; P7.2 live apply и P7.3 cleanup требуют owner D# после isolated/inventory evidence. | RAG:— (repo-grounded: `research/12-final-cross-phase-reconcile.md`, `phases/P1.md`, `phases/P6.md`, `phases/P7.md`) — обязанность без адресата не является исполняемым gate. |
| D44 | 2026-07-19 | Routing pass 3 сохраняет `gpt-5.6-sol` для design/contracts/audit и `gpt-5.6-terra` для prescribed implementation; 11 Terra/medium items идут через `plan-exec`, остальные 26 — `manual`, без workflow batches. | RAG:✅ 2026-07-19 (`findings/P7-openai-model-routing-2026-07-19.md`) — официальный catalog и Terra model page повторно подтверждены; account availability остаётся fail-closed runtime gate. |
| D45 | 2026-07-19 | Owner refinement: root и package-level `AGENTS.md` — семантический Codex-аналог соответствующего `CLAUDE.md`; оба строятся из common rule canon, byte identity не требуется, provider-specific extensions разрешены только явно. | RAG:— (owner-grounded: `brief/01-refinements.md`; synthesis: `research/13-instruction-contract-remediation.md`) — закрывает Major audit finding без сведения providers к lowest common denominator. |
| D46 | 2026-07-19 | Executable carrier: P5.6 frozen `provider-instruction-contract`; explicit harness instruction catalog/fragments + P5.7 renderer; P2 lock `.swissknifeman/provider-artifacts.lock.json` с full source/render hashes; два managed blocks и bytes-outside-markers ownership; P6.2 deploy/repair. | RAG:— (repo-grounded: `research/13-instruction-contract-remediation.md`, `core/block.py`, `packages/skiller/scripts/generate-hub.sh`, `packages/maind/lib/maind/health.py`) — один carrier на semantics/source/provenance, без output→output translation. |
| D47 | 2026-07-19 | Supersedes D32 sequence: P5 теперь P5.1→P5.7, где P5.6 contract предшествует P5.7 implementation/conformance; P6.2/P6.5/P6.6 интегрируют и доказывают механизм, P7 только self-host/cleanup/release-проверяет его. | RAG:— (repo-grounded: `phases/P5.md`–`phases/P7.md`, `research/13-instruction-contract-remediation.md`) — P7 не проектирует release-critical mechanism впервые. |
| D48 | 2026-07-19 | Restart traceability исправлена: durable carriers — P6.5 pre-restart disk+mAInd checkpoint и P6.6 cold-session proof, включая instruction source/render hashes; P6.4 остаётся analytics implementation. | RAG:— (repo-grounded: `phases/P6.md`, `research/00-user-intent-traceability.md`) — ссылка теперь указывает на фактические Deliverables. |
| D49 | 2026-07-19 | Journal remediation append-only: historical plan-design starts получают terminal `no-op` backfills (design завершён, execution statuses не менялись), invalid free-form audit friction компенсируется канонической `audit-red` deviation row; старые строки не переписываются. Anchored plan-lint в этом заходе не запускался и GREEN не заявляется. | RAG:— (repo-grounded: `packages/task/lib/task/journal.py`, plan-journal contract §1/§2, `journal.jsonl`) — сохраняет историю и честно выносит residual на повторный audit. |
| D50 | 2026-07-19 | Current Routing после remediation покрывает 39/39 items: 11 `plan-exec`, 28 `manual`; P5.6/P5.7 идут solo/full и не меняют provider model family D38/D44. | RAG:— (repo-grounded: `plan.md` §3, `roadmap.md`) — новые contract/implementation risks неоднородны с P5.5 и не батчатся. |
| D51 | 2026-07-19 | Owner-approved historical schema exception (supersedes D49 в части invalid row 11): sealed event `journal.jsonl` не переписывается и не расширяется; optional append-only `journal-exceptions.jsonl` фиксирует physical line 11 + SHA-256 exact raw bytes, exact `invalid_fields:["friction"]`, owner D51, actor/reason. Writer и linter fail closed на duplicate/hash mismatch/missing D#/valid или malformed target; sidecar не несёт event/status/next и не может таргетить sidecar. | RAG:— (owner-grounded: remediation invocation; repo-grounded synthesis: `research/14-journal-schema-exception-remediation.md`; F1: `findings/design-audit-2026-07-19-r2.md`) — устраняет append-only↔strict-per-line противоречие без correction-цикла и без изменения P0.1–P7.4. |
| D52 | 2026-07-20 | Supersedes D10 для остатка P0: после terminal P0.1 порядок становится P0.5→P0.2→P0.3→P0.4. P0.5 отдельно корректирует umbrella Command Surface (`32 = task 11 + skiller 5 + harness 6 + maind 8 + analyst 2`), не переписывая P0.1; P0.2 owner gate обязан принять различие Command Surface/Task Command и terminal P0.5 anchor до freeze. | RAG:— (owner-grounded: `brief/01-refinements.md`; repo-grounded synthesis: `research/15-command-surface-prerequisite-remediation.md`) — сохраняет item/journal provenance и устраняет prerequisite defect отдельным executable carrier. |
| D53 | 2026-07-20 | Approval Owner утверждает как единый набор весь P0.2 glossary и scenarios S1–S10/W1–W3: stable Provider IDs `claude-code`/`codex`; Support Level `native`/`adapted`/`unsupported`; раздельные Project Trust/Approval Policy/Sandbox Boundary; Canonical/Rendered/Managed Artifact lifecycle; Override/Drift/Repair; отдельные glossary entries Command Surface и Task Command. Terminal P0.5 anchor `d8ac22c04fc4d4219dc95244ee9d181e92553a74` принят: `32 = 11 + 5 + 6 + 8 + 2` — current umbrella observation, `11` — current task subset observation; counts не являются frozen constants. | RAG:— (owner-grounded: manual owner-gated P0.2 invocation 2026-07-20; repo-grounded: terminal `findings/P0-command-surface-correction.md`, `root/CONTEXT.md`, `research/04-provider-domain-scenarios.md`) — один approval покрывает весь vocabulary/scenario set и открывает P0.3 без freeze текущих inventory counts. |
| D54 | 2026-07-20 | Approval Owner требует исправлять все обнаруженные launch/hook/command defects, а повторяемые invariants компактно хранить в root `AGENTS.md`. Для P0.3 supersedes только дефектную Validation-команду: negative draft-scan ограничивается двумя P0.3 contract files и их строками Contracts table; draft contracts будущих P0.4/P1.1/P5.1/P6.3 не входят в acceptance P0.3. D54 не утверждает candidate contract semantics. | RAG:— (owner-grounded: `brief/02-launch-and-hook-remediation.md`; repo-grounded: `findings/P0-codex-launch-hook-defects-2026-07-20.md`, `phases/P0.md` P0.3 Validation) — устраняет observed hook exit 127, duplicate registration и невозможный cross-phase grep без преждевременного freeze. |
| D55 | 2026-07-20 | Approval Owner замораживает единым набором `provider-capability-contract.md` и `provider-artifact-contract.md` как v1.0.0 и принимает ADR-0001: stable provider/capability/support/evidence semantics; независимые trust/approval/sandbox axes; deterministic identity/provenance/hash/boundary/override/drift/repair; canonical semantic source + независимые provider adapters, symlink только optional dev mode. Точный pre-P0.3 `docs/reference.md` diff принят с SHA-256 `fcf8eec53645378a877f56a2743da2e0ecf848c4cb63a60b45c0817634ebacd1`. Решение не разрешает FOREMAN/fleet writes или будущие package items. | RAG:— (owner-grounded: explicit D55 approval 2026-07-20; repo-grounded: два contract candidates, `root/adr/0001-provider-adapter-architecture.md`, exact `git diff -- docs/reference.md`) — открывает final P0.3 validation/bookkeeping без изменения утверждённой candidate semantics. |
| D56 | 2026-07-20 | Environment defect, способный повлиять на model/effort, filesystem, MCP/evidence, hooks, sandbox/approval, context budget или validation fidelity, немедленно раскрывается Owner и останавливает зависимую работу. Safe in-scope defect исправляется сразу с повторной проверкой; доказуемо терпимый — фиксируется с exact follow-up; failed/skipped check не считается green. | RAG:— (owner-grounded: `brief/03-environment-defect-handling.md`) — сохраняет качество phase-first исполнения и запрещает молчаливые/ложнозелёные environment обходы. |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol high | Design pass 1/3: сохранены brief/findings/research, выбран target architecture, созданы draft contracts и скелеты 8 фаз/34 items; следующий фокус — детализация P0. |
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol high | ACTIVE перехвачен у `2026.07.18-FOREMAN`; FOREMAN paused на P1.3/P1.4 boundary до release gate P7.4. |
| 2026-07-19 | issue-planner/Codex high | P0 детализирована до DoR: 4 sequential items, per-item Routing, owner gates, pre-mortem и третий draft migration-gate contract; execution ещё не начинался. |
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol xhigh | P1 детализирована до DoR: frozen config-contract gate, pure core boundary, per-item Routing и compatibility/no-write matrix; P0 остаётся неисполненным entry gate. |
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol high | P2 детализирована до DoR: shared-package proposal/ADR gate, deterministic artifact/lock/catalog API, sequential Routing и synthetic no-write conformance; package code не исполнялся. |
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol high | P3 детализирована до DoR; Design pass 2/3 завершён: P0–P3 имеют sequential contracts/items, следующий фокус — P4–P7 и общий finish; package code не исполнялся. |
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol high | P4 детализирована до DoR: frozen command/routing contract, neutral tiers, dual projections, plan gates и independent parity; следующий фокус — P5, package code не исполнялся. |
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol high | P5 детализирована до DoR: harness/security contract, common profiles, native hooks/MCP/agents и independent conformance; 35 items всего, package code не исполнялся. |
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol high | P6 детализирована до DoR: provider-aware deploy/sync, owner-gated neutral analytics, reversible migration и split cold-restart proof; 37 items всего, package code не исполнялся. |
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol high | P7 детализирована до DoR; Routing/roadmap переведены на GPT-5.6 Sol/Terra и создан release/self-host sequence для всех 37 items; package code не исполнялся, FOREMAN/fleet не менялись. |
| 2026-07-19 | issue-planner/Codex gpt-5.6-sol xhigh | Design pass 3/3 finish: reconciled P0–P7 contracts/reads/Routing/owner gates, исправлены stale authoring carriers и пересобран roadmap v1.0.0; package code не исполнялся, FOREMAN/fleet не менялись. |
| 2026-07-19 | issue-planner/Codex | Post-audit design remediation: добавлены P5.6/P5.7 instruction contract+projection carriers, проведены через P6/P7, исправлена restart traceability, roadmap v1.1.0 и append-only journal lifecycle; package code/tests/plan-lint не запускались, GREEN не заявлен. |
| 2026-07-19 | issue-planner/Codex gpt-5.6 high | Audit-r2 F1 remediation: D51 owner-gated sidecar синхронизирован с journal writer/schema/linter/plan lifecycle; sealed event bytes сохранены, P0.1–P7.4 не исполнялись; детали и anchors см. `research/14-journal-schema-exception-remediation.md`. |
| 2026-07-20 | issue-planner/Codex gpt-5 high | Audit-r3 F1 remediation: event+sidecar IDs привязаны к canonical plan-directory ID в writer/linter, mismatch non-exemptable; contract/D51/canon не менялись, evidence — `findings/journal-same-plan-remediation-verification-2026-07-20.md`. |
| 2026-07-20 | plan-exec/Codex gpt-5.6-terra medium | P0.1 закрыт: reproducible provider inventory зафиксировал current path sets и task-command delta — детали см. phases/P0.md P0.1 Completion Notes. |
| 2026-07-20 | issue-planner/Codex gpt-5 high | P0.2 prerequisite remediated в design: добавлен P0.5 carrier, glossary различает umbrella 32 и task subset 11 (на `d8ac22c`); P0.1 history сохранена, freeze ждёт terminal P0.5 и owner D#. |
| 2026-07-20 | plan-exec/Codex gpt-5.6-terra medium | P0.5 закрыт: отдельный scanner и anchored umbrella correction фиксируют пять explicit roots без переписывания P0.1 — детали см. phases/P0.md P0.5 Completion Notes. |
| 2026-07-20 | plan-run/Codex gpt-5.6-sol high | P0.2 закрыт: D53 утвердил единый glossary/scenario set и distinction Command Surface / Task Command — детали см. phases/P0.md P0.2 Completion Notes. |
| 2026-07-20 | Approval Owner + plan-run/Codex gpt-5.6-sol xhigh | D54: исправлены Codex launch/hook registrations и P0.3 Validation scope; contract candidates остаются незамороженными до отдельного D55. |

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| `root/contracts/provider-capability-contract.md` | v1.0.0 | frozen (D55) | P1–P7, FOREMAN reconcile после P7.4 | 2026-07-20 (D55) |
| `root/contracts/provider-artifact-contract.md` | v1.0.0 | frozen (D55) | P2–P7, future fleet rollout | 2026-07-20 (D55) |
| `root/contracts/provider-migration-gates.md` | v0.1.0-draft | draft; sealing P0.4 | P1–P7, FOREMAN resume decision, future fleet plan | — |
| `root/contracts/provider-config-contract.md` | v0.1.0-draft | draft; sealing P1.1 after P0.3/P0.4 | P1.2–P7, future FOREMAN/fleet consumers | — |
| `root/contracts/provider-skill-publication-contract.md` | planned v1.0.0 | owner-gated creation/sealing P3.1 after P2.4 | P3.2–P3.5, P4 task adapters, P7 self-host/release evidence | — |
| `root/contracts/provider-command-routing-contract.md` | planned v1.0.0 | owner-gated creation/sealing P4.1 after P3.5 | P4.2–P4.5, P5–P7, FOREMAN reconcile после P7.4 | — |
| `root/contracts/provider-harness-contract.md` | v0.1.0-draft | draft; owner-gated sealing P5.1 after P4.5 | P5.2–P5.5, P6 deploy/sync, P7 self-host/release evidence | — |
| `root/contracts/provider-instruction-contract.md` | planned v1.0.0 | owner-gated creation/sealing P5.6 after P5.5 | P5.7 renderer/conformance, P6.2/P6.5/P6.6 deploy+restart, P7 self-host/cleanup/release evidence | — |
| `root/contracts/provider-analytics-contract.md` | v0.1.0-draft | draft; owner-gated sealing P6.3 after P6.2 | P6.4–P6.6, P7 self-host/release evidence, future provider telemetry | — |

## Обсуждение

### Distribution SSOT: symlink или generated adapters

- **(рекоменд.) Generated adapters.** Нативный output, lock/hash/drift, переносимость.
- **Symlink-first.** Проще локально, но хрупок в plugin cache/vendor/archive и не выражает transforms.

**Статус:** Resolved → D2

### Scope массовой раскатки

- **(рекоменд.) Self-host SKM сейчас, fleet после FOREMAN.** Меньше blast radius, сохраняет программу владельца.
- **Мигрировать все 25 проектов сразу.** Быстрее внешне, но смешивает platform migration и consumer rollout.

**Статус:** Resolved → D6

### Historical schema-invalid journal row: correction carrier или exception sidecar

- **(рекоменд.) Owner-gated exception sidecar.** Сохраняет sealed event schema/bytes,
  таргетирует exact raw SHA-256 и не попадает в event consumers; цена — optional второй
  provenance carrier только для schema gate.
- **Correction event внутри `journal.jsonl`.** Сохраняет один файл, но меняет event union,
  требует обновления всех readers и может ошибочно считаться execution/no-op.
- **Переписать row 11.** Возвращает per-line validity, но уничтожает append-only provenance.

**Статус:** Resolved → D51
