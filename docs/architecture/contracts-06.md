# Contract inventory, part 6

### 10.2 Явные JsonObject и отложенные представления

| Место | Причина / владелец уточнения |
|---|---|
| public.py: query views, Page-результаты портов, TokenView, StagedBlobView, FileVersionRef | K20 запрещает ручные wire DTO; формы находятся в схемах; generated-классы — P01.05.a, подключение — owner leaf |
| artifacts.domain: StagedBlobRef, FileVersionRef, OrphanReport | только алиасы JsonObject до codegen, без ручных dataclass DTO |
| access.domain.authorization: Allowed.details, Denied.details | владелец описывает смысл решения, но не фиксирует полный набор полей метаданных; P04.01 |
| workspace.ports.RepositoryRepository.match_remotes | RepositoryMatchView не задаёт полной формы полей; пока tuple[JsonObject, ...], P04.03 |
| artifacts.ports.BlobLocationRef (location BlobStore) | алиас JsonObject `{backend_id, storage_key, storage_version}` (artifacts §6); wire-форма — `location` во view open-file-version-content, сгенерированный тип — P06.03.c |
| settings.domain.WriteContext.spec/farther | будущие KeySpec/KeyResolution из platform config; P02.01/P02.03; пока JsonObject по K20 |
| platform.config Protocol: metadata, provenance, diagnostic, frozen/process config, pack/stored contributions, secret ref | временные JsonObject вместо ещё не материализованных представлений; конкретные типы — P01/P02; kernel ScopeRef и str chain/level используются до config-owned типов |
| workspace AttachDecisionView.refuse_details/diagnostics | произвольные details и будущий Diagnostic; P04.03 |
| settings get-schema: schema и import before/after | схема — JSON-объект, значения изменений — произвольный JSON. KeySpecView полностью объявлен по §A.8/§B.1 в views/get-schema.v1.json; типы метаданных используют config/key-spec.v1.json |
| workspace host requests/reports и artifacts host upload-file | §§7 описывают workflow/CLI, но не фиксируют wire DTO-поля. Схемы оставлены JsonObject; host Protocol принимает/возвращает JsonObject; владельцы P04.05/P04.06/P06.05 |
| artifacts host materialize-files | §4.4 задаёт file_version_ids/target_dir и массив MaterialEntry: эти формы объявлены явно; реализация — owner leaf |

Host DTO с нефиксированной формой допускает произвольные JSON-поля (`additionalProperties: {}`),
как JsonObject; это осознанное исключение из закрытых объектных DTO, а не выдуманный набор аргументов.

`ImportConfig.document` принимает TOML-строку или произвольный JSON-объект. Проверка предметной формы,
включая неизвестные секции и неверный `schema`, принадлежит parser/preview (§A.7.6, §B.11.4),
чтобы ошибки могли возвращаться в `problems` при dry-run, а не отвергаться входной схемой bus.

### 10.3 Отложенные ссылки до P00.04.f

Каждая цель и фрагмент проверяются по `src/skm/schemas/`; неизвестных целей нет.
Разрешение ссылок идёт только из `src/skm/schemas/`, без копий примеров и сетевого retrieve.

| Источник в src/skm/schemas | Отложенная ссылка | Материализует |
|---|---|---|
| settings/document.v1.json | urn:skm:execution:defs:v1#/$defs/json-value | P00.04.d |
| settings/document.v1.json | urn:skm:integrations:defs:v1#/$defs/hook_subscription | P00.04.e |
| settings/document.v1.json | urn:skm:policy:permission-layer:v1 | P00.04.c |
| settings/document.v1.json | urn:skm:policy:profile:v1 | P00.04.c |
| settings/hooks.v1.json | urn:skm:integrations:defs:v1#/$defs/hook_subscription | P00.04.e |
| settings/policy.v1.json | urn:skm:policy:permission-layer:v1 | P00.04.c |
| settings/policy.v1.json | urn:skm:policy:profile:v1 | P00.04.c |
| workspace/remote-normalization-vectors.v1.json | urn:skm:execution:defs:v1#/$defs/json-value | P00.04.d |

Закрытие всех восьми пар источник/цель — P00.04.f. Все остальные ссылки этой группы локальны или
разрешаются в уже материализованные схемы. Положительные/отрицательные диагностические векторы
проверяют обязательные поля, enum, границы, oneOf и отсутствие лишних полей; поведение модулей
и применение policy не считаются реализованными.

## 11. Группа P00.04.c — policy, extensions, runtimes, planning

Декларации материализованы в порядке policy → extensions → runtimes/planning.
Все четыре `MODULE` имеют точный `depends_on` из [графа модулей](layers-and-modules.md), `optional=False`,
собственную схему БД и одну одноимённую секцию настроек. Репозитории и шлюзы
перечислены ниже и в manifest; исполняемые commands/queries/subscribers/host_operations
и events пока пусты. `domain/events.py: EVENT_TYPES` перечисляет URN payload-схем,
а Python event DTO и регистрация остаются генератору P01.05.a и owner leaf.
Фасады и concrete domain methods явно бросают `NotImplementedError`.
Host operations объявлены только callable Protocol; функций `run` нет.

