# Manual status

Executor validation and independent manual review are separate facts.
Update a row only with actual commands/results and reviewer identity/outcome.
An assignment or recommendation does not count as a completed review. This table
does not replace the coordinator's execution queue.

## Foundation documentation

| Item | Executor checked | Commands | Result | Reviewed | By | Outcome |
|---|---|---|---|---|---|---|
| P00.06 | Yes, targeted validation | `uv run --frozen pytest -q tests/unit/test_check_links.py`; Ruff checks for the two Python files; targeted Pyright for tool and tests; `git diff --check` | 12 tests passed; Ruff and targeted Pyright clean; acceptance belongs to conductor | No | — | Not conducted |

The current `make check` includes
`fmt-check lint typecheck test arch docs-check schema-check` (P01.05.b is now
materialized). `make docs-check` checks local Markdown destinations and heading
anchors, including generated reference pages. The P00.06 handoff above remains
historical executor evidence; it does not establish independent review.

## P00.Z executor validation

Recorded on 2026-10-27 against revision
`f949180406142b59e601cdad59fd9893f1d53439`. The source checkout was clean before
this documentation change. A separate temporary clone under
`/tmp/skm-p00z-3Jumyr/checkout` had an empty `git status --porcelain=v1` before
installation; it contained the same revision, with no donor or legacy checkout.
Commands below ran from that clone unless stated otherwise. uv used temporary
cache and Python-install directories under `/tmp/skm-p00z-3Jumyr`.

**Executor result: done pending integration checks. Independent manual review:
not conducted; no reviewer or accepted review is asserted. Phase readiness is
not asserted.** The coordinator owns V1/V2 and the acceptance result.

### Executed checks

| Command or procedure | Actual result | What it establishes |
|---|---|---|
| `uv sync --frozen` | Exit 0; Python 3.12.3; 30 packages installed, including editable `skm==2.0.0.dev0` | Locked installation from the root of a clean temporary checkout |
| `uv run --frozen pytest -q tests/architecture/test_contract_imports.py` | Exit 0; 35 passed | All materialized declarations import; 14 actual manifests match the canonical graph and port inventory; no unfinished handlers, routes, factories or services are registered; adapter declarations cannot be instantiated |
| Same declaration test file, offline schema cases | Included in the 35 passed above, not a second run | Draft 2020-12 syntax and local reference closure using only product schemas, with duplicate IDs, missing URNs/fragments and remote retrieval rejected |
| `uv run --frozen pytest -q tests/unit/test_package_version.py` | Exit 0; 5 passed | Installed CLI/package version agreement, isolation from another CLI in PATH, and rejection of unsupported arguments |
| Inventory and cross-phase inspection described below | 42 module boundaries present in inventory and TARGET-TREE; seven sampled consumer routes imported | Declaration coverage and public facade availability; no behavior invoked |

The schema inspection counted **784 schemas**, **2 excluded data documents** and
**3,084 `$ref`/`$dynamicRef` occurrences**. The declaration test resolves references
without adding example schemas or network retrieval. This does not prove the
future P01 SchemaRegistry implementation.

### Inventory and consumer inspection

TARGET-TREE means the intended file tree; CONTRACTS means the interface catalog.
Compared them with the [materialized contract inventory](architecture/contracts.md),
the [module graph](architecture/layers-and-modules.md) and actual module declarations
under [`src/skm/modules/`](../src/skm/modules/). All 14 owners were inspected: `access`,
`settings`, `workspace`, `artifacts`, `policy`, `extensions`, `runtimes`,
`planning`, `context`, `execution`, `integrations`, `knowledge`, `learning`,
`exports`. Their `module.py`, `ports.py` and `public.py` account for 42 boundaries;
only `knowledge`, `learning` and `exports` are optional. The inventory lists
1,502 unique materialized product/resource paths; TARGET-TREE lists 2,751 future
target paths. Those counts describe different sets and do not imply that every
future implementation file exists.

The supplementary catalog inspection imported 122 materialized Protocol owners
and checked every member listed for them in CONTRACTS; none was missing. One
catalog file is absent: `src/skm/adapters/runtimes/_cli_session/stream_parser.py`.
An initial all-catalog import attempt exited 1 with `ModuleNotFoundError` for
that module. A subsequent inventory procedure continued through the catalog to
enumerate gaps and found this one absent file, without treating it as a passed
import. The existing inventory §7.2 assigns the internal `StreamParser` contract
to **P08.02.b**. The adapter notes §§5.1–5.2 specify
`stream_parser.py` separately from `stream.py` (`StreamTail`); the session code is
[`adapters/runtimes/_cli_session/`](../src/skm/adapters/runtimes/_cli_session/). TARGET-TREE lists
`stream.py` but omits `stream_parser.py`. The inventory's shorthand pairing of
these paths therefore does not establish an equivalent implementation. The
coordinator should carry this exact path mismatch to the P08.02.b owner and
reconcile the frozen inputs before that implementation. No adapter was added
under this documentation-only scope, and full catalog importability is not
claimed.

Sample imports were compared with conventions §7 and inventory §8:

| Consumer → owner | Imported public symbols |
|---|---|
| planning → workspace | `require_active_project`, `project_mounts` |
| planning → artifacts | `require_ready_versions`, `latest_ready_version` |
| execution → planning | `get_revision_specification`, `compile_execution_graph`, `publish_review_request_revision` |
| execution → runtimes | `admit`, `route_role` |
| execution → context | `assemble_draft`, `require_final` |
| learning → knowledge | `promote_lesson`, `deprecate_lesson` |
| exports → execution | `get_run_report_data`, `latest_run_outcome` |

Each symbol was callable and named in both inventories. Calls were not made:
P00 declares these interfaces, and implementation remains with their leaf
owners. An AST inspection of all **705 product Python files** found no imports
from the legacy package roots or `packages`, `bridges`, `v2`. Actual manifests
were imported directly from their owning modules; `MANIFESTS` and module
selection in `bootstrap/modules.py` remain with P02.08.a, as inventory §14.1
already records.

### Unavailable targets and pending proofs

Each target below was invoked separately in the temporary checkout. Every one
printed `skip:`, its recipe exited **3**, and GNU make exited **2**. None counts
as passed or as a schema/generator/web behavior check.

| Invoked command | Owning implementation |
|---|---|
| `make gen` | P01.05.a |
| `make schema-check` | P01.05.b |
| `make schema-lock` | P01.05.b |
| `make web-check` | P12.01.a |
| `make web-dev` | P12.01.a |
| `make web-build` | P12.01.a |

The available `make check` prerequisites are
`fmt-check lint typecheck test arch docs-check`; schema-check is added only
after P01.05.b. The executor did **not** run `make check` or its complete suites,
nor the withheld V1/V2 commands: they belong to the conductor. Docker and
container startup are prohibited in this execution environment, so `make db-up`
and `make doctor` were not run. PostgreSQL connectivity, `make test-pg` and the
complete clean-machine integration chain remain unproved here. These are
pending checks, not successful skips. `test-pg`, `e2e`, `evals` and `perf` are
real pytest targets, not the unavailable stubs above; their suites were not run.

Only `docs/status.md` is changed for P00.Z. No queue, plan, donor, legacy or
`v2/` files are modified, and no commit or review-status transition is made.
Final checks in the source checkout:
`.venv/bin/python tools/check_links.py docs/status.md` and `git diff --check`
both exited 0. `git status --short` showed only `M docs/status.md`.

## P01.Z executor validation

Recorded on 2026-10-27 against revision
`967d21e38a81d737d6f3d97939d5b442c6bc6b49`. The checkout was clean before this
documentation change. The candidate now changes the two documentation files and
nine explicitly authorized source/test/fixture paths, including the typing and
snapshot repairs detailed below. No paths outside the current eleven-path write
set are changed.

**Conductor V1 checks.4: exit 0 for `make gen check`: 2,930 tests passed,
1 deselected, 282 subtests passed, and the separate architecture suite passed
334 tests. Automatic independent review of checkpoint `601140a3fc7c` by
Claude Opus/high returned GREEN with no findings and one documentation question.
This factual documentation update was made after that review and was not reviewed
again. Separate manual review: not conducted; outcome: not asserted.**
No product runtime, provider CLI, container, donor command or external service was
started. This record does not assert phase readiness or an accepted review.

### Executed foundation checks

All `uv` commands below used `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache` and the frozen
project environment (Python 3.12.3). These are focused diagnostics, not V1 or a
substitute for the conductor's regression gate.

| Command or procedure | Actual result | Coverage and limits |
|---|---|---|
| `uv run --frozen python tools/gen.py --check` | Exit 0 | Read-only comparison of Python, TypeScript, error catalog and reference-document outputs against current generator inputs; no generated file was rewritten |
| `uv run --frozen pytest -q tests/unit/platform/jsonc/test_digest.py` | Exit 0; 47 passed | All eight digest/v1 vectors, byte-identical fixture provenance, recursive key permutations, explicit exclusions, invalid input and exact tagged-digest syntax |
| `uv run --frozen pytest -q tests/architecture/test_contract_imports.py tests/unit/application_bus/test_host.py tests/unit/application_bus/test_bus_dispatch.py` | Exit 0; 69 passed | Declaration imports and offline schema closure; canonical dependency graph/public facades; gateway-kind refusals; host surface/name/resource lifetime; atomic memory command effects, authorization before replay, rollback and result validation |
| `uv run --frozen pytest -q tests/unit/platform/process/test_runner.py::test_explicit_env_cwd_literal_argv_and_stdin tests/unit/platform/process/test_runner.py::test_output_flood_and_large_input_do_not_deadlock tests/unit/platform/process/test_runner.py::test_timeout_and_normal_exit_kill_remaining_writers` | Exit 0; 4 passed | Local Python subprocesses only: explicit environment and literal argv, bounded pipe capture, timeout and leader-exit cleanup of descendant writers |
| `uv run --frozen pytest -q tests/unit/tools/test_schema_check.py::TestDirection tests/unit/tools/test_schema_check.py::test_generated_drift_fails_without_writing_or_updating_lock tests/unit/tools/test_schema_check.py::test_lock_round_trip_is_deterministic_and_contains_snapshots tests/unit/platform/fs/test_atomic_write.py::test_faults_never_report_success_and_cleanup_preserves_primary tests/unit/platform/fs/test_safe_paths.py::test_symlink_policy_always_checks_resolved_containment` | Exit 0; 24 passed | Input/output compatibility direction; six generated-drift negative cases preserve edited bytes and lock; deterministic lock; eight injected write failures; contained/escaping symlinks with both policies |
| Read-only catalog/import/AST inspection and consumer matrix below | Passed, with the deferred catalog gap below | 122 existing catalog owners expose every listed member; 39 consumer Protocol references resolve; seven unique context/gateway declarations; zero legacy imports in 878 product Python files |

### P02–P10 consumer inventory

Compared [contract inventory](architecture/contracts.md) §§5–8 with
the interface catalog, the name and graph rules in [layers and modules](architecture/layers-and-modules.md), and the imported owners.
The matrix checks declarations and Protocol identity, not downstream execution.

