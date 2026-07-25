# 2026.07.24-AGENT-RELIABILITY — надёжное исполнение, SSOT и замкнутая обратная связь

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.07.24-AGENT-RELIABILITY |
| Title | Надёжное исполнение: checked task contract, единственный runtime source, bounded review и измеримая обратная связь |
| Version | 1.6.0 |
| Status | 🟡 In progress |
| Document Type | Executable Master Plan |
| Authoring Model | Codex gpt-5.6-sol/high; Owner-override Pass 4 — gpt-5.6-sol/xhigh |
| Last Updated | 2026-07-25 |
| Repository | swissknifeman |
| Related Packages | task, skiller, harness, analyst, maind |
| Execution Mode | reliability-first · evidence-before-mutation · phase-bounded |
| Target Operator Models | neutral Routing §3; native Codex mapping materialized only in roadmap launch blocks |
| Approval Owner | Dmitry Vostrikov |
| Home | repo:/home/vostrikov/projects/packages/swissknifeman |
| Paused By | — |
| Design Passes | 4/4 — Passes 1–3 завершили исходный design budget; design audit 2/2 вернул RED по F1/F2. Owner override B от 2026-07-25 разрешил ровно один Pass 4: immutable-bundle semantic verifier contract и private canonical/generator closure для 13 bootstrap identities. Следующий шаг — единственный exceptional fresh independent design audit (`0/1` использован до старта) |

## 1. Context

За 2026-07-20…24 крупные планы в `swissknifeman`, `azguard`, `insiders` и
`dterema` повторно теряли требования владельца, без нужды останавливались,
спрашивали уже данное согласование и возвращались в audit/fix loops.
Одновременно короткий `HONEST-HTTP-ERRORS` является clean counterexample.

Canonical controls уже содержали product-vs-bookkeeping verdict, two-audit
cap и `same-session — item`, но полевая работа им не соответствовала.
Поэтому план не объявляет причиной «отсутствующие правила». Он проверяет
falsifiable hypothesis: declarative controls не компилировались/не
проверялись на transition, pre-mutation, pre-final и public-acceptance
границах либо runtime выбирал stale/duplicate carrier. Duplicate identities
и session fragmentation остаются недоказанными усилителями до P0 traces.

Committed snapshot Perplexity-аудита в `artifacts/source-evidence/`
используется как hash-pinned hypothesis source, а не backlog. Там же лежат
lossless journal snapshots, sanitized selected session evidence и
precomputed corpus/baseline. План сначала проверяет self-contained bundle,
Task Contract и Acceptance bank; только затем меняет hooks/runtime.
P1 устраняет доказанные delivery/discovery collisions, P2 добавляет
enforcement существующих rules, P3 связывает traces/evals и выполняет
изолированный self-host canary. P4 не реализует speculative refactor:
он выносит code-grounded verdict, узкий operator doctor и Owner packet.

`plans/2026.07.24-AGENT-RELIABILITY/root/` — repo-relative canonical
artifact directory из plan-protocol, не системный `/root`. Плановые
contracts/commands одинаково видимы Claude и Codex; provider-specific
adapters и native launch blocks являются projections, а не скрытым SSOT.

Финальный исходный design audit attempt 2/2 оставлен literal RED:
`findings/08-design-audit-red-attempt-2.md`. Владелец выбрал capped option B.
Этот Pass 4 не исполняет P0.1 и не меняет packages/runtime; он устраняет F1
разделением immutable integrity gate и item-owned semantic verification, а F2
— private canonical sources плюс единственный deterministic root-bootstrap
generator. Исторический cap 2/2 не обнулён: отдельно разрешён только один
exceptional independent design audit после redesign.

## 2. Execution Rules

- P0 не начинается до literal GREEN единственного exceptional independent
  `plan-audit design`. Исходный cap `2/2` исчерпан; Owner override B разрешает
  после Pass 4 ровно один новый audit (`0/1`). RED/ATTENTION снова возвращает
  Owner decision без автоматического repair или следующего audit.
- P0.1–P0.3 только фиксируют evidence/contracts. Любая behavior mutation,
  включая hooks, начинается не раньше owner-approved P0.3 bank freeze.
- Latest explicit owner instruction действует только в своём scope; нижний
  carrier может сузить safety, но не расширить authority.