| Модуль | Repository Protocol | Gateway Protocol / сторона | Реализация |
|---|---|---|---|
| policy | ToolIntentRepository, ApprovalRepository, DecisionAuditRepository | PathFacts — host | P07.01, P10.05 |
| extensions | PackRepository, ResourceRepository, QuarantineRepository | PackReader, UpstreamFetcher — host; BuiltinPacks, RuntimeCatalogSeeder — control plane | P09.01 |
| runtimes | HostRuntimeRepository, CapabilityVerificationRepository, ModelCatalogRepository, HostModelAvailabilityRepository | AgentRuntime, RuntimeRegistry, WorkerModelOfferPolicy — host; CapabilityCatalog — shared | P08.01, P08.11, W02 |
| planning | PlanRepository, PlanCounters, DraftRepository, RevisionRepository, PlanningQueries | — | P05 |

Основные domain-объявления:

- policy: path/command/network policies, PermissionSet/PermissionLayer, OperationRule,
  TaskAuthority, ToolCall/ToolDecision unions, ToolIntent/Approval и enum-ы владельца.
- extensions: девять ResourceKind и RESOURCE_KINDS, Pack/PackVersion/PackManifest,
  Resource/ResourceVersion/ResourceRef, SemVer/VersionConstraint, PackPins,
  AgentProfile/PromptPlan/RoleLimits, SkillManifest/SteeringManifest,
  provenance/compat/requires/resolution/payload declarations.
- runtimes: model catalog, 15 capabilities, exact VerificationContext,
  RuntimeInstallation, ProcessOwner/ProcessOwnership, AgentRequest, RuntimeResult,
  RuntimeObservation, девять вариантов SessionEvent, UsageReport/SubagentUsage,
  ProviderFailure/ErrorRule, routing и admission types. RuntimeRegistry — каноническое
  имя (§9 выше), отдельного RuntimeDetector нет. CapabilityCatalog имеет shared marker.
- planning: Specification и восемь видов сущностей; Plan/Draft/RevisionMeta;
  CheckSpec и четыре definition; Read, ReviewRequirement, Authority и DraftChange unions;
  ExecutionGraph/TaskNode/TaskEdge/BatchGroup; preview/diff/rebase/material/validation
  declarations; scoped repository interfaces.

### 11.1 Владение и временные JsonObject

Python DTO не пишутся в `generated/`; wire-контракты объявлены JSON Schema.
Фасады принимают domain/kernel types и JsonObject вместо будущих generated views.
Ниже перечислены места, где дальнейшее уточнение принадлежит owner leaf:

| Место | Причина / владелец |
|---|---|
| policy public views, is_subset violations, DecisionAuditRepository records | wire DTO из §7/§8/§13, P07.01 после codegen |
| policy git_guard.GitViolation, rule_ladder.LadderRule/LadderVerdict | подробности переносимого ядра, P07.01/P10.05; IO отсутствует |
| policy public isolation_grants | kernel IsolationGrants пока не материализован; P01.01/P08.07 |
| extensions AgentProfile role/model_class/effort/capabilities/block types | строки владельцев runtimes/context; запрещён обратный import extensions→runtimes/context; валидируются схемами |
| extensions ContextPolicySpec, PlanTemplateManifest | context принадлежит будущей группе; template wire representation — schema, P09 |
| extensions repository summaries, resource bodies views, resolution candidates/diagnostics, pack config fragments | generated views и platform config contributions, P09.01/P02 |
| runtimes PermissionGrant path/command/network rules, credential mounts | JSON forms заданы agent-request/capabilities schemas; типизация adapters — P08 |
| runtimes AgentRequest.secret_env | будущий SecretStr не материализован; поле исключено из dataclass repr; в P08 требуется SecretStr и redaction, не сериализация сырого секрета |
| runtimes SelfLoadedSource, diagnostics/violations/ToolActivitySummary | adapter-owned metadata и будущие generated views; P08 |
| runtimes RoleRoute, admission/route explain nested views | routing config и wire DTO; P08.01/P08.11 |
| planning SpecificationDoc, MaterialRef, ReviewRequestSpec, Reviewer, Selector, public views | схемы и DTO владельца; P05 подключает generated types |
| planning Specification.extension payloads, work_policy, read accessors сложных views | wire documents из specification schema; P05/P07 типизируют consumers |
| planning ValidationContext.settings, rebase schema issues | generated settings/schema representations, P05 |

`IsolationProfile` отсутствует в текущем kernel: поля группы используют `str`, а схемы
сохраняют четыре встроенных значения и `<plugin_id>:<name>` по E11/D-REG-6.
Единственный kernel type добавляет P01.01; группа P00.04.b не изменялась.
`DraftId` объявлен локально у Draft по общему правилу module-specific ID из kernel/ids.py;
остальные общие ID переиспользуются. Digest — строка `sha256:…`, не JsonObject.