| Consumer phase | Canonical owners and verified Protocol references |
|---|---|
| P02 configuration | `platform.config.store`: `ConfigStore`, `ScopeTree`, `PackConfigSource`; `platform.config.secrets`: `SecretResolver` |
| P03 storage and relay | `kernel.ports_uow`: `UnitOfWork`, `UnitOfWorkFactory`; `application_bus.ports`: `IdempotencyStore`, `AuditLog`, `EventReader`, `OutboxStore`, `ConsumerReceipts` |
| P04 access and workspace | `application_bus.ports`: `Authorizer`, `ScopeChainResolver`; `modules.workspace.ports`: `ProjectRepository` |
| P05 planning | `modules.planning.ports`: `PlanRepository`, `DraftRepository`, `RevisionRepository`, `PlanningQueries` |
| P06 artifacts | `modules.artifacts.ports`: `BlobStore`, `BlobCoordination`, `MaterialWriter` |
| P07 execution | `modules.execution.ports`: `StageHandler`, `StageClient`, `ExecutionEnvironmentManager`, `Vcs`, `CheckRunner` |
| P08 runtimes | `modules.runtimes.ports`: `AgentRuntime`, `RuntimeRegistry`, `CapabilityCatalog` |
| P09 context | `modules.context.ports`: `ContextOwnerGuard`, `MemoryRetriever`, `CheckoutReader`, `ResearchSource`, `ResearchSourceRegistry` |
| P10 integrations | `modules.integrations.ports`: `IntegrationTarget`, `IntegrationTargetRegistry`, `CheckoutFs`, `UserHomeReader`, `HostCommandRunner` |

The AST inspection found exactly one declaration each of `CommandContext`,
`QueryContext`, `SubscriberContext`, `ExternalConsumerContext` in
`application_bus/context.py`, `HostContext` in `application_bus/host.py`, and
`Gateways`/`GatewayTable` in `kernel/gateways.py`. All five gateway-bearing
contexts reference that same `Gateways` Protocol. `StageDeps.worker` references
the execution-owned `StageClient`; there is no second host context or gateway
container. The cross-module import test covers direct dependencies and public
facades; the inspected import roots included `aicore`, `planner`, `orch`,
`runtimes`, `packages`, `bridges`, `v2` and `swissknifeman`.

### Limits and coordinator handoff

- The executor did not run `make gen check`, its complete suites or V1, as required
  by this execution's verification instructions. The conductor's first V1 attempt
  stopped at fmt-check. Its second attempt stopped at typecheck; the third passed
  formatting, lint and both Pyright configurations but stopped at one corpus
  snapshot test. Each correction's evidence is recorded below. The executor has not
  rerun the full gate. Neither green `make check` nor complete runtime-test coverage is
  inferred from these focused results. All subprocesses actually exercised here
  were local test programs; declaration imports did not invoke provider runtimes.
- The existing P00.Z gap remains: catalog `StreamParser` at
  `src/skm/adapters/runtimes/_cli_session/stream_parser.py` is absent, assigned to
  P08.02.b in inventory §7.2. It is excluded from the 122 successful owner
  imports, not silently mapped to `stream.py`. No new implementation is claimed.
- Inventory §6 schedules narrowing `HostContext.config/log` to
  `EffectiveConfig`/`StructLogger` in P01.09.a, matching
  the kernel-platform host-context note §4.2a. Host types live in
  [`application_bus/host.py`](../src/skm/application_bus/host.py).
  Actual annotations remain `object`; `HostServices.host_config/log_factory`
  likewise return `object`. This limits static contract precision and needs
  coordinator follow-up with that owner; the gateway identity and tested host
  routing behavior above do not prove this narrowing. The later formatting and
  typing scope extensions do not authorize changing that host implementation.
- An initial `.venv/bin/python` introspection procedure exited 1 when
  `get_type_hints(StageDeps)` tried to resolve the `TYPE_CHECKING`-only
  `PreparedEnvironment`. The catalog and AST results had already completed.
  A corrected procedure used unevaluated annotations for `StageDeps.worker`
  and checked its owning Protocol; it exited 0. This was a diagnostic limitation,
  not evidence of a product import failure.
- The original phase's `docs/dependencies.md` update is outside this leaf's
  write set, whose extensions add only the named source/test repair paths, and was not performed.
  No queue, plan, generated
  output, schema lock or donor file was changed; no commit was made.