- Routine implementation/tests/close/следующий ready item не требуют Owner
  Approval. Реальные gates: P0.3 acceptance/bank freeze и P4.3
  fleet/FOREMAN/tag/push/release decision.
- Existing audit cap/product distinction/same-session semantics не
  копируются новой прозой: P2 реализует единственный compiler/enforcement
  seam и conformance tests.
- Product, evidence и process findings имеют разные states. Evidence repair
  не переоткрывает доказанно green product; третий same-finding event
  создаёт incident, а не четвёртый fix loop.
- `azguard`, `insiders`, `dterema`, FOREMAN и fleet — read-only evidence.
  Writes разрешены только в self-host repo и disposable P3.4 worktree.
- `.agents/skills` и `.claude/skills` содержат только generated thin
  repository-bootstrap projections для identities, не обслуживаемых
  authoritative installed bundle; их 13 canonical sources живут только в
  private/source-only `packages/skiller/skills/repository-bootstrap/`.
  Normal bucket/core/marketplace publication этих 13 запрещена. 12 colliding
  root core/task adapters удаляются в P1.2/P1.3; task commands остаются только
  в `packages/task/commands`.
- Generated projection обязана иметь owner, provenance/hash, complete
  dependency closure и одну effective semantic identity.
- Canonical execution inputs живут в repo paths и semantic `task:*`
  carriers. Provider invocation рендерится только из checked mapping;
  `.agents` и native Codex blocks не переопределяют canon.
- Execution не читает `tmp/`, profiles, mAInd или foreign repos. Optional
  origin paths остаются provenance; только committed
  `artifacts/source-evidence/` является evidence input.
- Python остаётся stdlib-only. Missing evidence/route/capability остаётся
  unknown/red; ноль и silent skip запрещены.
- Каждый item коммитит только exact `Files`; `git add -A`, `git commit -a`,
  stash/revert чужих правок и staging `tmp/` запрещены.
- Item close следует canonical two-commit topology. Plan files закрываются
  отдельным bookkeeping commit; этот design pass не коммитит ничего.
- После каждого item — exact focused tests; package validate — перед item
  commit; terminal phase — один bounded independent audit.
- Все native Codex launch blocks используют repo cwd, routed model/effort,
  `-a never -s danger-full-access` и `NEW SESSION`.
- Каждый item recovery carrier требует `command.subagents`; если cold-start
  preflight не подтверждает capability как `native`/`adapted`, execution
  fail-closed до mutation без silent solo fallback.
- `plans/2026.07.18-FOREMAN` не исполнять и не менять.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
|  | P0.1 | implementation/medium | plan-exec | full | deterministic committed-bundle verifier/normalizer, baseline load-bearing |
|  | P0.2 | frontier/high | manual | full | frozen Task Contract с открытыми design decisions; full-класс не батчится |
|  | P0.3 | frontier/high | manual | full | Acceptance/bank freeze и Owner gate; full-класс не батчится |
|  | P0.4 | implementation/high | manual | full | hook lifecycle high-risk, реализация против frozen P0 contracts |
|  | P1.1 | frontier/high | manual | full | freeze cross-package identity/ownership semantics |
|  | P1.2 | implementation/high | manual | full | skiller/root/core publication correctness; full-класс не батчится |
|  | P1.3 | implementation/high | manual | full | task/harness effective catalog repair after P1.2; full-класс не батчится |
|  | P1.4 | implementation/medium | plan-exec | full | deterministic terminal conformance against frozen P1.1 |
|  | P2.1 | frontier/high | manual | full | freeze state/authority semantics before code |
|  | P2.2 | implementation/high | manual | full | shared task compiler/enforcement seam, correctness-critical |
|  | P2.3 | implementation/high | manual | full | audit/review transition enforcement, correctness-critical |
|  | P2.4 | implementation/high | manual | full | route evidence and fail-closed compliance |
|  | P2.5 | implementation/medium | plan-exec | full | deterministic end-to-end bank after P2 implementation |
|  | P3.1 | implementation/high | manual | full | versioned cross-provider trace schema and adapters |
|  | P3.2 | implementation/high | manual | full | metric arithmetic/provenance against frozen trace |
|  | P3.3 | implementation/high | manual | full | system behavioral eval release gate |
|  | P3.4 | implementation/high | manual | full | disposable-worktree canary, rollback and real mutations |
|  | P3.5 | frontier/xhigh | manual | full | fresh terminal adversarial verdict; no self-certification |
|  | P4.1 | frontier/high | manual | full | falsify architecture hypotheses; any accepted refactor becomes a new plan |
|  | P4.2 | implementation/medium | plan-exec | light | bounded read-only doctor over frozen P1/P3 contracts |
|  | P4.3 | frontier/high | manual | full | final measured-scope synthesis and real Owner rollout/release gate |