Planning использует собственный Effort с `max` по `specification.v1.json#/$defs/effort`; runtimes — четыре значения своего каталога.
Общий более короткий перечень эти типы не объединяет: прав схема владельца. Типы не импортируются против графа; будущая
маршрутизация/семантическая валидация принадлежит P05/P08.

### 11.2 Схемы и ссылки

Схемы исходных четырёх каталогов перенесены по нормативным `$id`, включая плоские
command/query примеры в `commands/` и `queries/`. Finding catalog data лежат в
`planning/data/finding-codes.json`, а не выдаются за JSON Schema.
Добавлены отсутствовавшие command/result/query/view/event и host contracts по owner
таблицам; неизвестные полные формы остаются JsonObject, не фиктивными handlers.
Оригинальные schema constraints сохранены; к примерам добавлены недостающие description
и codegen metadata. Поля и ограничения авторского source, exact draft version,
one-of save forms, prepared publish digest и verification context сохранены.

Все `$ref` группы разрешаются локально в уже материализованных `src/skm/schemas/`;
**отложенных `$ref` у P00.04.c нет**. Будущие resource-kind manifest URN в
`extensions.domain.kinds.RESOURCE_KINDS` являются данными, не `$ref`:
`urn:skm:execution:workflow:v1` (P00.04.d),
`urn:skm:integrations:bundle:v1` (P00.04.e). Оба имеют нормативные examples-владельцы.
Общее замыкание всех групп только из src остаётся P00.04.f.

Проверки сохранены в `tests/contracts/policy/test_group_contracts.py`: импорты, manifests,
маркеры портов, inventory событий, Draft202012Validator.check_schema, каждый URN/fragment,
положительные/отрицательные примеры источника чтения, save forms, publish digest,
trust установки и force push intent. Это доказательство деклараций P00, не поведения M3.

Имена без полной структуры у владельца сохранены отдельными JsonObject aliases:
`policy.classify.OperationHit`, `shell_words.SimpleCommand`, `operations.StaticPathFacts`;
`extensions.skill.SkillFrontmatter`, `override_rules.OverrideDecision`, `upstream.UpstreamItem`;
`runtimes.routing.RouteCandidate`; `planning.identity.AssignedId`,
`id_space.IdSpaceDocument`, `work_policy.WorkPolicyOverride`. Это точки уточнения
соответственно P07.01/P10, P09, P08, P05; aliases не предоставляют поведения.

## 12. P00.04.d — context and execution contracts

This group declares contracts only. Concrete facade functions raise `NotImplementedError`;
command/query/subscriber/event/host-operation registrations are empty until generated DTOs and
the owning implementation leaves exist. No lifecycle, scheduler, Git, runtime, or research IO
is implemented. Module dependencies use the [module graph](layers-and-modules.md); the execution module names the same set.

### 12.1 Ports and ownership

| Module | Repository inventory | Gateway inventory |
|---|---|---|
| context | `ContextRepository`, `TextStore`, `ResearchRepository` | `ContextOwnerGuard (control plane)`, `MemoryRetriever (control plane)`, `CheckoutReader (host)`, `ResearchSource (host)`, `ResearchSourceRegistry (host)` |
| execution | `RunRepository`, `BundleRepository`, `ReadinessRepository`, `TaskRepository`, `AttemptRepository`, `StageRepository`, `StepRepository`, `AssignmentRepository`, `EnvironmentRepository`, `OutputRepository`, `CheckRepository`, `ReviewRepository`, `AcceptanceRepository`, `BudgetRepository`, `DecisionRepository`, `EffectRepository`, `IntegrationSlotRepository`, `ReviewRequestRepository`, `AutopilotRepository`, `RecoveryRepository`, `EvidenceBindingRepository`, `ExecutionQueries` | `ExecutionEnvironmentManager (host)`, `Vcs (host)`, `CheckRunner (host)`, `CheckRunnerRegistry (host)`, `IsolationRegistry (host)`, `Isolation (host)` |

`ContextOwnerClaim` contains only UUID assignment/attempt/worker identities and a fencing token.
`ContextOwnerGuard.require_current` is a control-plane gateway in the caller's UoW. Context has no
execution import: the future adapter delegates to `execution.public.require_current_context_owner`.
That facade takes the same primitive IDs, actor, owner_ref, and authoritative time; it does not commit.
The lock/authorization implementation and replay checks belong to P09.04.d/P07.05.

`StageDeps` contains exactly worker, environment, runtimes, check_runners, isolation, vcs, uploader,
config, clock, monotonic, log, and cancel. `RuntimeRegistry` is reused from runtimes.public; the older
`AgentRuntimeRegistry` spelling in execution prose maps to the canonical registry already declared
by P00.04.c (see §9). No duplicate runtime registry is created. `StageClient` exposes only progress,
seal_output, record_effect, acquire_integration_slot, and release_integration_slot. Stage handler
Protocol keeps the host `run(request, deps)` and control-plane `decide(request, ctx, uow)` signatures.
The six host stage declaration files use callable Protocols without executable `run` functions.