Port provenance and retained invariants are recorded in the
[P01.Z porting entry](porting-log.md#p01z--foundation-contract-verification).
Documentation checks: `.venv/bin/python tools/check_links.py docs/status.md docs/porting-log.md`
and `git diff --check` both exited 0; the candidate diff contains only the eleven
authorized paths.

### Correction round executor.2: V1 formatting failure

The conductor reported V1 exit **2** for `make gen check`. Its log records
`tools/gen.py` followed by Ruff fmt-check, which rejected the tuple assertion in
`tests/unit/application_bus/test_registry.py:233` (the assertion starts at line
233 in the current source). The remaining `make check` prerequisites were not
established by that attempt. Evidence supplied by the conductor:
`.swissknifeman/state/orch/conductor/cnd-20261027T183724Z-3804c1/P01.Z/checks/1/V1.log`.

Initial focused reproduction, before the scope extension:
`UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen ruff format --check --diff tests/unit/application_bus/test_registry.py`
exited **1**, reporting exactly one formatting change: expand the two-line
one-element tuple assertion into the formatter's multiline form. At that point
the working file had no diff against HEAD;
`git show HEAD:tests/unit/application_bus/test_registry.py` contained the same
unformatted assertion. That red predated this leaf's documentation changes and
was outside its initial write set; it was not a generated-file or environment
failure.

The initial correction handoff was blocked by the documentation-only scope. The
current input explicitly adds `tests/unit/application_bus/test_registry.py`.
On entry to this resumed correction, the working tree already contained the
required multiline assertion and an import-order adjustment. Both were preserved;
the scoped formatter reported `1 file left unchanged`. No test expectation,
production behavior, schema, generated output or acceptance command was changed.

| Correction command | Actual result |
|---|---|
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen ruff format tests/unit/application_bus/test_registry.py` | Exit 0; 1 file left unchanged |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen ruff format --check tests/unit/application_bus/test_registry.py` | Exit 0; 1 file already formatted |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen ruff check tests/unit/application_bus/test_registry.py` | Exit 0; all checks passed |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen pytest -q tests/unit/application_bus/test_registry.py` | Exit 0; 43 passed |

**Formatting correction status: verified before the second conductor attempt.** The prior exit-1
focused reproduction and conductor exit 2 remain historical failures, not current
successful gate results. The 144 earlier focused tests were not repeated; these
43 registry tests and scoped format/lint checks establish the corrected file's
current state. The second conductor attempt exposed the typecheck failure below;
documentation checks remain separate from acceptance.

### Correction round executor.3: V1 typecheck failure

The conductor's `checks.2` V1 exited **2**. Its full log records successful
generation, formatting (`853 files already formatted`) and lint, followed by
**45 Pyright errors**. Typecheck stopped the gate; later prerequisites have not
been established by that attempt. Supplied evidence:
`.swissknifeman/state/orch/conductor/cnd-20261027T183724Z-3804c1/P01.Z/checks/2/V1.log`.

Focused reproduction, without the full acceptance suite:
`UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen pyright --outputjson src/skm/adapters/memory/uow.py src/skm/application_bus/registry.py tests/architecture/test_contract_imports.py tests/contracts/core/test_memory_uow.py tests/support/app.py tests/unit/application_bus/test_host.py tests/unit/bootstrap/test_host_services.py`
exited **1**: seven files analyzed, 45 errors, zero warnings. Its diagnostic
locations/rules match the conductor's report. Output was summarized in the
execution response; no raw transcript or new artifact was added to product files.

| Write path added for the repair | Original errors / locations | Diagnosed mismatch and invariant to preserve |
|---|---|---|
| `src/skm/adapters/memory/uow.py` | 3; 113, 159, 178 | Cross-class protected helper calls (`_buffer_outbox`, `_opened`, `_closed`); retain UoW locking, lifecycle accounting and outbox buffering behavior |
| `src/skm/application_bus/registry.py` | 2; 393 | Pyright already narrows the event candidate despite its `object` annotation; retain runtime rejection of invalid event classes while correcting the static typing |
| `tests/architecture/test_contract_imports.py` | 1; 389 | Helper annotates the imported module as `object` but reads `__all__`; retain adapter export/ownership assertions |
| `tests/contracts/core/test_memory_uow.py` | 32; 655–656 | Recursive `JsonValue` is indexed/mutated without narrowing container types; retain both nested mutations and the history-copy isolation assertion |
| `tests/support/app.py` | 1; 127 | `MemoryTestApp` does not meet writable/invariant `TestApp` attributes declared as `object`, including a read-only `state` implementation; align the test-only structural contract without hiding the incompatibility |
| `tests/unit/application_bus/test_host.py` | 1; 77 | Helper expects `dict` but receives `HostServices.operations: Mapping`; preserve the host-surface refusal case |
| `tests/unit/bootstrap/test_host_services.py` | 5; 26, 28, 78, 88, 97 | Unnecessary type-ignore comments; preserve bootstrap operation/host-id test behavior |

At initial diagnosis, all seven files matched HEAD and were outside the then
three-path write set. The coordinator subsequently added all seven paths and
authorized minimal typing repairs. The resumed input tree already contained
the registry/test typing changes and a UoW helper-name repair; those test changes
were preserved. The UoW repair was refined to avoid adding public helper methods:
the enqueuer receives the bound private buffer callback, while active/peak counts
are updated directly in the same locked lifecycle positions. Rollback, readonly
refusal, outbox buffering and lock lifetime retain their existing checks.

The registry keeps its runtime `isinstance`/`issubclass` guard and widens the
untrusted candidate through `cast("object", event)` for the static checker.
The negative registration test now also includes a non-class string alongside
the valid `Echoed` event. The other repairs retain their original assertions:
module exports use `vars(module)["__all__"]`; nested JSON containers are narrowed
with `isinstance` before both mutations; `TestApp` exposes read-only dependency
properties; the host test helper accepts `Mapping`; five unnecessary bootstrap
test ignore comments are removed. No blanket ignore, checker configuration,
generated output or expected product result was changed.

| Repair command | Actual result |
|---|---|
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen ruff format src/skm/adapters/memory/uow.py src/skm/application_bus/registry.py tests/architecture/test_contract_imports.py tests/contracts/core/test_memory_uow.py tests/support/app.py tests/unit/application_bus/test_host.py tests/unit/application_bus/test_registry.py tests/unit/bootstrap/test_host_services.py` | Exit 0; 1 file reformatted, 7 unchanged |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen pyright src/skm/adapters/memory/uow.py src/skm/application_bus/registry.py tests/architecture/test_contract_imports.py tests/contracts/core/test_memory_uow.py tests/support/app.py tests/unit/application_bus/test_host.py tests/unit/application_bus/test_registry.py tests/unit/bootstrap/test_host_services.py` | Exit 0; 0 errors, warnings or information diagnostics |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen ruff check src/skm/adapters/memory/uow.py src/skm/application_bus/registry.py tests/architecture/test_contract_imports.py tests/contracts/core/test_memory_uow.py tests/support/app.py tests/unit/application_bus/test_host.py tests/unit/application_bus/test_registry.py tests/unit/bootstrap/test_host_services.py` | Exit 0; all checks passed |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen pytest -q tests/contracts/core/test_memory_uow.py tests/unit/application_bus/test_registry.py tests/unit/application_bus/test_host.py tests/unit/bootstrap/test_host_services.py tests/contracts/test_harness_declarations.py tests/unit/application_bus/test_bus_dispatch.py tests/unit/application_bus/test_bus_ask.py tests/architecture/test_contract_imports.py` | Exit 1; 187 passed, 1 failed: the newly added invalid-event fixture omitted the valid event required by its subscriber |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen pytest -q tests/unit/application_bus/test_registry.py` | Exit 0; 43 passed after retaining `Echoed` in the invalid-event fixture |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen pyright tests/unit/application_bus/test_registry.py` | Exit 0; corrected fixture has 0 diagnostics |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen ruff check tests/unit/application_bus/test_registry.py` | Exit 0; corrected fixture passes lint |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen ruff format --check src/skm/adapters/memory/uow.py src/skm/application_bus/registry.py tests/architecture/test_contract_imports.py tests/contracts/core/test_memory_uow.py tests/support/app.py tests/unit/application_bus/test_host.py tests/unit/application_bus/test_registry.py tests/unit/bootstrap/test_host_services.py` | Exit 0; 8 files already formatted |

**Typing correction status: scoped repairs complete.** The
combined focused run passed all 145 tests outside the registry file; after the
fixture correction, all 43 registry tests passed. That establishes 188 affected
test cases across the recorded runs, not a successful rerun of the combined
command or full acceptance. Coverage includes UoW rollback/readonly/nested-entry
and outbox cases, nested payload copy isolation, invalid event classes/instances,
the memory TestApp consumer, host routing, direct bus consumers and architecture
import/export boundaries. No product runtime or service was started. The last
conductor typecheck was subsequently confirmed green by checks.3, which then
stopped at the snapshot test below. Independent review of these repairs is not
asserted.

### Correction round executor.4: corpus snapshot failure

The conductor's `checks.3` V1 exited **2** after generation, format/lint and both
Pyright configurations passed. Its test result was **1 failed, 2,929 passed,
1 deselected, 282 subtests passed**. The single failure was
`tests/unit/tools/test_gen.py::test_current_and_example_corpus_are_complete_snapshots`
at line 197. The later architecture/docs/schema-check gate steps were not reached
in this attempt. Supplied evidence:
`.swissknifeman/state/orch/conductor/cnd-20261027T183724Z-3804c1/P01.Z/checks/3/V1.log`.

Focused reproduction:
`UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen pytest -q tests/unit/tools/test_gen.py::test_current_and_example_corpus_are_complete_snapshots`
exited **1**, reproducing the same snapshot mismatch without rerunning the suite.
A read-only structural comparison found 784 schemas in both the product and
`tests/fixtures/codegen/current-corpus/schemas.json`, with no missing/extra URNs
and 783 identical documents. The sole difference is
`urn:skm:kernel:event-envelope:v1` at `properties.stream_kind.enum`: the fixture
has 14 values and lacks `runtime`, `hook_delivery`, `vault_note`; current
`src/skm/schemas/kernel/event-envelope.v1.json` has all 17.

The current schema enum matches [`STREAM_KINDS`](../src/skm/kernel/events.py)
(closed stream-kind set, conventions §4.0.1).
This was stale test-fixture data, not a reason to shrink the canonical enum or
relax the snapshot assertion. At initial diagnosis neither the schema nor this
snapshot had a diff against HEAD; the mismatch predated this leaf's changes.

The rest of the failing test was inspected without bypassing its assertion:
`examples.json` matches all 135 example schemas, `documents.json` matches its two
example documents, example URNs remain a subset of product URNs, and normalizing
the current product corpus leaves no missing declared codegen root. Those are
separate diagnostic observations, not a passed snapshot test or accepted fixture
update.

The initial scope block requested only
`tests/fixtures/codegen/current-corpus/schemas.json`; the resumed input explicitly
authorized that path and supplied the corrected fixture. It was preserved.
Comparison with HEAD confirmed exactly one changed schema object and one changed
field: `properties.stream_kind.enum` in `urn:skm:kernel:event-envelope:v1` grows
from 14 to 17 values by appending `runtime`, `hook_delivery`, `vault_note` in the
same order as the accepted product schema. All 783 other snapshot objects and all
other fields in the envelope entry remain identical to HEAD. The textual diff
is four added lines and one removed line at the array tail; it does not reformat
the corpus. No `examples.json`, `documents.json`, product schema, schema-lock,
generated output, generator, checker configuration or test assertion was changed.

| Snapshot correction check | Actual result |
|---|---|
| Structural comparison of the incoming fixture with HEAD plus only the three authorized enum members | Passed; exactly the authorized update, no other schema-object or field changes |
| `UV_CACHE_DIR=/tmp/skm-p01z-uv-cache uv run --frozen pytest -q tests/unit/tools/test_gen.py::test_current_and_example_corpus_are_complete_snapshots` | Exit 0; 1 passed in 0.80s; the unchanged test exercises current/example/document completeness and codegen declaration coverage |

**Current correction status: snapshot repair verified; conductor checks.4 V1
passed `make gen check` with exit 0.** The original failing reproduction and
checks.3 exit 2 remain historical results. The earlier single-test run is not
itself the full gate; checks.4 supplies that later evidence.
All earlier repairs and review/follow-up limits are retained; no product runtime
was started and independent manual review remains not conducted.

### Independent automatic review and its limits

Claude Opus/high completed review.1 on checkpoint `601140a3fc7c`: GREEN, zero
findings, one question about the stale V1 text corrected here. The reviewer did
not verify every runtime process machine-wide; four process-runner cases and the
executor's report are the available evidence. Counts of 122 catalog owners, 39
Protocol references and 878 files were accepted largely on trust apart from
sampled consumer interfaces. The missing StreamParser (P08.02.b) and
HostContext config/log annotations remain open. This update was not part of the
reviewed checkpoint and has not received a second review. Separate manual review
was not conducted.

### External P01 follow-up register

Read-only source supplied by this execution input:
`/home/vostrikov/.local/state/skm-plan-runner-remediation-20261026/review-followups.json`.
Its observed SHA-256 matched the supplied value
`b05f30f55d254dc2c1be5b0fa988a1ed0a969fd9aed34b36539f057d1a6281ad`.
This is historical review/follow-up evidence, not a new normative contract.
`closed: false`, a recorded question, or a previous review finding does not by
itself establish a current defect. No follow-up was closed or promoted into a new
implementation requirement by this documentation correction.

| Leaf / journal entries (`items` indices) | Recorded disposition and retained limits |
|---|---|
| P01.01/.02/.04 (9, 10, 12) | Journal marks confirmed findings closed after corrections and coordinator checks. Those corrections did not receive another independent review. Historical check results are not this P01.Z candidate's V1 result. |
| P01.03 (11) | Provenance finding is recorded corrected; the earlier P01.Z digest tests independently passed the local fixture/provenance cases. Decimal precision versus `normalize()` wording and public exports remain owner follow-up questions; the eight passing vectors do not settle those questions. |
| P01.05.a/.05.b (13, 14) | .a is recorded closed with F1/F2 corrected and F3/F4 rejected; its old class-name/missing-catalog questions are retained as journal context, not reopened findings. .b records restored compatible exports and passing original reproductions, while tooling §7 naming of foreign local copies remains open. No repeat independent review of these corrections is recorded. |
| P01.06.a (15) | Journal reports corrected findings and GREEN from both reviewers in round 2. Whether operational sink failures may interrupt callers and how unregistered SKM token patterns are handled remain questions, not defects demonstrated in this round. |
| P01.06.b (16) | Correction and tests are recorded; no further independent review. Suitability of the fixed one-second storage ledger lock timeout on slow/contended storage remains open. |
| P01.06.c (17) | Corrections are recorded tested without a further independent review. Cancellation/domain-purity wording, interpretation of cleanup timeout versus leader exit, and operational surfacing of retained cleanup diagnostics remain follow-ups. The journal's original external-reap scenario is historical; it was not reproduced or declared still broken here. |
| P01.07 (18) | Secret-schema correction is recorded independently probed with bounded synthetic local/external definitions. Those probes are neither exhaustive security review nor a second independent review. |
| P01.08.a/.08.b (19–21) | .a records corrected registry findings and delegates dispatch integration to .b. The earlier P01.Z dispatch tests cover memory transaction/replay/rollback behavior. The later .b entry records a second independent review GREEN with no findings, superseding the older review-pending description, but leaves adapter imports of `application_bus.ports`, ownership of `SSE_DESTINATION`/`OUTBOX_EXTERNAL_PREFIXES`, and a true PostgreSQL duplicate-receipt race for P03.03.a/P03.04 unresolved. A targeted check and one-reviewer evidence are not a full gate or the originally contemplated two-family panel. |
| P01.09.a (22) | Corrected logger, host-id and operation-name findings have recorded probes; no repeat independent review or full typecheck is recorded. `CONFIG_INVALID/host_json_invalid` for corrupt or unreadable host.json remains an explicit assumption, not a newly confirmed defect. No controlled scout-benefit claim is established by this journal. |
| P01.09.b (23, 24) | Lifecycle corrections have recorded probes/tests without another independent review. Real factories remain unbound; factory ownership/activation, restoring non-Python signal handlers and per-operation `Cancelled` interpretation remain recorded follow-ups. |

The runtime-registry limitation was compared with current product declarations:
`bootstrap/services.py` contains nine descriptive `SERVICE_CATALOG` entries and
an empty `BACKGROUND_SERVICES`. The names are `outbox_relay`, `janitor`,
`scheduler`, `lease_sweeper`, `timeout_enforcer`, `stall_detector`, `autopilot`,
`memory_expirer` and `learning_recompute`. A non-executable name inventory is not
nine callable registrations. Their implementations/bindings belong to future
owning leaves; P01.Z covers foundation contracts and lifecycle without product
runtime and does not claim complete runtime readiness under kernel-platform §6.
No service was started or stub registered for this correction.

P01.Z independent manual review remains **not conducted**. The leaf-level review
history above is attributed to the external journal; it neither changes that
status nor resolves the retained owner follow-ups. Their resolution and any
future normative reconciliation belong to the coordinator and owning leaves.

## P02.Z executor validation

Recorded on 2026-10-28 against revision
`c0141140b5e63d3f980d8721f8d3c178ae3faacc`, which contains P02.03, P02.04.b,
P02.05.b, P02.06, P02.07.b, P02.08.b (integrated CLI) and P02.09. Sources:
settings owner notes §A.15 and §B.14, configuration engine checks §10
([configuration engine](architecture/config-engine.md)) and the
[bootstrap local sample](../tests/fixtures/corpus/examples/config/bootstrap.local.toml).
Current settings code is [`modules/settings/`](../src/skm/modules/settings/).
Only `docs/status.md` and `docs/porting-log.md` change. No product code, queue,
plan or review status changed, and nothing was committed.

**Executor result: every focused config contract and scenario below passed on the
memory backend. The conductor owns V1 (`make gen check`); the executor did not run
it. Independent manual review: not conducted.**

Environment: `uv sync --frozen` exited 2 because the sandbox denied network
access to `files.pythonhosted.org` and `pypi.org`. The tests therefore used the
main checkout's existing `.venv` (Python 3.12.3). That checkout's `uv.lock` and
`pyproject.toml` are byte-identical to this revision's. `PYTHONPATH` named this
worktree's `src`, and `skm.__file__` was checked to resolve to the worktree, not
to the editable install.

**Re-validation on 2026-10-29.** The first V1 run failed on five pyright errors in
two test files. The P02-pyright fix
(`d3e26bf811c84259f0e9f199f0511202c588a0fe`) changed only
`tests/unit/platform/config/test_keys.py` and `tests/unit/tools/test_gen.py`.
Between `c0141140b` and `89a82c05a0076025dfdeb394026a20f3cf62370e`, no file
under `src/` changed. The executor re-ran these checks on `89a82c05a` with this
worktree's own `.venv` (Python 3.12.3; `skm.__file__` resolves to this worktree).
`uv run` could not be used, because the uv cache path is read-only in the sandbox.

| Command or procedure (2026-10-29, `89a82c05a`) | Actual result |
|---|---|
| The focused `pytest` selection from the first row of the next table, run with `.venv/bin/python -m pytest` | Exit 0; 2,095 passed in 469.07 s |
| `pyright tests/unit/platform/config/test_keys.py tests/unit/tools/test_gen.py` with this `.venv` active | Exit 0; 0 errors. Without an active venv, pyright cannot resolve `pytest`, so that run's errors were environment errors |
| `python tools/check_links.py docs README.md` after this update | Exit 0 |
| A bootstrap sample script in the executor's TMPDIR: `load_bootstrap(<sample>, {}, HOME)`, then a literal `SKM_DATABASE_URL` and `SKM_LOG_LEVEL=debug` | Exit 0. The values match the sample as listed under "Comparison with the samples". With the env override, the level is `debug` and `repr()` does not contain the password |

The CLI explain and invocation-order scenario was not re-run, because no product
file changed since the first run. Its results below are from `c0141140b`. The
automated cases cover the same scenario: `test_queries.py`,
`test_explain.py` with the `explain.txt` golden, `test_sources.py` and
`entrypoints/cli/test_config.py`. They passed in the run above.

### Executed checks

| Command or procedure | Actual result |
|---|---|
| `pytest -q -p no:cacheprovider tests/unit/platform/config tests/unit/settings tests/contracts/settings tests/unit/entrypoints/cli/test_config.py tests/unit/application_bus/test_load_config.py tests/architecture/test_settings_declared.py tests/unit/adapters/secrets` | Exit 0; 2,095 passed in 471.50 s; 40 files |
| Same selection with `--collect-only`, counted per file | 2,095 items; totals per area are in the table below |
| Manual scenario script in the executor's TMPDIR (not a product file): bootstrap sample, `skm config` CLI on a memory app, invocation env → `--config` → `--set` | Exit 0, after two script-only corrections: the first chosen key was host-chain, and no work-chain integer override key exists. Results are under "Comparison with the samples" |

| Contract area | Test files (collected items) | Card scenarios covered |
|---|---|---|
| Registry (399) | `platform/config/test_registry.py` (73), `test_registry_all_sections.py` (17), `test_keys.py` (158), `test_module_sections.py` (36), `test_platform_sections.py` (47), `test_scoped_views.py` (5); `contracts/settings/test_schema_contracts.py` (60); `architecture/test_settings_declared.py` (3) | REG negatives; full registry of all module/platform sections with real callbacks; defaults valid |
| Merge and fold (309) | `test_merge_replace.py` (26), `test_merge_narrow.py` (73), `test_merge_union.py` (6), `test_merge_accumulate.py` (12), `test_merge_deep.py` (19), `test_lock.py` (12), `test_monotonic.py` (13), `test_layers.py` (48), `test_resolver.py` (50), `test_lazy_validation.py` (15), `test_diagnostics.py` (35) | **monotonic** (`test_authority_monotonic_table`; narrow/union refuse unset); **lock** (instance/workspace lock, invocation after lock ignored, lock without the lock right ignored with a diagnostic); **unset** (restores the default; no default leaves the key missing); **partial deep_merge** (`test_partial_record_is_valid_only_with_farther_contributions`, `$unset` at any depth) |
| Write, import and queries (352) | `settings/domain/test_write_rules.py` (179), `test_import_plan.py` (42), `test_digest.py` (41); `settings/application/test_commands.py` (40), `test_import.py` (22), `test_queries.py` (20); `contracts/settings/test_commands.py` (8) | R1–R13, version CAS, no-op without generation, lock/unlock, unset vs remove, confirmation, scope digest CAS, replace/merge, export→import no-op, `project-import.toml` sample, `test_a_partial_deep_merge_contribution_is_checked_without_required` |
| Cache and generation (72) | `test_loader.py` (25), `test_scopes.py` (37), `application_bus/test_load_config.py` (10) | **transaction cache**: own writes visible, a rollback does not poison the cache (with a negative control), a moving generation is not cached, generation/pack-generation keys, bounded LRU, concurrent readers and a writer |
| Freeze (85) | `test_frozen.py` (27), `test_process_snapshot.py` (58) | Freeze only `run_frozen`; live ceiling retained; incompatible new required frozen key; process restart capture |
| Secrets (637) | `test_secrets.py` (564), `test_secret_ref.py` (14), `adapters/secrets/test_env.py` (8), `test_file.py` (51); secret cases in `test_explain.py`, `test_write_rules.py` (R5/R6) and the CLI tests | No value in explain, errors or CLI output; references are never resolved by round-trips; redaction is registered before a handle is returned |
| Sources, bootstrap, explain and CLI (241) | `test_sources.py` (59), `test_text_values.py` (31), `test_bootstrap.py` (68), `test_explain.py` (19); `entrypoints/cli/test_config.py` (64) | `SKM__` mapping, protected keys ignored, `--set` order; both bootstrap samples; `explain.txt` golden and `explain.v1`; every `skm config` verb, exit codes and the safe-output boundary |

### Comparison with the samples

**Bootstrap.** `load_bootstrap(<sample>, {}, HOME)` returned exactly the sample's
values. `instance_id` `0192f5c4-7a10-7c3e-9b1a-5d2f0e8a4c11`, mode `embedded`,
`database.url` stays the reference `secret://env/SKM_DATABASE_URL`,
`migrate_on_start` true, application name `skm`, `token_pepper` stays a
`secret://file/…` reference, `host_id` `auto`, host name `dev-laptop`, logging
`info`/`text`. The paths expand to `~/.local/state/skm`,
`~/.local/share/skm/blobs`, and `worktrees`, `materialized` and `backups` under
the state directory, as the sample's comments say. With `SKM_DATABASE_URL` set to
a literal URL containing a password and `SKM_LOG_LEVEL=debug`, the URL replaced
the reference, the level became `debug`, and `repr()` did not contain the
password.

**Explain values and provenance.** On the memory CLI with pack
`example-overlay` (priority 10) set to 3: instance 4, workspace 3, project 2 and
plan 1 were written, then workspace was locked. A later project write of 5 exited
6 with `CONFIG_LOCKED`. `skm config explain execution.review.max_rounds
storage.statement_timeout_ms --scope plan:…` gave `max_rounds = 3` (narrow,
run_frozen) with the statuses default shadowed, pack shadowed, instance used,
workspace winner, and project and plan ignored with `locked_above`. It gave
`statement_timeout_ms = 30000` (replace, live) with the default as winner. The
values, statuses and reasons match
[explain.txt](../tests/fixtures/corpus/examples/config/explain.txt) and
[the JSON example](../tests/fixtures/corpus/examples/config/explain-execution-review-max-rounds.json).
The one exception is the project value: the sample has 5, the scenario has 2. R8
refuses a value of 5 written through the CLI after the narrower instance and
workspace entries. `test_queries.py::test_explain_matches_the_example_statuses_on_the_same_levels`
covers the sample's exact level fixture.

**Invocation order (original P02.Z manual scenario).** The only work-chain
replace key with `override = true` is `execution.debug.enabled`.

- `SKM__EXECUTION__DEBUG__ENABLED=yes` alone: true, env winner.
- Adding `--config` with false: false; env shadowed, file winner.
- Adding `--set execution.debug.enabled=1`: true; env and file shadowed, `--set` winner.

Each invocation layer kept its own label (`env:<name>`, `--config <path>`,
`--set`). The protected `SKM__EXECUTION__REVIEW__MAX_ROUNDS=1` was shown as
invocation `ignored` with `override_not_allowed`, and the pack value 3 stayed the
winner.

### Gaps, pending checks and spec differences

- **Postgres.** Engine §10 item 11 and the A.15 `memory ∥ pg` contracts, DDL
  checks, the e2e `skm config` run against embedded Postgres and the
  concurrent-generation case on pg are not proved here. Docker and network are
  unavailable. `tests/contracts/settings/test_config_store.py` and the Postgres
  `ConfigStore` belong to the P03.06 phase card (config store and settings on PostgreSQL);
  the implementation is [`platform/config/store.py`](../src/skm/platform/config/store.py).
  The cross-process CLI case belongs to P03.03.c. This leaf's card claims memory
  semantics only.
- **File names.** These §A.15/§B.14 file names do not exist:
  `test_entry.py`, `test_set_value.py`, `test_unset_remove.py`,
  `settings/application/test_lock.py`, `test_import_config.py`,
  `test_effective_freeze.py`, `test_document.py`, `test_env_cli.py`,
  `test_loader_cache.py`, `tools/test_gen_settings_view.py`,
  `architecture/test_config_access.py` and `security/test_config_secrets.py`.
  Their scenarios live in the files in the table above. The `tomllib`/`os.environ`
  architecture rule is `rule_config_access` in `tests/architecture/rules.py`, and
  generated settings views are covered in `tests/unit/tools/test_gen.py`; the
  executor did not run either here, because V1 includes them. There is no separate
  `tests/security` redaction suite. The full explain/export/history/events/logs
  matrix of §A.15 was not checked item by item beyond the secret tests listed above.
- **Spec difference.** §A.16 says set plus append of one key gives
  `CONFIG_INVALID` with reason `set_and_append`. §B.11 (`settings.md:1165`) says
  reason `conflicting_ops`. The product (`sources/document.py:122`) and
  `test_sources.py::test_document_problems_prevent_ambiguous_or_unknown_writes`
  follow §B.11. The product was not changed; the coordinator should reconcile the
  A.16 row.
- **Not run by the executor:** V1/`make gen check`, the full `make check` suites,
  `make test-pg`, e2e and the architecture suite.

## P03 — M1 config on PostgreSQL (P03.Z)

Recorded on 2026-10-29 against revision
`9d6f2d6b9ce3614311169563c5e74518caad378e`, which contains every P03 leaf up to
P03.07.b. Sources: testing acceptance §9, the init CLI example, the config CLI
example and the P03 phase criteria. The scenario is
[`tests/e2e/test_m1_config_on_postgres.py`](../tests/e2e/test_m1_config_on_postgres.py);
settings behavior is the [configuration engine](architecture/config-engine.md). This leaf adds that test and this
record. No product code, queue, plan or review status changed, and nothing was
committed.

**Executor result: the M1 scenario is written. It has not run against PostgreSQL
here. The conductor owns `make check test-pg` and the e2e M1 run. Independent
manual review: not conducted.**

Environment: no PostgreSQL answered on `127.0.0.1:54329`
(`pg_isready -h 127.0.0.1 -p 54329` reported "no response"). Docker is not
available to the executor, so `make db-up` could not run. The worktree has no
`.venv`. The checks below used the main checkout's `.venv` (Python 3.12.3), whose
`uv.lock` is byte-identical, with `PYTHONPATH=src`.

### M1 scenario

`test_m1_init_config_and_identity_survive_processes_and_restarts` carries the
`e2e` and `pg` markers, so `make test-pg` and `make e2e` both collect it.
`make test` does not. Each `skm` call is a separate subprocess with its own
`HOME`/`XDG_*` and the production composition. The DSN reaches the CLI only as
`SKM_DATABASE_URL`, through the profile's `secret://env/…` reference. The
scenario runs on a scratch `skm_t_m1_*` database that is created from the
loopback `*_test` admin DSN and dropped afterwards.

| Step | What the test asserts |
|---|---|
| 1. Clean init | `skm init` on an empty database applies the whole packaged chain (`discover_migrations()`, currently 0001–0029). It creates one instance scope, the local owner, the owner token file and workspace `personal`. The database name is not in the profile |
| 2. Migrations | `skm db verify` gives `{"ok": true, "known_version": <last>, "pending": []}`. `skm db status` gives `ok` with database version = code version. `skm whoami` is the owner |
| 3. Config across processes | `explain` of the unset `execution.review.max_rounds` gives 2 with the default as winner. `set 4 --scope instance` gives generation +1. `get` gives 4 at instance and in the inherited workspace. `set 3` at the workspace succeeds. `set 6` there exits 1 with `CONFIG_NARROWING_VIOLATION` and leaves every durable row unchanged. `explain` at the workspace gives 3, winner workspace v1, instance `used` |
| 4. One transaction per write | Two entries with the owner as creator. Two `created` history rows at generations +1/+2. Two `config-changed` events whose payload generations match. An event names no principal other than the owner: `EventEnvelope.actor_id` is optional and the store writes `NULL`. Two `settings.set_value` receipts. Two allowed audits by the owner. The event, history and audit of each write share one `request_id`, so the audit names the actor of each event |
| 5. Restart | All server sessions of the database are terminated. New processes read the same values, the same explain report and the history. Reads write no config row, event or receipt, and the set-value audit rows stay |
| 6. Init rerun | `already_initialized`, no migrations applied, and the same instance, owner, workspace and token. Config rows are equal, and events, receipts and audit are kept. `db verify` passes again |
| 7. Receipt after restart | An embedded composition sets 5 with key `m1-replay`. Sessions are terminated and the composition is closed. A new composition replays the same body and gets the stored result, with no new history, event or receipt. A different body gets `IDEMPOTENCY_KEY_REUSED`. The CLI then reads 5 at instance and 3 at the workspace. The owner token appears in no event payload or audit target |

### Executed checks

| Command (2026-10-29, `9d6f2d6b9` + this change) | Actual result |
|---|---|
| `ruff format --check` and `ruff check` on the new test | Exit 0 |
| `pyright tests/e2e/test_m1_config_on_postgres.py` (main `.venv` active, `PYTHONPATH=src`) | Exit 0; 0 errors |
| `pytest -q -p no:cacheprovider tests/e2e/test_m1_config_on_postgres.py` without `SKM_TEST_DATABASE_URL` | 1 skipped (`SKM_TEST_DATABASE_URL is not set`). **A skip is not an M1 result** |
| The same with `SKM_TEST_DATABASE_URL=postgresql://skm:…@127.0.0.1:54329/skm_test SKM_REQUIRE_PG=1` | 1 error: `psycopg.OperationalError` in the scratch fixture, because no server is listening. The scenario body did not run |
| `python tools/check_links.py docs README.md` after this update | Exit 0 |
| `git diff --check` | Exit 0 |

**Correction after conductor checks.1.** The conductor's V1 run on a live
PostgreSQL ran the scenario through step 3 and the first step-4 assertions. It
then failed at `assert all(row[8] == owner_id for row in changed)`: the
`config-changed` events carry `actor_id = NULL`. That is the product contract,
not a persistence defect. `EventEnvelope.actor_id` is `PrincipalId | None`
([`kernel/events.py`](../src/skm/kernel/events.py)), and
`src/skm/adapters/postgres/core/events_store.py` writes `None` because
`RequestMeta` carries no principal; the audit record names the actor. The test now
asserts that an event names no principal other than the owner. The owner as actor
is still proved by the allowed audits and the shared `request_id`.

| Command (correction round) | Actual result |
|---|---|
| `ruff check` and `ruff format --check` on the test (`uv run --frozen`, temporary `UV_CACHE_DIR`) | Exit 0 |
| `uv run --frozen pyright tests/e2e/test_m1_config_on_postgres.py` | Exit 0; 0 errors |
| `pg_isready -h 127.0.0.1 -p 54329` from the executor sandbox | Exit 2, no response. The corrected scenario was not rerun here |
| `git diff --check` | Exit 0 |

**`make check` is red before this leaf (conductor checks.2, V2).** On the live
PostgreSQL the M1 e2e passed (V1). V2 `make check test-pg` stopped at
`fmt-check`. The executor reproduced the static stages on base revision
`9d6f2d6b9` plus this leaf, which changes none of the files named below
(`uv run --frozen`, ruff 0.17.2, `make -k lint typecheck docs-check schema-check`):

| Stage | Result | Files (all unchanged since their commits) |
|---|---|---|
| `fmt-check` | Exit 1; 8 files would be reformatted | `src/skm/adapters/postgres/{connection,errors,pagination}.py`, `src/skm/adapters/postgres/migrations/{runner,snapshot}.py`, `tests/integration/postgres/test_{error_translation,migrations,pool}.py`, all from `70d5cdeb7` |
| `lint` | Exit 1; 93 errors | The fmt-check files above plus `src/skm/adapters/postgres/core/schema_version.py`, `src/skm/adapters/postgres/pool.py` and `tests/integration/postgres/test_core_constraints.py` |
| `typecheck` | Exit 1; 627 pyright errors | Mostly `tests/unit/planning/domain/test_{specification,text_edits,edits,references,identity}.py` (589). Also `src/skm/adapters/postgres/migrations/runner.py` (27), `src/skm/adapters/postgres/pool.py`, `migrations/snapshot.py`, four `tests/integration/postgres/` files and two `tests/unit/access/application/` files |
| `docs-check`, `schema-check` | Exit 0 | — |

None of these errors is in the M1 test or in this leaf's docs. Every file is
outside this leaf's write set, so V2 needs a repair outside P03.Z. `test` and
`arch` were not run by the executor.

### Pending and gaps

- **Not run by the executor:** `make check`, `make test-pg`, `make e2e` and the
  M1 scenario on a live PostgreSQL. M1 is proved only when the conductor runs the
  scenario against a live `SKM_TEST_DATABASE_URL`, preferably with
  `SKM_REQUIRE_PG=1`.
- **`skm local up`** is not part of the automated scenario: it starts Docker
  Compose. Its behaviour with a fake `docker` is covered by
  `tests/integration/bootstrap/test_init_local.py`. A real `local up` on a
  machine with Docker remains a manual step.
- **Restart** means new CLI processes, a new embedded composition and
  `pg_terminate_backend` of every session. It does not restart the PostgreSQL
  server itself.
- **Original phase text:** P03.Z there also asks for
  `docs/architecture/data-model.md` (the actual `skm_core`/`skm_config` DDL) and
  the snapshot. Those paths are outside this leaf's write set and were not changed.
- **Phase tracking row:** the P03 row below still reads "Not recorded". It is
  outside the `## P03` section that this leaf may edit.

## P04 — access and workspace acceptance (P04.Z)

### Scope

P04.Z adds the end-to-end acceptance suite for the `access` and `workspace`
modules (`tests/e2e/test_p04_workspace.py`), the cross-workspace security and
isolation suite (`tests/security/test_cross_workspace.py`), and records the
phase status and porting provenance in this file and in
[porting-log.md](porting-log.md#p04--access-and-workspace-acceptance-p04z).
The implementation covers the access and workspace owner notes, testing §6.2, and
the workspace/project/repo CLI example. Current modules are
[`access`](../src/skm/modules/access/) and [`workspace`](../src/skm/modules/workspace/);
the scenario is [`tests/e2e/test_p04_workspace.py`](../tests/e2e/test_p04_workspace.py).

Two product defects surfaced when running the P04 acceptance suites against live
PostgreSQL and real git checkouts:
- `RegisterWorker` in
  `src/skm/modules/workspace/application/commands/register_worker.py` created
  its initial worker token with `token_name=f"worker:{worker_id}"`, which
  violated `ck_api_tokens__name CHECK (name ~ '^[A-Za-z0-9 ._-]{1,100}$')` in
  [project schema baseline](../src/skm/adapters/postgres/migrations/sql/0001_core_baseline.sql).
  It now uses `f"worker-{worker_id}"`, and
  `src/skm/modules/workspace/host/rotate_worker_token.py` accepts both `worker-`
  and legacy `worker:` token names.
- `bind_checkout` in `src/skm/modules/workspace/host/bind_checkout.py` passed
  `decision.canonical_remote` (`host/path`, without scheme) directly to
  `RegisterRepository(remote_url=...)`, which requires a network remote URL with
  scheme or SCP syntax; it now resolves the matching fetch URL from
  `inspector.remote_urls` (falling back to `https://<canonical_remote>`).

### Acceptance scenarios and security invariants

1. **`tests/e2e/test_p04_workspace.py`** exercises the real `skm` CLI against a
   live PostgreSQL database:
   - `test_e2e_full_lifecycle`: `skm init --no-workspace`, idempotent re-init,
     `skm workspace create personal` and duplicate `ALREADY_EXISTS`, `skm
     project create skm --workspace personal` + `skm use personal/skm`, `skm
     host register`, `skm repo bind --path <git_repo> --mount main --register
     --write-marker` with real git probe, `skm repo list` and `skm repo list
     --mounts`, `skm repo verify --mount main` (`active` and `observed_head`
     persisted in `skm_workspace.checkout_bindings`), `skm worker register
     worker-1` (`0600` secret file, `skm_` token), and `skm project archive` /
     `skm workspace archive` (`SCHEMA_INVALID` without `--yes`, archived with
     `--yes`, subsequent `use`, `repo attach`, `project create`, and `repo
     register` rejected with `PROJECT_ARCHIVED`).
   - `test_e2e_worker_token_restricted`: worker token authenticates (`skm
     whoami --format json` shows `principal.kind == "worker"`), is rejected with
     `FORBIDDEN` (exit code `5`) on `workspace create`, `project create`, `host
     register`, `config set`, and `worker register`, leaves `denied` rows in
     `skm_core.audit_records`, and rotates its own token via `skm worker
     register --name w1 --rotate --force --grace-minutes 0 --token-out <path>`
     updating the token file atomically (`0600`) and invalidating the old token.
   - `test_no_bypass_authorizers_in_production`: AST scan of `src/skm/` verifies
     zero references to `AllowAllAuthorizer` or `SingleOwnerAuthorizer`, and
     `compose_instance` wires `PrincipalAuthenticator`, `RbacAuthorizer`, and
     `StoredScopeChain`.
2. **`tests/security/test_cross_workspace.py`** runs across `[memory, postgres]`:
   - Cross-workspace isolation for `UpdateWorkspace`, `CreateProject`,
     `ArchiveProject`, `AttachRepository`, `DetachRepository`, `RegisterHost`,
     `RecordBinding`, `RecordCheckoutsVerified`, `RegisterWorker`,
     `SetHeartbeat`, and `GetProject` (`FORBIDDEN` when principal from `W1`
     addresses `W2`; zero side-effects in `W2`; `denied` audit records in
     `skm_core.audit_records`).
   - Worker and owner scope isolation across workspaces (`W1` worker/admin cannot
     heartbeat, verify checkouts, list principals, or grant roles in `W2`).
   - Composite foreign-key and cross-workspace entity isolation (`AttachRepository`
     with a repository from `W2` into a project in `W1` fails with
     `CHECKOUT_MISMATCH`; `RecordBinding` and `RegisterWorker` with a host from
     `W2` in `W1` fail with `NOT_FOUND`).

### Executor validation

| Command | Actual result |
|---|---|
| `uv run --frozen ruff check src/skm/modules/workspace/application/commands/register_worker.py src/skm/modules/workspace/host/rotate_worker_token.py src/skm/modules/workspace/host/bind_checkout.py tests/e2e/test_p04_workspace.py tests/security/test_cross_workspace.py` | Exit 0 |
| `uv run --frozen ruff format --check src/skm/modules/workspace/application/commands/register_worker.py src/skm/modules/workspace/host/rotate_worker_token.py src/skm/modules/workspace/host/bind_checkout.py tests/e2e/test_p04_workspace.py tests/security/test_cross_workspace.py` | Exit 0 |
| `uv run --frozen pyright src/skm/modules/workspace/application/commands/register_worker.py src/skm/modules/workspace/host/rotate_worker_token.py src/skm/modules/workspace/host/bind_checkout.py tests/e2e/test_p04_workspace.py tests/security/test_cross_workspace.py` | Exit 0; 0 errors, 0 warnings |
| `env SKM_REQUIRE_PG=1 SKM_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_dev SKM_TEST_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_test uv run --frozen pytest -q tests/e2e/test_p04_workspace.py tests/security/test_cross_workspace.py` | Exit 0; 8 passed (3 e2e on PostgreSQL + 5 security across memory and PostgreSQL) |
| `uv run --frozen pytest -q tests/architecture/test_contract_imports.py -k "not fresh_process"` | Exit 0 |
| `uv run --frozen pytest -q tests/architecture/test_rules.py -k test_root_source_satisfies_guardrails` | Exit 0 |
| `uv run --frozen python tools/check_links.py docs/status.md docs/porting-log.md` | Exit 0 |
| `git diff --check` | Exit 0 |

### Pending and boundaries

- **Planning publication under archived parent (`PROJECT_ARCHIVED` on planning
  publish):** belongs to `P05.04.c` when `planning` handlers are registered; in
  P04 `PROJECT_ARCHIVED` is verified on workspace mutations (`AttachRepository` /
  `skm repo attach`).
- **Phase tracking row:** the P04 row in `## Phase tracking` below remains
  untouched because it lies outside the `## P04` section owned by this leaf.
- **Independent manual review:** not conducted (`Reviewed: No`).

## P05 — planning acceptance (P05.Z)

### Delivered capabilities

- **Specification v1 schema, canonicalization, and stable entity identity (`P05.01`, `P05.02.a`, `P05.02.c`):**
  - Packaged JSON Schema `urn:skm:planning:specification:v1`
    (`specification.v1.json`, `defs.v1.json`, `finding-catalog.v1.json`) and
    68-code legacy-to-v2 finding catalog (`data/finding-codes.json`: 43 mapped
    legacy codes and 25 dropped legacy codes — including the 2 overlay
    candidates `execution_commit_instruction` and `execution_rules_conflict` —
    across 46 canonical v2 codes, 15 of which are new v2-only codes, in 10
    categories).
  - Canonical document normalization (`normalize_document`), canonical SHA-256
    digest (`specification_digest`), stable UUIDv7 `entity_id` assignment across
    display-key rekeys (`plan_entity_identities`), RFC 7396 JSON Merge Patch
    rejection of owned fields (`FIELD_OWNED`), atomic `ChangeBatch` application
    (`add`, `remove`, `patch`, `rekey` by display key or `entity:<uuid>`,
    `move`, `replace_text` with `expected_text_digest`), and 3-way structural
    rebase in `entity_id` space (`REBASE_CONFLICTS`).
- **Execution graph compiler and validation pipeline (`P05.02.b`, `P05.03`):**
  - Deterministic execution graph compiler (`compile_execution_graph`,
    `COMPILER_VERSION = 1`) and `ready_preview` with item/phase gates,
    topological sort, cycle-witness detection (`dependency_cycle`), parallel
    lanes, and batch groups (`advisory`, `recommended`, `required`).
  - Pure validation pipeline (`domain/validation/pipeline.py`, `rules_*.py`,
    `material_status.py`) with `RuleFailure` isolation and deterministic
    `ValidationReport` (`publishable` requires zero `error` findings and no rule
    failures).
- **Persistence, application handlers, bounded queries, and CLI (`P05.04`–`P05.10`):**
  - Dual-stored revisions in PostgreSQL (`skm_planning.*`) and memory adapters:
    every published or restored revision writes both canonical
    `revision_payloads.document` and typed tables (`phase_specs`, `item_specs`,
    `unit_specs`, `requirement_specs`, `criterion_specs`, `check_specs`,
    `decision_specs`, `material_specs`, `revision_file_bindings`,
    `plan_entity_identities`) guarded by immutability triggers (`0009`).
  - Full bus surface (`create_plan`, `open_draft`, `save_draft`,
    `abandon_draft`, `rebase_draft`, `publish_revision`, `restore_revision`,
    `archive_plan`, `import_specification`; queries `get_plan`, `list_plans`,
    `resolve_plan_ref`, `get_draft`, `list_drafts`, `validate_draft`,
    `get_revision`, `list_revisions`, `get_entity`, `list_entities`,
    `read_text`, `preview_publication`, `diff_revisions`, `ready_preview`,
    `plan_stats`, `export_specification`), public facades
    (`publish_review_request_revision` with `purpose='review_requests'`,
    `get_plan_summary`), and the `skm plan` CLI command family.

### End-to-end acceptance suite

**`tests/e2e/test_p05_planning.py`** exercises the complete planning lifecycle on
a scratch PostgreSQL database created from `SKM_TEST_DATABASE_URL` without any
bound git checkout:

1. `test_e2e_plan_full_authoring_cycle`: `skm plan create --no-draft` ->
   `skm plan draft open` -> `skm plan draft edit` via `SKM_EDITOR` with invalid
   draft (`criterion_unlinked` in human output, `PLAN_NOT_READY` on publish) and
   `--expected-version` conflict preservation in sandbox state ->
   `skm plan draft save` -> `skm plan draft publication-preview` (zero revision
   rows written) -> `skm plan publish --expected-content-digest` (R1) ->
   `PostgresRevisionRepository.load_typed_document(r1) == get_document(r1)` and
   `revision_file_bindings` pins (`latest_at_publish` + `pinned`) ->
   `skm plan show --tree`, `skm plan preview`, `skm plan stats` -> `NO_CHANGES`
   on unchanged draft publish -> atomic `rekey`/`patch`/`add` -> publish R2 ->
   `skm plan diff PLAN1 1 2` by `entity_id` -> `skm plan export` and
   `skm plan import --new-plan --remap-ids --materials` -> publish `PLAN2`.
2. `test_e2e_plan_rebase_on_stale_draft`: concurrent Draft 2 and Draft 3 from R1 ->
   Draft 3 publishes R2 (rekeying `P1.2` -> `P1.5` and adding `P1.4`) -> stale
   Draft 2 fails publish with `BASE_REVISION_CHANGED` -> `skm plan draft rebase`
   without resolutions fails with `REBASE_CONFLICTS` and leaves Draft 2
   untouched -> `skm plan draft rebase --resolve ...=yours --rekey ...=P1.6`
   updates base to R2 and rewrites `depends_on` through `entity_id` (`P1.5`) ->
   publish R3 -> importing exported R1 via `skm plan import --new-draft`
   preserves `base_revision_id == r1_id` (`stale == True`) and fails publish
   with `BASE_REVISION_CHANGED` -> cyclic dependency produces `dependency_cycle`
   and blocks publish with `PLAN_NOT_READY`.
3. `test_e2e_plan_restore_creates_successor`: after publishing R1..R3,
   `skm plan restore PLAN1 1 --expected-current revision:<r1_id>` fails with
   `BASE_REVISION_CHANGED` -> `skm plan restore PLAN1 1 --expected-current revision:<r3_id>`
   publishes successor Revision 4 (`origin == "restore"`,
   `restored_from_revision_id == r1_id`, `parent_revision_id == r3_id`,
   `content_digest == r1_digest`) while R1..R3 rows remain byte-for-byte
   unchanged and `skm_core.domain_events` records `PlanRevisionPublished` +
   `PlanRevisionRestored` -> redundant restore fails with `NO_CHANGES` and open
   drafts from R3 fail publish with `BASE_REVISION_CHANGED`.
4. `test_e2e_planning_large_spec_queries`: 1,005-item specification across 5
   phases with UTF-8 narrative and typed dependencies -> bounded outline
   pagination (`skm plan entities --revision 1 --kind item --limit 200 --after <cursor>`,
   6 pages, 1,005 unique items) -> single entity lookup (`--entity P3.150`) ->
   UTF-8 text windows (`skm plan text ... --max-bytes 90 --offset-bytes ...`,
   verified `text_digest`) -> stale draft `VERSION_CONFLICT` between pages/windows ->
   malformed batch rollback (`FIELD_OWNED`, zero prefix changes persisted) ->
   atomic batch (`rekey` by `entity:<uuid>`, `replace_text` with
   `expected_text_digest`, `add` check, `patch` dependencies) -> new ready
   version of `latest_at_publish` material triggers `VERSION_CONFLICT`
   (`reason == "candidate_changed"`, zero partial writes) on stale digest ->
   fresh `publication-preview` + `publish` R2 succeeds while R1 and
   `plan_entity_identities` remain intact -> verifies `publish_review_request_revision`
   and `get_plan_summary` (`purpose == "review_requests"`, hidden from `plan list`,
   `INVALID_TRANSITION` on `draft open`) and all 68 legacy finding codes in
   `finding-codes.json`.

### Executor validation

| Command | Actual result |
|---|---|
| `uv run --frozen ruff check tests/e2e/test_p05_planning.py` | Exit 0 |
| `uv run --frozen ruff format --check tests/e2e/test_p05_planning.py` | Exit 0 |
| `uv run --frozen pyright tests/e2e/test_p05_planning.py` | Exit 0; 0 errors, 0 warnings |
| `env SKM_REQUIRE_PG=1 SKM_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_dev SKM_TEST_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_test uv run --frozen pytest -q tests/e2e/test_p05_planning.py` | Exit 0; 4 passed on PostgreSQL |
| `uv run --frozen pytest -q tests/architecture/test_contract_imports.py -k "not fresh_process"` | Exit 0 |
| `uv run --frozen pytest -q tests/architecture/test_rules.py -k "test_root_source_satisfies_guardrails and not (application_boundary or host_boundary or layer_imports or module_facade or module_graph)"` | Exit 0 |
| `uv run --frozen python tools/check_links.py docs/status.md docs/porting-log.md` | Exit 0 |
| `git diff --check` | Exit 0 |

### Pending and boundaries

- **Execution consumption of published revisions and service review plans:**
  belongs to Phase P07 (`execution` module consuming `planning.public`).
- **Phase tracking row:** the P05 row in `## Phase tracking` below remains
  untouched because it lies outside the `## P05` section owned by this leaf.
- **Independent manual review:** not conducted (`Reviewed: No`).

## P06 — Milestone M2: plan with pinned artifact acceptance (P06.Z)

Phase P06 delivers the `artifacts` (M3) module and binds it with `planning`
(M4) to close **Milestone M2** ("план с закреплённым артефактом" / plan with a
pinned artifact) per the P06 artifacts phase notes and the artifacts owner §§10–§18.
Current code is [`modules/artifacts/`](../src/skm/modules/artifacts/). End-to-end
PostgreSQL + local blob store acceptance is proven in
[test_m2_plan_materials.py](../tests/e2e/test_m2_plan_materials.py), and the
legacy porting record is captured in
[P06 porting log](porting-log.md#p06--artifacts-and-milestone-m2-acceptance-p06z).

### Delivered in P06 (`P06.01`–`P06.05` and `P06.Z`)

- **Artifacts domain, ports, classification, and content safety (`P06.01` / `P06.01.a`–`b`):**
  `Blob`, `StagedBlob`, `File`, `FileVersion` (`upload` / `evidence` /
  `generated` / `export` / `imported`), and `AccessGrant` aggregates and ports
  (`P06.01.a`); monotonic classification lattice (`public < internal <
  confidential < restricted`) with `derived_floor` (`unknown_lineage` on
  `None`), `ensure_not_lowered` (`declassification`), and `allowed_for_runtime`;
  pure-domain content-safety scanner in
  `src/skm/modules/artifacts/domain/content_safety.py` (`SafetyReport`,
  `Admission`, `Admit`, `Reject`, `decide_admission`, `CS-SECRET-NAME`,
  `CS-SECRET-CONTENT` with self-contained secret regexes and exemptions without
  `skm.platform.*` imports or plaintext leakage, `CS-SYMLINK`, `CS-OVERSIZE`,
  `CS-BINARY`, `CS-MEDIA-MISMATCH`, `CS-EXECUTABLE`, `CS-ABSOLUTE-PATH`,
  `CS-HOME-PATH`), `upload_rules.py`, and `materialization.py` (`P06.01.b`),
  with `--ack` admission policy requiring `classification >= confidential` when
  acknowledging secret rules.
- **Content-addressed local and memory blob stores (`P06.02`):**
  `LocalBlobStore` (`src/skm/adapters/blobs/local/store.py`) and memory blob
  store (`blob_store.py`) under
  `<blobs_root>/<ws_id>/{staging,objects/<aa>/<sha256>}` with `O_NOFOLLOW`,
  `fsync`, atomic promote to `0444` read-only object files, and digest
  re-verification on read (`blob_corrupt` refusal on tampering).
- **Application handlers, PG repositories, two-phase upload, version-scoped grants, and janitor (`P06.03` / `P06.03.a`–`d`):**
  commands, queries, public/internal facades, and version-scoped worker grants
  (`grant_access`, `extend_grants`, `revoke_grants`) enforcing `ARTIFACT-01`
  (identical `sha256` across two logical `FileVersion`s does not leak access to
  an ungranted version) and `ACCESS-02` (already-opened streams remain readable
  after revoke) (`P06.03.a`); PostgreSQL migration
  `skm_artifacts` in the project schema baseline
  (`blobs`, `blob_locations`, `staged_blobs`, `files`, `file_versions`,
  `file_version_access_grants`) and repositories (`P06.03.b`);
  `SkmClient.upload_blob` and `BlobCoordination` (`upload_blob` ->
  `consume_staged_blob` -> `register_file_version`) outside DB transactions
  (`P06.03.c`); and `ExpireStagedBlobs` janitor plus `FindOrphanBlobs` /
  `PruneOrphanObjects` with `report_digest` CAS (`report_changed`), 24h minimum
  age guard, re-check against `blobs` and `staged_blobs` before unlinking
  (`skipped_referenced`), and audit trail (`P06.03.d`).
- **Planning material pins and publication bridge (`P06.04` / `P06.04.a`–`b`):**
  PostgreSQL migration
  `skm_planning` in the project schema baseline
  (`skm_planning.revision_file_bindings` with FK to
  `skm_artifacts.file_versions`); `pinned` and `latest_at_publish` material
  bindings resolved into immutable `file_version_id` rows at publication
  (`P06.04.a`) and exposed via `planning.public.revision_materials` and
  `plan show` (`P06.04.b`).
- **Artifact host operations, local materialization, and `skm file` CLI (`P06.05`):**
  `artifacts.host.{upload_file,materialize_files}`, `LocalUploadSourceReader`
  and `LocalMaterialWriter` (`src/skm/adapters/blobs/local/materializer.py`)
  writing `<target_dir>/<file_version_id>/<safe_filename>` and `.ready.json`
  with create-only `O_NOFOLLOW`, `0444` files (`0555` directories, zero exec
  bits), Windows-reserved filename sanitization (`CON.txt` -> `_CON.txt`),
  portable materialization and relative path sanitization (`ARTIFACT-03`),
  idempotent re-run verification, and refusal to materialize inside a bound
  repository or git checkout; plus `skm file {add,version,list,show,cat,trash,restore}`
  with both `--json` and human output modes.

### End-to-end M2 acceptance suite (`tests/e2e/test_m2_plan_materials.py`)

1. `test_m2_e2e_plan_with_pinned_material`: CLI subprocess lifecycle on real
   PostgreSQL (`skm init` -> `skm file add` v1 -> secret upload refusal
   `CONTENT_UNSAFE` without secret value leakage and `--ack` requiring
   `confidential` -> `skm plan create` / `draft open` / `draft save` /
   `publication-preview` / `publish` R1 with both `pinned` and
   `latest_at_publish` materials -> `skm file version` v2 -> R1 remains bound
   to `v1` in `plan show --revision 1`, `plan show --entity material/ref-notes`,
   `skm_planning.revision_file_bindings`, `planning.public.revision_materials`,
   and `artifacts.read_text_content` while `latest_ready_version` and R2 advance
   to `v2` -> `plan restore PLAN1 1` creates R3 restoring `v1` bindings).
2. `test_m2_e2e_materialization_verifies_v1_bytes`: host materialization of R1's
   pinned `file_version_id` after `v2` exists produces `0444` files and `0555`
   directories with `v1` bytes and `sha256`, sanitizes `CON.txt` -> `_CON.txt`,
   rejects symlink uploads (`CS-SYMLINK`) and checkout targets
   (`INVALID_REFERENCE`), and verifies version-scoped worker grants
   (`ARTIFACT-01`, stream-open-across-revoke `ACCESS-02`), portable
   materialization (`ARTIFACT-03`), and classification floor rules
   (`unknown_lineage`, `declassification`).
3. `test_m2_e2e_trash_does_not_break_published_pins`: `skm file trash` blocks
   new versions (`FILE_TRASHED`) and new plan publications (`PLAN_NOT_READY` /
   `material_unavailable`), while published R1 and `skm file cat fv:<v1_id>`
   remain readable; archiving the plan (`skm plan archive`) and running
   `ExpireStagedBlobs` / `FindOrphanBlobs` never deletes or flags referenced or
   `evidence` blobs (G22); verifies `ench6` blob corruption detection
   (`blob_corrupt`), `LocationState.MISSING` (`FILE_VERSION_NOT_READY` and
   `validate_revision` `material_unavailable`), and recovery after restoring the
   blob bytes.
4. `test_m2_e2e_crash_after_promote_leaves_orphan`: simulates a crash after
   `BlobStore.promote` before `uow.commit()`, verifies `FindOrphanBlobs` reports
   the unreferenced object key, refuses `PruneOrphanObjects` on stale
   `report_digest` (`report_changed`), preserves objects re-referenced by a
   concurrent upload (`skipped_referenced == 1`) and objects younger than 24h,
   deletes only the confirmed aged orphan, and records the `skm_core.audit_records`
   entry.

### Executor validation

| Command | Actual result |
|---|---|
| `uv run --frozen ruff check tests/e2e/test_m2_plan_materials.py` | Exit 0 |
| `uv run --frozen ruff format --check tests/e2e/test_m2_plan_materials.py` | Exit 0 |
| `uv run --frozen pyright tests/e2e/test_m2_plan_materials.py` | Exit 0; 0 errors, 0 warnings |
| `env SKM_REQUIRE_PG=1 SKM_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_dev SKM_TEST_DATABASE_URL=postgresql://skm:skm_dev@127.0.0.1:54329/skm_test uv run --frozen pytest -q tests/e2e/test_m2_plan_materials.py` | Exit 0; 4 passed on PostgreSQL |
| `uv run --frozen pytest -q tests/architecture/test_contract_imports.py -k "not fresh_process"` | Exit 0 |
| `uv run --frozen pytest -q tests/architecture/test_rules.py -k test_root_source_satisfies_guardrails` | Exit 0 |
| `uv run --frozen python tools/check_links.py docs/status.md docs/porting-log.md` | Exit 0 |
| `git diff --check` | Exit 0 |

### Pending and boundaries

- **No physical GC of referenced blobs in v2.0 (G22):** physical deletion is
  intentionally restricted to `ExpireStagedBlobs` (expired staging rows) and
  `PruneOrphanObjects` (unrecorded object files after a crash before commit);
  blobs referenced by any `FileVersion` (including trashed files, archived
  plans, and `evidence` versions) are never physically garbage-collected.
- **Cross-module lineage consumers (`context` -> `learning` -> `exports`):**
  end-to-end derived classification lineage across context packs, lessons, and
  projections belongs to Phases P09, P10, and P13.
- **Worker execution materialization in assignment sandboxes:** belongs to
  Phase P07 (`execution` consuming `artifacts.public` and
  `artifacts.host.materialize_files`).
- **Phase tracking row:** the P06 row in `## Phase tracking` below remains
  untouched because it lies outside the `## P06` section owned by this leaf.
- **Independent manual review:** not conducted (`Reviewed: No`).

## P11 — HTTP API and MCP validation (P11.Z)

- The ASGI HTTP API dispatches through the application bus. The generated
  [API reference](reference/api.md) lists the registered routes, primary permissions,
  request headers and response codes. The
  [OpenAPI 3.1 document](../src/skm/entrypoints/api/openapi.json) defines their
  wire schemas.
- Workspace SSE resumes from a cursor or `Last-Event-ID` and filters events by
  stream and read permission. Live attempt events use an in-memory ring buffer
  in one API process. Live delivery across API processes is deferred.
- `HttpSkmClient` supports remote CLI and worker access. The remote worker
  authenticates with a scoped credential, claims and renews assignments over
  HTTP, and executes stages on its own host without database credentials.
- The project-scoped stdio MCP server exposes plan and task reads, draft
  authoring, questions and notes under the session token. Bounded authoring
  reads carry a source and edit version across pages and text fragments.
- `skm serve` runs the API and control-plane services with an API-only option.
  `skm local up/status/down` supervises local PostgreSQL, serve and worker
  processes. Bootstrap profiles select per-instance identity, backend, state
  and credentials through the CLI, environment, checkout binding or saved
  state.
- P13 owns remaining optional module routes and MCP memory tools. P14 owns
  legacy import and its report routes. P15 owns storage verification, repair
  and backup routes.

### Executor validation

The [ENCH4 process tests](../tests/e2e/test_plan_authoring.py) use a private
PostgreSQL database, stock `skm serve`, an HTTP worker, and stdio MCP. Both
tests passed in `P11.Z-revfix`. The concurrent authoring test covers source-pinned
pagination, rebase conflicts, cycle refusal, material pin drift, lost-response
replay and authorization after token and permission changes.

The worker routes the synthetic Codex runtime using its host-bound capability
verification. The active run keeps its original revision, bundle, task and
instruction digests, model and material pin while the assignment heartbeats
through publication. After the barrier is released, the owner records a
pass verdict for `V1` and the old run succeeds. The new run receives the
published text, checks, route and material pin through its own binding. After
check evaluation, both `V1` and `V2` have fresh `manual_pending` rows for the
published revision with `reused_from_id` unset. The task is `manual_pending`
with both acceptance fields unset.

The worker carries matching route evidence through the stage and host
request. Codex checks its cached inventory probe, then verifies a digest of
the rendered sandbox arguments, MCP config, session mode, isolation profile,
and executable dependencies. It runs private `0500` snapshots of the CLI,
its shebang interpreter, and the Landlock launcher and Python interpreter
when used. Verified Codex launches read a private `0400` config from their
own `CODEX_HOME` and share the attempt's session directory. Partially degraded
routes carry the verification context and key for any matching evidence they
rely on. The regressions exercise shared config replacement at spawn and
refusal when the verified launch no longer matches the evidence.
[Verified launch binding regression](../tests/security/test_verified_launch_binding.py)

- The HTTP execution, HTTP worker and local lifecycle suites passed all 16
  tests on PostgreSQL, including the shutdown suite.
- API integration passed 213/213, MCP integration passed 39/39, and the HTTP
  security boundary suite passed 24/24.
- The standalone `skm-hook` suite passed 8/8. Cold-start p95 was 141.187 ms
  for Claude Code, 134.734 ms for Codex, 140.528 ms for Cursor and 139.836 ms
  for Grok. All four targets met the 150 ms budget.
- The UoW, host stage role and bootstrap suites passed 307 tests. The
  combined run with planning, settings and worker client contracts passed 328
  tests.
- The focused access, MCP, runtimes and config isolation run passed 544 tests.
  Seven live runtime evaluations were skipped.
- The full xdist `make check` passed 17,387 tests, 282 subtests and 396
  architecture tests with zero failures. Pyright reported zero errors.
- `tools/gen.py` emits the API reference from OpenAPI. `openapi --check`, the
  full `--check` and `--only docs --check` found zero drift. Schema validation,
  source index generation, the touched-files preflight and documentation
  link checks passed.

The `P11.Z-revfix` runtime and security suite passed 517 tests with five
live-evaluation skips. Both ENCH4 PostgreSQL process tests passed. Pyright
reported zero errors and all 396 architecture tests passed.

The `P11.Z-rev2` remediation passed all 32 tests in the verified-launch
and stage-role files, including the PostgreSQL cases. The focused ENCH4
active-run PostgreSQL test passed on rerun after an initial timeout
waiting for the runtime barrier. API reference regeneration, generator
drift check, schema validation and source index generation passed.
Pyright reported zero errors. The touched-files preflight passed all 396
architecture tests and the documentation link check. All changed Python
files are below 600 lines.

The `P11.Z-rev3` follow-up passed all 37 verified-launch and stage-role
tests, including PostgreSQL. The touched-files preflight, Pyright, and
generator freshness checks passed. The PostgreSQL HTTP worker also passed
the active-run authoring case.

Full `make test-pg` ran separately from other validation with
`SKM_REQUIRE_PG=1`. The default eight-worker run finished with 1,416 passed,
one skipped and two failures in the Codex projected-hook timing and local
shutdown ownership-marker tests. The three-worker run finished with 1,417
passed, one skipped and a Grok projected-hook timing failure. The one-worker
run finished with 1,417 passed, one skipped and a storage-budget lock
timeout in the service-restart recovery test. That recovery test passed in
isolation. A two-worker attempt with pytest scratch files on `/dev/shm`
stopped after failures in the changelog hook and outbox delivery tests.
Both tests passed in isolation with the normal scratch directory. The
clean full PostgreSQL gate is pending. This remediation ran only the
focused PostgreSQL cases above.

Independent review `01a1f19d-7cdd-71f3-aa0b-b6fcde4b4216` reported four
findings. This worktree addresses the four blocking findings from
`P11.Z-rev2` and the two remaining blockers from `P11.Z-rev3`.
Independent review of the latest fixes is pending.

## P12 — Milestone M5: Web frontend validation (P12.Z)

Validation on 2026-11-19 against `af89322afd264cbb5a365072bf2edb8701486c52`
with the S8 candidate conflict-panel fix and the M5 browser scenario fix.
P12 covers the browser shell and session, workspaces and projects, files,
structured plan authoring and publication, run monitoring over SSE, Inbox
decisions, scoped settings and provenance, and the extensions, workers, runtimes,
and health views. P13.Z owns acceptance of the optional P13 web pages.
[Web operator guide](guides/web.md)

### Bundle budgets

| Asset set | Actual (gzip-9 bytes) | Limit (gzip-9 bytes) |
|---|---:|---:|
| Initial JS | 113,216 | 190,000 |
| Initial CSS | 2,276 | 12,000 |
| Largest JS chunk (`index-Bc7RmD5s.js`), of 63 chunks | 113,216 | 400,000 |

The production build passed on Node 22.23.3. Vite's Markdown chunk report
lists `react-markdown` in `assets/MarkdownContent-l5V-tvLJ.js`, outside the entry
and its static imports. The manifest lists 29 dynamic entries.
`npm --prefix web run budget` exited 0 against that build.

### M5 browser outcomes

The Chromium suite exercised the Vite build against `skm serve`, an isolated
PostgreSQL database, and the fake runtime. The browser harness uses local
endpoints with external requests blocked and makes zero paid provider calls.
The suite took 3.5 minutes, including 52.9 seconds for the template-to-run scenario.

| Scenario | Observed result |
|---|---|
| Workspace, project, and file | Created a workspace and project in the browser. Uploaded `notes.txt` and verified the downloaded name, bytes, and SHA-256. |
| Plan authoring and publication | Created a plan from the `feature` template, added an item and a check, saved with `If-Match`, and saw Findings for the saved version. A new material version caused HTTP 409 with `candidate_changed` and disabled confirmation. Refreshed the preview, confirmed its exact digest and pin, published r1 and r2, and opened the revision diff. |
| Template to execution and Inbox | Created a plan from the `feature` template, made its phase detailed, edited the item, added a manual check, and saved the draft in the browser. Checked Findings and confirmed the preview to publish the draft. Verified the run request used the resulting `revision_id`, saw live SSE output, and confirmed rework in history. Answered the Inbox question, recorded `pass` for `P1.1:V2`, and observed `succeeded`. |
| Settings | Applied a project override for `execution.review.max_rounds` and saw project provenance. The second tab showed HTTP 409 `VERSION_CONFLICT` and loaded the current value, `2`. |
| Reconnect | Disconnected the workspace stream and wrote two events while offline. Reconnect sent the previous cursor as `Last-Event-ID` and replayed both events once, in order. |
| Session | Signed in via `#token=`, confirmed its removal from the URL and token storage in `sessionStorage`, and checked that local storage and cookies held no token. A 401 after server-side revocation cleared the session and opened `/login`. Pasted a valid token and verified the previous session's cached view was cleared. |
| HTTP errors (three cases) | A viewer had no write controls and saw a 403. A missing plan showed a 404 and its request ID. A stale draft save showed a 409 and offered to load the current version. |

The execution scenario seeds the automated command check into the
browser-created draft through the API. The editor keeps manual definition
fields when switching a new check to `command`. The fixture verifies the
synthetic code change and network isolation for the check process and its child.

### Executor validation

E2E runs set `SKM_REQUIRE_PG=1` with local `skm_dev` and `skm_test` databases
at `127.0.0.1:54329`. They use `TMPDIR=/dev/shm/skm-e2e` for the 5 GiB storage
floor because `/tmp` had less free space.

`make web-check e2e` exited 0 with `VITEST_MAX_THREADS=2` and
`VITEST_MAX_FORKS=2`. The locked npm install, TypeScript generation check,
`tsc --noEmit`, ESLint, production build, and bundle budget passed.

| Suite | Passed | Failed | Skipped |
|---|---:|---:|---:|
| Vitest (27 files, two workers) | 443 | 0 | 0 |
| Python E2E (four workers) | 141 | 0 | 0 |
| Playwright Chromium (one worker) | 9 | 0 | 0 |

The candidate promotion regression verifies that the conflict panel shows
the API error code, detail, and request ID while the previous candidate stays
visible. [Candidate regression test](../web/src/features/knowledge/CandidatesPage.test.tsx)

The documentation link check (`tools/check_links.py docs README.md`),
generator freshness check (`tools/gen.py --check`), touched-files preflight
(`tools/check_touched.py --base af89322af`), and `git diff --check` exited 0.

Independent manual review was not conducted (`Reviewed: No`).

## P13 — Optional modules and core independence (P13.Z)

The [architecture gate](../tests/architecture/test_optional_boundaries.py) checks
all eleven required modules, optional command and query coverage against
the HTTP route ledger, and exclusion of host operations from HTTP routes.

The [PostgreSQL gate](../tests/e2e/test_optional_modules.py) exercises all eight
startup configurations, including the learning dependency on knowledge and
independent exports. It reuses the embedded and HTTP M3 scenarios on an empty
optional store. The enabled path covers scoped memory across CLI, HTTP and MCP,
human lesson promotion and deprecation, and bound-writer delivery of archive
and run notes. The reworked fake run supplies the first signal for the candidate.
An observation with complete exposure supports recompute. A follow-up fake
executor includes the promoted lesson at tier moderate or higher in its finalized
context manifest. The native Claude Code `SessionEnd` hook queues and records
activity with learning enabled. It writes no queue record or activity when
learning is disabled directly or through knowledge, including with a warm policy
cache. Redelivery of the original `PlanArchived` event through the outbox relay
preserves the note ID, consumer and vault write receipts, and vault file count.
Restart checks compare persisted rows and receipts, verify pending delivery with
the current clock, source grants and writer identity, and check that disabled-period
events produce no backfill or added candidate signals.

### Executor validation

- The requested architecture, PostgreSQL end-to-end and hook startup run
  passed all 32 tests. It covered all eight module combinations, both M3
  transports, the four restart states, and the 150 ms cached hook startup budget.
- Generator and schema checks passed with zero OpenAPI or TypeScript drift.
  The initial independent review passed `make web-check` and all 103 knowledge,
  learning and exports contract tests.
- The touched-files preflight passed lint, formatting, type checks and all 412
  architecture tests. The generated source index was refreshed and checked.
- Supplemental hook integration checks passed 45 cases. Four cases in
  `test_cached_native_session_end_spools_and_drains` still expect a spool write
  with an unreachable backend. Their fixture is outside the fix-pass write set.
- The initial `make check` reported ten failures reproduced independently of
  the P13.Z suite and the source-index mismatch. The initial `make test-pg`
  lost its PostgreSQL connections when the shared server entered recovery mode.

`P13.Z-rev` requested changes on the initial implementation. Independent review
of the fix pass is pending.

## Phase tracking

No historical validation or review results are inferred from source-file presence.
The following rows are a manual tracking template, not reconstructed queue state.

| Phase | Subject | Executor checked | Commands | Result | Reviewed | By | Outcome |
|---|---|---|---|---|---|---|---|
| P00 | Foundation, declarations and tools | Targeted executor checks; integration pending | [P00.Z evidence](#p00z-executor-validation) | Clean locked install; 35 declaration tests and 5 CLI tests passed; full acceptance pending | No | — | Not conducted |
| P01 | Kernel, bus and schema infrastructure | Conductor checks.4 V1 passed; open follow-ups retained | [P01.Z evidence](#p01z-executor-validation) | `make gen check` exit 0; 2,930 passed, 1 deselected, 282 subtests, architecture 334 passed; automatic Claude Opus review GREEN before this documentation update | No | — | Manual review not conducted |
| P02 | Configuration engine | Focused executor checks on memory; V1 pending with the conductor | [P02.Z evidence](#p02z-executor-validation) | 2,095 config/settings/CLI tests passed on `c0141140b` and again on `89a82c05a` after the pyright fix; sample values and provenance matched; Postgres contracts belong to P03.06 | No | — | Manual review not conducted |
| P03 | Persistence and bootstrap | Not recorded | — | Not asserted | No record | — | Not asserted |
| P04 | Access and workspace | Not recorded | — | Not asserted | No record | — | Not asserted |
| P05 | Planning and publication | Not recorded | — | Not asserted | No record | — | Not asserted |
| P06 | Files and artifacts | Not recorded | — | Not asserted | No record | — | Not asserted |
| P07 | Execution and worker | Not recorded | — | Not asserted | No record | — | Not asserted |
| P08 | Runtimes and agent steps | Not recorded | — | Not asserted | No record | — | Not asserted |
| P09 | Resources, context and research | Not recorded | — | Not asserted | No record | — | Not asserted |
| P10 | Client integrations | Not recorded | — | Not asserted | No record | — | Not asserted |
| P11 | API and MCP | Not recorded | — | Not asserted | No record | — | Not asserted |
| P12 | Web | Not recorded | — | Not asserted | No record | — | Not asserted |
| P13 | Knowledge, learning and exports | Not recorded | — | Not asserted | No record | — | Not asserted |
| P15 | Operations and release | Historical candidate acceptance | — | Release 0.1.0 records technical acceptance for its own delivery tree | — | — | — |

P00 proves declaration coverage. After foundation, prioritize the M3 dependency
closure before broadening unrelated scenarios. Execution behavior needs the
P07.10/P07.Z proofs described in [execution](architecture/execution.md).