## 4. Phase Index & Status Board

| Phase | Title | Items 🟢/всего | Status |
|:--|:--|:--|:--|
| P0 | Evidence, contracts и acceptance-before-mutation | 0/4 | ⬜ Not started |
| P1 | Единственный semantic source и runtime uniqueness | 0/4 | ⬜ Not started |
| P2 | Checked outcome execution и bounded review | 0/5 | ⬜ Not started |
| P3 | Unified traces, evals и isolated self-host canary | 0/5 | ⬜ Not started |
| P4 | Hypothesis verdict, operator doctor и Owner packet | 0/3 | ⬜ Not started |

## 5. Decision Log

| D# | Дата | Решение | Почему |
|:--|:--|:--|:--|
| D1 | 2026-07-24 | `control-plane enforcement failure` — falsifiable working hypothesis, не установленная root cause. | RAG:— (repo-grounded: `findings/07-design-audit-red-attempt-1.md`, `research/01-root-cause-analysis.md`). |
| D2 | 2026-07-24 | Existing product/bookkeeping, two-audit cap и same-session rules считаются declarative inputs; план не дублирует их как новое решение. | RAG:— (repo-grounded: `packages/task/commands/plan-audit.md:45`, `packages/skiller/skills/general/plan-protocol/SKILL.md:759`). |
| D3 | 2026-07-24 | P0.1 обязан различить carrier availability, selection, check execution и failing transition для каждого critical case. | RAG:— (plan-grounded: falsification requirement D1). |
| D4 | 2026-07-24 | Perplexity-аудит hash-pinned и используется только как claim inventory; speculative refactor не входит в critical path. | RAG:— (repo-grounded: `findings/00-source-evidence-manifest.md`, `findings/01-perplexity-audit-assessment.md`). |
| D5 | 2026-07-24 | Task Contract v1 содержит Goal, Must/Never, Done/Public Acceptance, Authority, Next, Route, Evidence, Portability, Conflicts и Version/Supersedes. | RAG:✅ 2026-07-24 OpenAI Codex best-practice check (`findings/05-external-practices.md`); extended by D26. |
| D6 | 2026-07-24 | Один semantic workflow имеет один canonical owner и одну effective runtime identity. | RAG:— (repo-grounded: `findings/03-ssot-runtime-inventory.md`). |
| D7 | 2026-07-24 | Provider projection публикуется только при complete references, capability coverage и immutable `(name,version)→tree hash`; иначе fail-closed. | RAG:— (repo-grounded: P1 observed incomplete same-version cache and invalid carriers). |
| D8 | 2026-07-24 | P2 implements enforcement at transitions/pre-mutation/pre-final/public acceptance through one compiler/state seam; prose-only repetition запрещено. | RAG:— (repo-grounded: D2 controls existed while field outcomes diverged). |
| D9 | 2026-07-24 | Product/evidence/process findings и stable `finding_id/reopen_of` — machine fields; third same-finding event enters INCIDENT. | RAG:— (plan-grounded: bounded remediation requirement and existing two-audit cap). |
| D10 | 2026-07-24 | Regression bank starts from 20–50 real failure/control cases and grades transcript actions plus public outcome. | RAG:✅ 2026-07-24 Anthropic agent eval method (`findings/05-external-practices.md`). |
| D11 | 2026-07-24 | Unified trace links session/task/run/requirement/route/finding/outcome and carries completeness flags; no external telemetry dependency. | RAG:✅ 2026-07-24 OTel GenAI vocabulary (`findings/05-external-practices.md`). |
| D12 | 2026-07-24 | Neutral Routing is SSOT; native Codex selectors live only in ready roadmap launch blocks. | RAG:— (repo-grounded: canonical plan-protocol §9 and root AGENTS launch requirement). |
| D13 | 2026-07-24 | P0–P3 writes stay inside self-host/disposable fixtures; consumers, fleet and FOREMAN remain read-only. | RAG:— (repo-grounded: root `AGENTS.md`). |
| D14 | 2026-07-24 | P4 structural audit can end accept/reject/unknown, but accepted refactor is a separate future plan, not dynamic Files in this plan. | RAG:— (plan-grounded: executable Files/DoR requirement). |
| D15 | 2026-07-24 | Exact performance floors and grader/corpus hashes freeze in P0.3 before any behavior mutation; later change requires Owner D#. | RAG:✅ 2026-07-24 static paired eval practice (`findings/05-external-practices.md`). |
| D16 | 2026-07-24 | P0.4 is first behavior mutation and is blocked on P0.3 Owner Approval. | RAG:— (plan-grounded: evidence-before-mutation safety boundary). |
| D17 | 2026-07-24 | Phase ordering is strictly P0→P1→P2→P3→P4; no cross-phase parallel execution. | RAG:— (plan-grounded: explicit producer/consumer contracts in phase contexts). |
| D18 | 2026-07-24 | Design accounting is corrected to Pass 2/3; each pass is a fresh session and next step is Pass 3, not P0 execution. | RAG:— (repo-grounded: plan-protocol design budget; supersedes withdrawn draft pass-count claim). |
| D19 | 2026-07-24 | Roadmap stores a ready native Codex `NEW SESSION` carrier for every solo/batch group; predecessor close may refresh hash/input refs but may not omit the group carrier. | RAG:— (repo-grounded: plan-protocol roadmap requirement; supersedes withdrawn draft D19). |
| D20 | 2026-07-24 | Raw sessions are consumed only through a selected exact path/hash manifest generated once by the P0.1 stdlib extractor; repeat runs read that manifest. | RAG:— (plan-grounded: cold-start reproducibility requirement). |
| D21 | 2026-07-24 | P3.4 runs in one disposable detached git worktree; every canary case is committed, inspected, returned to candidate by clean detach, and cleanup refuses dirty state. | RAG:— (repo-grounded: user-change preservation and canary rollback boundary). |
| D22 | 2026-07-24 | Root supervisory session persists and dispatches each executable item to a fresh subagent grounded from committed plan/handoff; roadmap records canonical `Plan context=same-session — item` and native recovery `Context=NEW SESSION` separately. Every item carrier requires `command.subagents`; preflight verifies the Codex mapping is `native` and live `multi_agent` is enabled, otherwise fails closed. | RAG:— (repo-grounded: root `AGENTS.md`; `packages/task/configs/command-routing.json` Codex capability binding; `codex doctor --json` at Pass 3 reports `multi_agent` enabled). |
| D23 | 2026-07-24 | Shared-package/public-contract items consume `package-contribution-protocol`: reuse-survey and Rule of Three first; a new public seam requires pinned consumers, ≥2 alternatives, proposal/ADR decision and explicit SemVer. Unfrozen scope escalates rather than expanding inline. | RAG:— (repo-grounded: `packages/skiller/skills/architect/package-contribution-protocol/SKILL.md`; applies to P0.4, P1.1–P1.3, P2.1–P2.4, P3.1–P3.3 and P4.2). |
| D24 | 2026-07-24 | Provider-portable SSOT is the committed plan/canonical repo sources plus semantic `task:*` carrier. `plans/<ID>/root/` is relative, not OS `/root`; `.agents` and native blocks are projections. P0.1 raw evidence is intentionally host-bound and non-portable until exact manifests/corpus/baseline are committed; absence/hash drift fails closed. | RAG:— (repo-grounded: plan-protocol §3; `packages/task/configs/command-routing.json`; commit `454ea86d` migrated one archived plan's absent `root/` checklist and did not change the active-plan canon). |
| D25 | 2026-07-24 | Owner decision: execution evidence is fully self-contained before audit. `artifacts/source-evidence/` carries full audit snapshot, seven lossless journals, sanitized selected session incidents, manifests, precomputed corpus/baseline and deterministic verifier. External origins are optional provenance only; P0.1 verifies/normalizes the committed bundle. Supersedes D20 and D24 only where they allowed host-bound execution inputs. | RAG:— (owner refinement captured in `brief/01-refinements.md`; repo-grounded portability contract and privacy boundary). |
| D26 | 2026-07-24 | Self-contained planning becomes a compiled package capability, not plan-local prose. Canon defines tiers: simple low-risk/single-session plans may use committed brief+acceptance; multi-session, high-risk, handoff and audit plans require committed execution inputs or exact predecessor-produced paths. Host/chat/mAInd/`tmp`/foreign references are provenance/advisory only; evidence bundles are minimized, exclude secrets/chain-of-thought/raw bulk, carry deterministic manifest/verifier, and use one provider-neutral semantic carrier with provider renderers. P2.2 enforces this in Task Contract/plan-design/plan-lint; P2.5/P3.3 prove it; P4.3 documents it. | RAG:— (explicit Owner refinement; local D25 bundle is the first acceptance fixture, not the only implementation). |
| D27 | 2026-07-24 | Every canonical/package publication change is version-first and generator-closed: one owner item bumps its exact package/plugin/publication-unit version, regenerates the full declared tree/locks/marketplaces, proves a read-only second check, and passes an exact diff-scope guard. `packages/skiller/configs/publication-versions.json` separates package API SemVer from finite unit versions so unaffected bucket manifests remain byte-identical. Reusing `(name,version)` for different tree bytes is forbidden. P1.1 freezes candidate versions; P1.2/P1.3/P2.2/P2.3 publish them; P4.3 is read-only and reopens the owner on drift. | RAG:— (repo-grounded: `skiller validate` includes `registry --check`; registry currently derives all bucket versions from one package version; generated Codex/task locks encode version/tree). |
| D28 | 2026-07-24 | Resolve all 12 native Codex collisions by ownership, not suppression: installed generated `core` and `task` bundles are authoritative; delete the six exact root core and six exact root task auto-discovered adapter directories only after repository-marketplace/generated-bundle proof. Remaining root adapters are unique bootstrap-only carriers. P1.4 cold-installs from explicit fixture roots and requires each of the 12 semantic IDs exactly once. | RAG:— (repo-grounded: committed effective inventory and read-only `codex plugin list --json` confirm enabled `core@0.4.0` and `task@0.3.0`; root adapters duplicate their semantic IDs). |
| D29 | 2026-07-25 | Owner chose capped option B: preserve the two historical RED verdicts and exhausted design cap `2/2`, authorize exactly one redesigned executable contract (Pass 4/4) and exactly one later fresh independent exceptional design audit (`0/1` before launch). P0.1 requires its literal GREEN; any non-GREEN returns to Owner without implicit repair/audit authority. | RAG:— (owner-grounded: `brief/01-refinements.md`, Owner override B). |
| D30 | 2026-07-25 | F1 repair: immutable `artifacts/source-evidence/verify_source_bundle.py` owns only its actual byte/schema/pinned-constant checks and remains unchanged. P0.1 owns `root/contracts/source-evidence-verification-v1.md`, a machine contract, semantic verifier, focused tests and report outside the bundle. Recomputed/cross-checked facts are distinct from `pinned-not-recomputable`/`unknown`; excluded raw-session dedup and an uncommitted lifecycle classifier can never be reported as semantically verified. | RAG:— (repo-grounded: `findings/08-design-audit-red-attempt-2.md` F1 and `artifacts/source-evidence/verify_source_bundle.py:26-111`). |
| D31 | 2026-07-25 | F2 repair, supersedes D27/D28 only for the 13 remaining root bootstrap identities: canonical bilingual sources are exact `packages/skiller/skills/repository-bootstrap/<name>/{SKILL.ru.md,SKILL.md}` records in a private/source-only bucket. `build_registry` indexes them, but publication catalog excludes the bucket from normal Claude/Codex bucket, core and marketplace units; consumer vendor/connect selection also rejects these source-only records. `registry.py` invokes the sole `publication.py` root-bootstrap renderer from `configs/repository-bootstrap-skills.json`; it emits only thin `.claude/skills/<name>/SKILL.md` and `.agents/skills/<name>/SKILL.md` projections plus one version/tree lock. `skillset.py` may enforce consumer exclusion but is never this self-host producer. | RAG:— (repo-grounded: `findings/08-design-audit-red-attempt-2.md` F2; current `registry.py:18-24,398-430`; `publication.py:131-177,293-367`; `skillset.py:60-101,223-287,767-853`). |

## 6. Update Log

| Дата | Кто (role/model) | Что |
|:--|:--|:--|
| 2026-07-24 | plan-design/Codex gpt-5.6-sol/high | Design pass 1/3: initial audit/telemetry/SSOT synthesis and 5-phase draft; design audit attempt 1 returned RED — `findings/07-design-audit-red-attempt-1.md`. |
| 2026-07-24 | plan-design/Codex gpt-5.6-sol/high | Design pass 2/3: full plan sweep corrected RCA, evidence manifests, neutral routing, exact phase specs, roadmap carriers and canary topology; Pass 3 remains. |
| 2026-07-24 | plan-design/Codex gpt-5.6-sol/high | Design pass 3/3: fresh full-plan DoR/brief/RCA/dependency/routing/CLI sweep; exact reads, contribution gates, semantic+native recovery carriers and safe temp/worktree contracts reconciled; next — separate audit-design. |
| 2026-07-24 | Owner refinement / plan-design | D25 removes host-bound execution evidence. The materialized bundle passed four verifier modes: 20 manifest entries, 7 journals, 5 sanitized cases, corrected denominators/control and 8 claim ranges. |
| 2026-07-24 | plan-design/Codex gpt-5.6-sol/high | Design pass 3/3 final reconciliation: downstream items, findings, roadmap and handoff consume only the source bundle; version 1.4.0 is ready for separate fresh audit-design. P0 remains unexecuted. |
| 2026-07-24 | Owner refinement / plan-design | D26 promotes self-contained planning into the canonical package contract without adding a phase/item: P0.2/P0.3 freeze fields/cases; P2.1/P2.2 define and enforce tiers in Task Contract, plan-design and plan-lint; P2.5/P3.3 run conformance; P4.3 publishes docs. Version 1.4.0 remains 21 items. |
| 2026-07-24 | plan-design/Codex gpt-5.6-sol/high | Audit attempt 2 stopped pre-verdict on SSOT gaps. Reopened Pass 3 added D27 version/generated-tree closure and D28 exact 12-collision removal plus P1.4 cold discovery. Version 1.5.0; 21 items; P0 unexecuted. |
| 2026-07-25 | Owner override B / plan-design Codex gpt-5.6-sol/xhigh | Design pass 4/4: preserved audit RED 2/2, redesigned F1 as immutable-integrity + item-owned semantic verification and F2 as private 13-source + one generated root-bootstrap unit. Version 1.6.0; 21 items; P0 unexecuted; next is the sole exceptional audit `0/1`. |

## 7. Contracts

### Exported

| Контракт | Версия | Статус | Потребители | Уведомлены |
|:--|:--|:--|:--|:--|
| `root/contracts/source-evidence-verification-v1.md` | v1 | planned P0.1 | P0.2, P0.3, P3.2, P3.5 | task, skiller, analyst |
| `root/contracts/task-contract-v1.md` | v1 | planned P0.2 | P0.3, P2, P3 | task, skiller, harness |
| `root/contracts/reliability-acceptance-v1.md` | v1 | Owner-freeze P0.3 | P0.4–P3 | skiller, task, analyst, harness |
| `root/contracts/semantic-identity-ownership-v1.md` | v1 | planned P1.1 | P1.2–P1.4 | skiller, task, harness |
| `root/contracts/generated-artifact-version-v1.md` | v1 | planned P1.1 | P1.2, P1.3, P2.2, P2.3, P4.3 | skiller, task, harness |
| `root/contracts/execution-state-machine-v1.md` | v1 | planned P2.1 | P2.2–P3 | task, analyst |
| `root/contracts/plan-portability-v1.md` | v1 | planned P2.1 | P2.2, P2.5, P3.3, P4.3 | task, skiller |
| `root/contracts/unified-agent-trace-v1.md` | v1 | planned P3.1 | P3.2–P4 | analyst, harness, task |

### Consumed

| Контракт | Донор-план | Pinned | Замечено | Реакция |
|:--|:--|:--|:--|:--|
| plan-protocol | repository canonical source | `2.11.0` at Pass 2 | P0/P2/P4 | re-read exact source before each plan item |
| provider publication/artifact contract | 2026.07.19-DUAL-PROVIDER | execution commit at P1 start | P1 | preserve Claude compatibility and managed generation |
| Codex hook/plugin/skill behavior | official docs snapshot | reverify at P0.4/P1/P3 | external capability drift | fail closed, update `findings/` first |

## 8. Acceptance proposal for P0.3 Owner freeze

| Метрика | Proposed floor |
|:--|:--|
| Critical requirement retention | 100% critical bank |
| Premature stop / redundant approval | 0 critical bank |
| Effective semantic identity collisions | 0 |
| Hook/reference/provider resolution | 100% controlled fixtures |
| Required trace completeness | ≥99% controlled bank |
| Overall first-pass success | ≥95% and ≥30 percentage points over paired baseline |
| Context input per successful outcome | ≤50% paired baseline |
| Owner intervention | ≤25% paired baseline |
| Same-finding loop depth | median ≤1, p95 ≤2 |
| Critical regression escape | 0 |

These values are proposals until P0.3 Owner Approval. Baseline/corpus/grader
hashes and exact floors freeze together. Candidate-only threshold changes are
forbidden; a grader correction versions the bank and reruns both sides.

## 9. Risks and Boundaries

| Risk | Control |
|:--|:--|
| RCA again hardens a correlation into cause | P0.1 per-case falsification table; `unknown` allowed |
| Plan adds another prose control | P2 one compiler/state seam + conformance tests |
| Source evidence disappears/drifts | committed `artifacts/source-evidence/` with per-file hashes and deterministic verifier; external origins are optional |
| Immutable integrity verifier again accepted as semantic proof | D30 two-layer contract: all four immutable modes run, then P0.1-owned semantic tests/report classify every claim by proof class; bundle diff must remain empty |
| Claude/new clone cannot see Codex-host raw evidence | no execution dependency remains: full audit/journals and sanitized selected incidents are committed; raw rollouts are intentionally excluded |
| Future plans repeat host-bound evidence | D26 compiled portability tiers + plan-design/plan-lint gates + P2.5/P3.3 conformance; not a prose-only reminder |
| `root/` mistaken for OS `/root` or removed after archived-plan migration | D24 + plan-protocol §3: it is a repo-relative plan artifact directory; `454ea86d` is not a canon change |
| Hook repair invalidates baseline | P0.3 freeze before P0.4 mutation |
| Runtime dedup breaks Claude | provider goldens + effective installed-runtime fixtures |
| Registry package bump rewrites unrelated bucket manifests | D27 per-publication-unit version map + exact diff-scope guard + no-op second check |
| Collision gate merely suppresses duplicate adapters | D28 exact 12-directory deletion + P1.4 actual cold install/discovery exactly-once proof |
| Private 13-skill canon leaks into a normal bucket/plugin/consumer vendor channel or root copies drift | D31 source-only publication and vendor/connect exclusion, bilingual source hashes, one `registry.py`→`publication.py` generator, 26 thin projections + version/tree lock and P1.4 exactly-once/provenance checks |
| Canary touches user work | detached disposable worktree; clean-state cleanup guard |
| Self-host GREEN is called fleet GREEN | P3.5 scope literal; P4.3 explicit Owner gate |
| P4 dynamic hypothesis causes wildcard scope | accepted structural refactor leaves this plan as a new proposal |

## 10. Owner Approval Boundaries

- **A0 before P0.1 (already authorized, not a new Owner stop):** run exactly
  one fresh independent exceptional design audit under D29. Literal GREEN
  unlocks P0.1; non-GREEN exhausts `1/1` and returns to Owner.
- **G0 after P0.3:** approve exact Acceptance v1, bank/grader hashes and floors.
  P0.4/P1/P2/P3 cannot begin before this decision.
- **G1 at P4.3:** decide separately whether to authorize any fleet/consumer
  write, FOREMAN continuation, tag, push or release. P4.3 itself only builds
  the packet and may recommend hold.
- A new external authority, destructive operation, or frozen contract change
  outside exact item Scope stops at an explicit owner question.