`host/registry.py` has an empty `tuple[HostOperationSpec, ...]` and an explicit operation-name inventory:
context research_query; execution worker_loop, clean_environments. P09.10 registers request_review. Constructing a bound
HostOperationSpec requires its generated request/result classes and callable implementation, so it is
left to the owner leaf rather than registering a placeholder callable. Worker stages are StageHandler
components, not separately registered HostOperationSpecs. Host files do not import UnitOfWork or
repository ports; stage files do not import HostContext, SkmClient, or application modules.
`CheckRunnerRegistry.get/kinds` and `IsolationRegistry.get/profiles` are minimal declaration APIs matching
the existing runtime/research registry style; component loading remains P01.10/P08.

### 12.2 Domain declarations and deferred Python wire types

Context declares the 24 ordered BlockTypes, budget/trust enums, BLOCK_SPECS/ROUND_TYPES, request and
runtime/permissions inputs, policy, draft/selection/finalization, host selectors/results/facts, manifests,
skill requests/entries, and research source/query/document/result/batch carriers. Execution declares run,
task, attempt, stage, step, assignment/lease, environment/output, checks/verdicts, reviews/findings/fix brief,
acceptance/deviation, budgets, decisions/effects/integration/carry-forward, blocking/recovery/autopilot,
workflow/actions/session/retry, work policy, risk, grouping, and coverage carriers. All concrete domain
entities are frozen dataclasses; domain code has no IO. Helper functions are fail-fast declarations.
Durable continuation is represented by distinct selected-stage and deferred-advance carriers; it does
not implement a dispatch queue, evaluator, migration, or admission guard.

Wire command/result/query/view/event classes are not hand-written in generated/. JSON Schema owns
these forms; codegen P01.05.a and the owner leaves will connect them to Python. Public read facades
therefore return JsonObject where they need future generated views. Settings modules expose only
section URNs, following the previous groups, until generated typed settings exist.

The following named metadata/helper inputs remain explicit JsonObject aliases. They are declaration
boundaries, not claims that the full behavior or adapter-specific representation exists. P07/P08 own
execution helpers and host contracts; P09 owns context assembly/research helpers. Page/Cursor are
placeholders for generated pagination views; Digest is a string. These aliases never create a new
permission, grant, result transition, or schema-registry behavior.

| Module | Deferred aliases in domain/contracts.py |
|---|---|
| context | `Candidate`, `Compatible`, `Diagnostic`, `Digest`, `DraftMeta`, `FindingItem`, `HostFactsMeta`, `MemoryHit`, `Page`, `RouteRecord`, `Selected`, `SelfLoadView`, `SkillSelectionTrace`, `SnapshotBlock`, `StoredResearchResult`, `Validated` |
| execution | `Ambiguous`, `AttemptView`, `AutonomyFactors`, `AutopilotStatusView`, `AvailabilityResult`, `BeginStageResult`, `BudgetEstimate`, `BudgetView`, `Cursor`, `DecisionPayload`, `DecisionRequestView`, `Diagnostic`, `EffectReconciliation`, `EffectRecordResult`, `EffectReport`, `EnvironmentView`, `ExecutionPolicy`, `Extracted`, `GateView`, `HealOutcome`, `HistoryCause`, `HistoryPage`, `LeaseSignal`, `Missing`, `NotHealable`, `OutputManifestDraft`, `Page`, `RangeSpec`, `ReadinessAudit`, `RebaseResult`, `RetainPolicy`, `ReviewReceipt`, `RunBudgetView`, `RunSummary`, `RunView`, `SealedOutput`, `SlotBusy`, `SlotLease`, `StageProgress`, `StepView`, `TaskContractRef`, `TaskView`, `TimelineEntry`, `Vote` |

Host operation request/result forms without a complete owner field table remain JsonObject schemas;
background/void command results whose wire payload is not specified also remain JsonObject rather than
inventing counters or success responses. Nested diagnostic, explanation, configuration, permission,
and read-model metadata uses JSON until connected to generated DTOs by its owner. Complete source
schemas retain their validation constraints. Domain carriers do not enforce lifecycle invariants yet;
those tests belong to M3 and the implementation leaves.

### 12.3 Schema inventory and reference closure

All context/execution examples are materialized by their canonical URN paths, including commands,
queries, event payloads, seven role results, workflow, stage outcomes, history, continuation, output/Git
publication definitions, and work policy. Missing command/result/query/view/host declarations are
added from context §§7–8 and execution §§7–9. Context assembly/draft/selection/finalized-context schemas
share context/defs; staged blob references use the existing artifacts defs owner. No schema is retrieved
from the network. Event schema URNs are also listed in domain/events.py; generated event classes and
manifest registration remain empty.

**Deferred $refs for this group: none.** Every target and JSON Pointer fragment resolves in the current
src/skm/schemas tree. Earlier groups' references to execution:defs are now materialized; the cross-group
inventory in §10.3 is historical and final closure still belongs to P00.04.f, using src only.

Q1 / RC-P00.04.d-01 was answered `a` by the coordinator: the researcher result follows context §5.14,
with the schema/status envelope (complete|partial|blocked), query, claims[].document_ids,
contradictions, unknowns, sources_used, and follow_up_queries.
The product schema preserves its URN, rejects the incompatible source_ids shape, and requires at least
one document per claim. No compatibility alias between source_ids and document_ids is assumed.
The read-only example is not modified by this leaf; the accepted answer is the authority for alignment.

Declaration tests are kept at src/skm/modules/execution/tests/test_contracts.py because the write set
contains only these modules/schemas and this document. They cover imports and complete manifest port
inventories, narrow StageDeps/StageClient, host import boundaries, schema syntax and reference fragments,
researcher positive/negative examples, worker claim/digest rejection, current context-owner claim,
and exclusive readiness selectors. They do not prove execution lifecycle behavior, runtime isolation,
process cleanup, authorization enforcement, or integration correctness.

RUN_TRANSITIONS, TASK_TRANSITIONS, ATTEMPT_TRANSITIONS, and AUTOPILOT_TRANSITIONS preserve the
owner transition rows as immutable TransitionDeclaration inventories (source/target descriptions and
rule IDs), rather than implementing transition guards. RESEARCH_LADDER declares the four source tiers.


### 12.4 Codegen symbol inventory and wire corrections

Host request/result symbols use Request, Result or Report suffixes. Query inputs keep
verb-based names; the corrected view outputs have independent Python and TypeScript symbols below.
URNs and payload property names are unchanged by these metadata corrections. The full-group collision
check also covers execution.host.request_review versus the RequestReview bus command: their different
forms must not share a TypeScript symbol. The host result uses RequestReviewReport to avoid the separate
bus result's RequestReviewResult symbol.

| Schema URN | Python class / TypeScript name |
|---|---|
| `urn:skm:context:host-result:research-query:v1` | `ResearchQueryResult` |
| `urn:skm:context:host:research-query:v1` | `ResearchQueryRequest` |
| `urn:skm:context:view:diff-contexts:v1` | `ContextDiffView` |
| `urn:skm:context:view:explain-context:v1` | `ContextExplainView` |
| `urn:skm:context:view:find-research-cache:v1` | `ResearchCacheView` |
| `urn:skm:context:view:get-context-text:v1` | `ContextTextView` |
| `urn:skm:context:view:get-research-query:v1` | `ResearchResultView` |
| `urn:skm:context:view:list-external-sources:v1` | `ExternalSourcesView` |
| `urn:skm:execution:host-result:request-review:v1` | `RequestReviewReport` |
| `urn:skm:execution:host:request-review:v1` | `RequestReviewRequest` |
| `urn:skm:execution:view:explain-autopilot:v1` | `AutopilotExplainView` |
| `urn:skm:execution:view:get-attempt:v1` | `AttemptView` |
| `urn:skm:execution:view:get-autopilot-status:v1` | `AutopilotStatusView` |
| `urn:skm:execution:view:get-fix-brief:v1` | `FixBriefView` |
| `urn:skm:execution:view:get-readiness-report:v1` | `ReadinessReportView` |
| `urn:skm:execution:view:get-review-receipt:v1` | `ReviewReceipt` |
| `urn:skm:execution:view:get-run-budget:v1` | `RunBudgetView` |
| `urn:skm:execution:view:get-run-health:v1` | `RunHealth` |
| `urn:skm:execution:view:get-run-timeline:v1` | `RunTimelineView` |
| `urn:skm:execution:view:get-run:v1` | `RunView` |
| `urn:skm:execution:view:get-step:v1` | `StepView` |
| `urn:skm:execution:view:get-task:v1` | `TaskView` |
| `urn:skm:execution:view:list-decision-requests:v1` | `DecisionRequestsView` |
| `urn:skm:execution:view:list-execution-environments:v1` | `ExecutionEnvironmentsView` |
| `urn:skm:execution:view:list-runs:v1` | `RunsView` |
| `urn:skm:execution:view:list-task-attempts:v1` | `TaskAttemptsView` |
| `urn:skm:execution:view:list-tasks:v1` | `TasksView` |

The get-run-history view's HistoryPage is an alias of the execution-history document; identical resolved
wire forms may retain one TypeScript symbol. Identical WorkerLoop and CleanEnvironments host forms also
retain their existing bindings. Tests reject different wire forms at the same (python.module, class) or
(typescript.file, name), and exercise that diagnostic with deliberately conflicting forms and a valid alias.

Wire corrections preserve the required researcher status; SealOutput declares executor/range and requires
a step only for executor; RenewLeaseResult admits the optional committed refusal and next instruction.
ResearchDocument locator values are JsonScalar (string/number/boolean/null), including inside ContextRequest
research blocks. Event stage_id and skipped_stage_ids are workflow string keys, while stage_record_id
remains a UUID. Positive and negative examples for these boundaries live in the scoped contract test file.
These declarations do not implement lifecycle, admission, or code generation.


## P00.04.e — integrations, knowledge, learning, exports

Declarations only: no command/query/subscriber/host implementation is registered. Event payloads are JSON
Schemas; `domain/events.py` inventories their URNs. Generated Python DTO/event classes and registrations
remain with codegen and the implementation owners (P10/P13). Optional modules are knowledge, learning, exports.
The manifest graph and settings section identifiers follow the [module graph](layers-and-modules.md); learning reuses knowledge's
lesson permissions rather than declaring duplicate permissions.

| Module | Repository ports (`@repository_port`) | Host gateways (`@host_gateway`) | Public facade |
|---|---|---|---|
| integrations | ProjectionRepository | IntegrationTarget, IntegrationTargetRegistry, CheckoutFs, UserHomeReader, HostCommandRunner | domain exports; no inter-module functions |
| knowledge | MemoryRepository, LessonRepository, GraphRepository | CodeGraphReader, ManifestReader | promote_lesson, deprecate_lesson, flag_lesson_decay, lesson_confidence_inputs, list_lessons_for_context, search_memory_for_context |
| learning | ActivityRecordRepository, CandidateRepository, SignalRepository, CandidateReviewRepository, CandidateProposalRepository | — | domain exports; no inter-module functions |
| exports | VaultNoteRepository | VaultFs | domain exports; no inter-module functions |

`CheckoutFs` has a single owner: `modules/integrations/ports.py`, referenced by kernel-platform §2.11a.
Writes/removals require the expected whole-file digest; `None` on write means create-only. Path-root and
symlink enforcement, locking and durability are adapter responsibilities; P00 declares their interface only.
`IntegrationTarget.summarize_session` returns a `JsonObject | None` wire activity summary: integrations does
not import optional learning against its dependency graph. Knowledge's candidate reference uses a primitive
UUID to avoid an upward import of learning. Named JSON carrier aliases in domain/contracts.py describe
unimplemented projections; they are not handwritten generated DTO classes. Repository Page/Cursor are
JSON/string declarations until their kernel owner materializes pagination.

Schemas are confined to `src/skm/schemas/{integrations,knowledge,learning,exports}/`. All references of this
slice resolve to materialized product schemas, including the execution JSON-value helper; the deferred
reference inventory for P00.04.f is **empty**. Schema syntax and every local/cross-schema JSON pointer are
checked in `tests/contracts/integrations/test_group_contracts.py`, with unknown-URN/fragment negative examples.
This is a declaration check and does not establish M3 behavior or replace the product SchemaRegistry.

Approved Q1 alignment: `knowledge/graph-answer.v1.json` follows knowledge §4.4/§8, including subgraph,
nullable repository/revision/generation/basis, and declared/text basis values. It retains its schema tag.
The copied host-command-output enum was narrowed to deny/ask/none as integrations §3/§4.10 require;
subscriptions cannot grant permission. Source examples remain read-only.

### Approved Q2 alignment — first-turn budget host contracts

The owner chose canonical request/result placement for `first_turn_budget`.
`integrations/host/first-turn-budget.v1.json` now declares
`FirstTurnBudgetRequest` with `project_id`, optional nullable `mount`, `target`, and `include_plugins`.
The report is materialized in `integrations/host-results/first-turn-budget.v1.json` as
`FirstTurnBudgetResult`, with `$id` and its required `schema` tag both equal to
`urn:skm:integrations:host-result:first-turn-budget:v1`. Both codegen declarations target
`skm.modules.integrations.generated.host`; the result no longer references the request schema.
No alternate request URN or executable HostOperationSpec is registered. Regression tests validate each
contract and reject swapped request/report bodies and the old report schema tag. Other copied host reports
(projection-plan, doctor-report, hook-decision) do not collide with their operation names.

The read-only source example still uses the old report URN. Q2 authorizes the product alignment;
synchronizing frozen source examples/spec references remains the coordinator's responsibility.

### Approved Q3 alignment and confirmed review corrections

Q3 confirms the first-turn verdict enum from integrations §5.7:
`ok`, `elevated`, `warn`, `incomplete`. The full result schema now accepts `elevated` for the example
`total=20000`, `target=16000`, `warn=23000`; legacy verdict spellings are rejected.

The confirmed F2–F5 corrections retain separate domain and wire contracts:

- Integration target fields reference `TargetId`, while `HookDecision.surface` references `HookSurfaceId`.
- `HookPolicyView.subscriptions` uses the flat `HostSubscriptionView` of integrations §5.8.5;
  internal `HookSubscription` retains its separate shape.
- `ProjectionInputs.host_subscription_events` is required, including an empty list when no registration
  is needed. Its named `HostSubscriptionEvent` entries carry `HookEventKind` and a tuple/list of `HookClass`.
- `CandidateReview.reviewer_kind` uses the kernel `PrincipalKind` values `human`, `service`, `worker`.

`tests/contracts/integrations/test_review_regressions.py` validates full consumer views and rejects invalid
enums, missing host subscription fields and the internal subscription shape at the host boundary. The F2
field checks enable JSON Schema format validation. The single independent review produced F1–F5;
these corrections are verified by executor tests and have not received a second independent review.


## 14. P00.04.f — adapter slots, surfaces and final closure

Technology and module package boundaries from tree.md are materialized. Technology-specific repository
and gateway classes are Protocol declarations inheriting the existing owning port signatures: they
cannot be instantiated and provide no fake production behavior. Memory and fake-runtime packages are
test slots. No SQL, IO, process launch, handlers, target factories, runtime factories, CLI groups, routes
or services are registered at import. CLI commands exports only CommandGroup and GROUPS=(); discovery
belongs to P02.08.a. The P00.01 CLI main and the excluded bootstrap modules/platform_module are preserved.

Only resource directory slots are created under resources/. P09.02.a/b supply the validated neutral core
pack, profiles, prompts, skills and workflows; P09.08 supplies templates. No invalid placeholder manifest
or active resource is bundled. Personal overlays remain outside core; wheel mapping is skm/_resources.

Bootstrap declares App/build_app, host construction, doctor checks, plugin loading and instance init.
Not-yet-declared owner types remain explicit object/JsonObject placeholders: Bus (P01.08.a),
SchemaRegistry (P01.04), HostServices/HostConfigSource and DoctorContext (P01.09.a), plugin
manifest/components/runtime data (P01.10), diagnostics (P01.02), bootstrap/invocation and init-report
DTOs (P01.05.a, P02.01, P03.07.a/b). Those owners narrow the same fields, without duplicate wire DTOs.
API ASGI binding belongs to P11.01.a. The hook/lifecycle files reserve their composition responsibility
for P10.05.a/b and P11.06.

RepositoryFactory's connection/state argument remains opaque until P01.08.b/P03.03.a; empty route
and built-in component tuples acquire Route/ComponentSpec from P11.02.a/P01.10. Shared bootstrap files
have the following contract prerequisites in addition to their leaf's declared dependencies:

| Shared file | Sequential implementation slices and prerequisites |
|---|---|
| bootstrap/composition.py | P02.08.a: CLI configuration with test composition; P03.03.c: real UoW, events and receipts from P03.03.a/b; P04.02.c: production RbacAuthorizer/Actor; P01.10: plugin data/phase-two settings after P03.03.c, P02.08.a and P04.04.a (which requires P04.02.c); P06.03.c: staged-blob client ports; P09.03: installed packs and pack-config source; P09.04.d: execution ownership facade and context transaction; P09.09.a: active research ownership and run-policy loader; P11.04.a: HTTP client/bootstrap credentials; P15.01.b: backup services |
| bootstrap/adapters.py | P02.08.a: memory repository contracts and P01.08.b factories; P03.03.a: PostgreSQL factories after scopes/DDL P03.02/P03.02.b |
| bootstrap/services.py | P01.09.b: ServiceRunner/BackgroundService; P07.06: scheduler, lease and timeout commands with system Actor |
| bootstrap/host_services.py | P01.09.a: HostServices, gateways and host-config source; P07.07.b: worker host/profile and stage ports; P11.04.b: authenticated HTTP worker/client |
| bootstrap/stage_broker.py | P07.05.a, P11.04.b, W03: private Unix socket for live assignment MCP access |
| background/outbox_relay.py | P03.05: UoW, event/outbox store and subscriber registry; P03.05.b: external-consumer delivery, retries and receipts |
| background/janitor.py | P03.05.b: idempotency/outbox/receipts; P06.03.d: staged-blob cleanup with digest guard; P13.04.a: enabled exports purge command |
| bootstrap/runtimes.py | P08.03 → P08.04 → P08.05 provider slices, each after AgentRuntime/CapabilityCatalog and the shared CLI session; P00 registers none |
| adapters/integrations/registry.py | P10.02 → P10.03 → P10.04.a → P10.04.b target slices, each after IntegrationTarget/TargetCapabilities and the render contracts; P00 registers none |

Artifact repository ownership is separate from prerequisites and neighboring files. P06.03.a owns
memory/artifacts/repositories.py after P06.01.b, P06.02 and P04.02.c. P06.03.b owns the PostgreSQL file
after P06.03.a, P05.05.a and P03.02.b. P06.03.c follows P06.03.b, P03.03.b, P03.03.c and P01.10;
it owns the two artifacts/blob_coordination.py adapters and its composition slice, not either
repositories.py file. Those prerequisites do not acquire write authority over the repository files.

Coordinator-transferred P00.04.d/F7 is closed: execution/domain/run.py exports typed fail-fast
start/pause/resume/cancel/finish and domain/task.py exports transition. Existing records, enums and
transition inventories are preserved. The pure functions return Run/Task and receive required timestamps
explicitly; no transition guards, clock, IO or handlers are implemented. Base transitions belong to
P07.02; later task extensions belong to P07.11, after the base state machine.

### 14.1 Import, graph and offline-reference proof

tests/architecture/test_contract_imports.py imports all 14 public.py/ports.py/module.py boundaries and
every materialized declaration without invoking handlers. It compares all actual ModuleManifest fields
with the catalog and an independent copy of the [module graph](layers-and-modules.md), validates the DAG and complete marked-port
inventory, and scans runtime, TYPE_CHECKING and relative imports for direct depends_on and public/ports
boundaries. Negative fixtures reject cycles, unknown/duplicate modules, private imports and transitive
dependencies. The six transferred execution functions are callable, fully annotated and fail fast.

The final schema registry uses **only src/skm/schemas/**, skipping data documents. It rejects duplicate
ids, checks Draft 2020-12 syntax and resolves every $ref/$dynamicRef and fragment with an explicitly
rejecting retrieve callback. Negative fixtures reject missing URNs, missing fragments and HTTP targets;
an escaped JSON Pointer has a positive fixture. All eight historical source/target pairs in §10.3
are **closed** by the materialized P00.04.c-e owners. No deferred references remain. Neither examples nor
network retrieval enter this final registry. This smoke proves declarations, not P01 SchemaRegistry
behavior or the M3 execution lifecycle.

The actual manifests are imported directly from their owners in the smoke test. MANIFESTS and module
selection behavior in the bootstrap/modules.py were implemented by P02.08.a (`MANIFESTS` loads the owners' `MODULE`s); no parallel
production manifest registry is introduced. tree.md names pack_reader.py while the short layout says
pack_loader.py; the declaration uses the detailed tree's existing path and P09.01.b owner. Grok/Cursor
runtime.py are declared from adapters §5.1; P08.05 owns both providers (tree's runtime argv tests and
bootstrap/runtimes.py).

### 14.2 Complete materialized-file inventory

Each row names a real file, its declared contracts and sequential owners. The first P00 leaf declares
the file; subsequent leaves implement or refine it in their dependency order. Owners come from tree.md;
group IDs are expanded to the explicit child leaves present there. The original P03.02/P03.05 leaves
remain distinct from their separately named .b extensions (tree.md; E23 for scopes/DDL). Carrier-only files follow the
module's owning public/ports contracts; host registry carriers follow their host-operation owners.
Canonical schema results and views follow the command/query leaf; shared definitions and event payloads
follow their owner's contract leaves. Package-only rows end with P00.04.f because future logic belongs
to the descendant implementation files. This inventory covers the materialized skeleton, not every
future implementation file or resource. Shared-file rows retain all sequential owners; a leaf implements
only its assigned responsibility after its declared prerequisites.

| Materialized file | Contracts | Declaration → implementation/refinement leaves |
|---|---|---|

### P01.05.a: generated contracts

`make gen` runs the independent stdlib error catalog emitter and the schema parse/model/Python/TypeScript pipeline. The original schemas remain the runtime validation authority; generated converters enforce conversion shape without a global registry. Recursive TypeScript maps use readonly index signatures, equivalent to `Readonly<Record<string, T>>`. The full current schema snapshot and all frozen examples/documents are retained by URN in `tests/fixtures/codegen/current-corpus/`.

## P10.05.a — hook policy and host boundaries

| File | Contract | Owner |
|---|---|---|
| `src/skm/modules/policy/domain/managed_guard.py` | candidate_paths, managed_hit; pure reserved/managed path checks | P10.05.a |
| `src/skm/modules/policy/domain/changelog_gate.py` | RELEASE_TYPES, RULES, changelog_gate_verdict | P10.05.a |
| `src/skm/modules/integrations/application/queries/get_hook_policy.py` | Project-authorized policy snapshot and generation | P10.05.a |
| `src/skm/modules/integrations/host/hook_state.py` | HookState host gateway for cache, checkout facts and audit IO | P10.05.a |
| `src/skm/adapters/git/hook_state.py` | LocalHookState; private TTL cache, staged output digest, idempotent audit spool | P10.05.a |
| `src/skm/adapters/git/identity_proof.py` | IdentityProofCache; few-second memory of a plain checkout's identity proof, keyed by file stamps | P10.05.a |
| `src/skm/entrypoints/cli/commands/hook.py` | Native hook command forwarded to the shared bootstrap profile | P10.05.a |

`HookPolicyView.changelog.changelog_paths` carries every configured changelog file.
Any staged member satisfies the changelog gate. The optional field preserves reads of
older cached policies through their existing singular `changelog_path`; generated clients
must be refreshed for the extended closed output contract before release 2.0.0.
