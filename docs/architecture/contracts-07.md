# Contract inventory, part 7

Codegen-only metadata repairs under the coordinator amendment (all validation content is unchanged):

| Schema | Previous declaration | Generated declaration |
|---|---|---|
| `src/skm/schemas/artifacts/host-results/materialize-files.v1.json` | `MaterializeFilesReport` / `dataclass` | `MaterializeFilesReport` / `alias` |
| `src/skm/schemas/extensions/defs.v1.json` | `Extensions definitions` / `dataclass` | `ExtensionsDefinitions` / `alias` |
| `src/skm/schemas/extensions/host/install-pack.v1.json` | `InstallPackRequest` / `dataclass` | `InstallPackRequest` / `alias` |
| `src/skm/schemas/integrations/host-results/remove-projection.v1.json` | `RemoveProjectionResult` / `typeddict` | `RemoveProjectionReport` / `typeddict` |
| `src/skm/schemas/planning/defs.v1.json` | `Defs` / `dataclass` | `Defs` / `alias` |
| `src/skm/schemas/planning/views/drafts.v1.json` | `DraftsView` / `dataclass` | `DraftsView` / `alias` |
| `src/skm/schemas/policy/tool-call.v1.json` | `ToolCall` / `dataclass` | `ToolCall` / `alias` |
| `src/skm/schemas/policy/views/explain-permissions.v1.json` | `ExplainPermissionsView` / `dataclass` | `ExplainPermissionsView` / `alias` |
| `src/skm/schemas/policy/views/profiles.v1.json` | `ProfilesView` / `dataclass` | `ProfilesView` / `alias` |
| `src/skm/schemas/runtimes/views/runtimes.v1.json` | `RuntimesView` / `dataclass` | `RuntimesView` / `alias` |
| `src/skm/schemas/workspace/views/project-repositories.v1.json` | `ProjectRepositoriesView` / `dataclass` | `ProjectRepositoriesView` / `alias` |

Kinds follow the generator in [`tools/codegen/`](../../tools/codegen/): arrays, open maps, definitions-only
documents and unions retain their existing validation shape instead of claiming to be dataclasses.
The materialization sequence follows the artifacts schemas. Host requests follow the extensions schemas.
Collection aliases follow the policy, runtimes and workspace schemas. The host remove-projection report is
distinguished from the command's `RemoveProjectionResult`; both wire schemas are unchanged.
Current modules: [`artifacts`](../../src/skm/modules/artifacts/), [`extensions`](../../src/skm/modules/extensions/),
[`planning`](../../src/skm/modules/planning/), [`policy`](../../src/skm/modules/policy/),
[`runtimes`](../../src/skm/modules/runtimes/), [`workspace`](../../src/skm/modules/workspace/) and
[`integrations`](../../src/skm/modules/integrations/).
`ExtensionsDefinitions` only removes spaces from the existing definitions-document export.
Frozen examples remain unchanged; their original metadata and the repaired current schemas are
retained separately in `current-corpus/examples.json` and `current-corpus/schemas.json`.

Materialized generator outputs and supporting files:

| Materialized file | Contracts | Declaration → implementation/refinement leaves |
|---|---|---|
| `src/skm/schemas/schema-lock.json` | Generated normalized compatibility snapshots; tooling data excluded only at the schema root | P01.05.b |
| `src/skm/kernel/generated/_codec.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/kernel/generated/defs.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/kernel/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/kernel/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/access/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/access/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/access/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/access/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/access/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/access/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/access/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/artifacts/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/artifacts/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/artifacts/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/artifacts/generated/host.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/artifacts/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/artifacts/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/artifacts/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/artifacts/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/context/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/context/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/context/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/context/generated/host.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/context/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/context/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/context/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/context/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/execution/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/execution/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/execution/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/execution/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/execution/generated/host.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/execution/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/execution/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/execution/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/execution/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/exports/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/exports/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/exports/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/exports/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/exports/generated/host.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/exports/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/exports/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/exports/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/exports/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/extensions/generated/agent_profile.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/host.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/pack.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/skill.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/extensions/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/integrations/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/integrations/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/integrations/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/integrations/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/integrations/generated/host.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/integrations/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/integrations/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/integrations/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/integrations/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/knowledge/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/knowledge/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/knowledge/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/knowledge/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/knowledge/generated/host.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/knowledge/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/knowledge/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/knowledge/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/knowledge/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/learning/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/learning/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/learning/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/learning/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/learning/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/learning/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/learning/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/learning/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/planning/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/planning/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/planning/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/planning/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/planning/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/planning/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/planning/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/planning/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/policy/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/policy/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/policy/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/policy/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/policy/generated/intent_approval.py` | Schema-derived approval projection | P12.06 |
| `src/skm/modules/policy/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/policy/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/policy/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/policy/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/runtimes/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/host.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/observation.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/request.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/result.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/session_events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/usage.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/runtimes/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/settings/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/settings/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/settings/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/settings/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/settings/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b → P02.08.b |
| `src/skm/modules/settings/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/settings/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/workspace/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/modules/workspace/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/workspace/generated/documents.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/workspace/generated/events.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/workspace/generated/host.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/workspace/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/workspace/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/workspace/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/modules/workspace/generated/views.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/platform/config/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/platform/config/generated/settings.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/platform/generated/__init__.py` | Schema-derived types/converters or generator component | P01.05.a |
| `src/skm/platform/generated/commands.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/platform/generated/queries.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `src/skm/platform/generated/results.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `web/src/api/generated/access.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/artifacts.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/config.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/context.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/execution.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/exports.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/extensions.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/integrations.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/kernel.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/knowledge.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/learning.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/planning.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/platform.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/policy.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/runtimes.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/settings-document.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `web/src/api/generated/settings.ts` | Schema-derived types/converters or generator component | P01.05.a → P02.08.b |
| `web/src/api/generated/workspace.ts` | Schema-derived types/converters or generator component | P01.05.a |
| `tools/codegen/__init__.py` | Generator package boundary | P01.05.a |
| `tools/codegen/cli_reference.py` | AST-only CLI reference emitter and configuration usage guide; outputs docs/reference/cli.md and guide in docs/reference/config.md without handler execution | P02.08.b (bounded partial) |
| `tools/codegen/error_catalog.py` | Independent stdlib error-catalog emitter; connected to make gen | P01.02 → P01.05.a |
| `tools/codegen/model.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `tools/codegen/parse.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `tools/codegen/render_python.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `tools/codegen/render_typescript.py` | Schema-derived types/converters or generator component | P01.05.a |
| `tools/codegen/runtime.py` | Schema-derived types/converters or generator component | P01.05.a → P01.05.b |
| `tools/gen.py` | Schema-derived types/converters and references; CLI AST reference and configuration guide generation | P01.05.a → P01.05.b → P02.08.b (bounded partial) |

### P01.05.b: compatibility and generated architecture corrections

Schema compatibility and freshness use generated normalized lock snapshots. Only the root schema-lock.json
is tooling data; nested files retain strict discovery. The independent error-catalog emitter remains the owner
of ErrorCode. Configuration, error and event references are outputs of the same generation pass.

The pure SecretRef value now lives in kernel/generated/_codec.py; platform/config/secrets.py re-exports the
same class and retains the secret-resolution port. Python-only helpers materialize foreign JSON shapes locally
without changing wire validation or the TypeScript model. Foreign nominal value types require an owner public
facade instead of a private import.

Provider-literal checks distinguish only inert slots of byte-for-byte fresh schema-generated output.
Neutral-literal defaults additionally require a matching source-schema default and the existing exact source
allowance. Imports and executable literals retain their architectural checks. These generator corrections
follow the P01.05.a review and have not received independent review in this correction round.


## Материализованные файлы P01

| Файл | Контракт | Владелец |
|---|---|---|
| `src/skm/adapters/memory/core/audit.py` | MemoryAuditLog, MemoryConsumerReceipts | P01.08.b |
| `src/skm/adapters/memory/core/events.py` | MemoryEventReader | P01.08.b |
| `src/skm/adapters/memory/core/idempotency.py` | MemoryIdempotencyStore | P01.08.b |
| `src/skm/adapters/memory/core/outbox.py` | MemoryOutboxStore, CLAIM_TTL | P01.08.b → P10.08.a |
| `src/skm/adapters/memory/config_store.py` | MemoryConfigStore, config table row writers | P02.06 |
| `src/skm/adapters/memory/core/scopes.py` | MemoryScopeRegistry, MemoryScopeTree | P01.08.b → P02.06 |
| `src/skm/adapters/memory/core/state.py` | MemoryBackendState, MemoryCoreState, OutboxRecord, ClockRef, NIL_UUID | P01.08.b |
| `src/skm/application_bus/bus.py` | Bus, RetryPolicy | P01.08.a → P01.08.b → P09.09.a |
| `src/skm/application_bus/middleware.py` | Bus middleware functions | P01.08.a → P01.08.b |
| `src/skm/application_bus/outbox_gc.py` | IdempotencyGc, OutboxGc | P03.05 |
| `src/skm/application_bus/subscribers.py` | EventSink, EventSinkRegistry, SinkDeliveryResult; P03.05: deliver, DeliveryOutcome, DeliverySettings, backoff, EventConfigLoader, OutboxRelayPass | P01.08.a → P03.05 |
| `src/skm/platform/fs/atomic_write.py` | Atomic file replacement | P01.06.b |
| `src/skm/platform/fs/file_lock.py` | FileLock, LockTimeout | P01.06.b |
| `src/skm/platform/fs/safe_paths.py` | Safe path operations | P01.06.b |
| `src/skm/platform/fs/storage_budget.py` | StorageBudget and reservations | P01.06.b |
| `src/skm/platform/logging/envelope.py` | Structured logging fields | P01.06.a |
| `src/skm/platform/logging/setup.py` | Logging configuration and emission | P01.06.a |
| `src/skm/platform/process/argv_rules.py` | Argument validation | P01.06.c |
| `src/skm/platform/process/environment.py` | Process environment filtering | P01.06.c |
| `src/skm/platform/process/identity.py` | ProcessIdentity and diagnostic process facts by number; no signal or reap authority | P01.06.c |
| `src/skm/platform/process/ownership.py` | ChildPipes, OwnershipUnavailable, OwnedProcess, launch, discard, require_support, start_cleanup_worker, adopt_cleanup, recover_cleanups, unattended_note, supervised_note, add_note, describe_failure | P08.02.a follow-up |
| `src/skm/platform/process/runner.py` | ProcessHandle, ProcessResult, run, spawn | P01.06.c |
| `src/skm/platform/process/streams.py` | BoundedCapture, ProcessStreams | P01.06.c |

### Fake runtime admission and finalization (P08.02.a correction)

`FakeRuntime` requires explicit host/test consent through `allow_pgroup_best_effort=True` for its
closed synthetic scenarios with `none` or `worktree` isolation. It has no verified full-lifecycle
containment backend: `landlock`, `container` and plugin isolation profiles, and requests without
best-effort consent, fail with `SANDBOX_UNAVAILABLE` before scenario selection or subprocess spawn.
Consent never downgrades a required profile. Process-group emptiness supplies no L2 reap/reuse proof.

Spawn and collector/writer startup failures surface as `RuntimeStartError(ProviderFailure)`, a
`BackendUnavailable`; a failed start publishes no session. Prompt delivery runs independently of
the collector, so a full stdin pipe cannot block admission or timeout handling. A later stdin failure
finalizes the admitted session. Cleanup/status loss overrides native success, cancellation and timeout
with non-retryable `RUNTIME_CRASHED(reason=cleanup_unconfirmed)`. Observations retain measured ingress
counts and reported usage, use partial capture with `capture_gap` and unknown duration, and ignore
stdout/stderr after result finalization. SIGTERM after an ignored SIGINT records `CancelIgnored(SIGINT)`
and `SESSION_CANCELLED`; SIGKILL escalation yields `CANCEL_IGNORED`. Executor checks do not constitute
the leaf's independent manual review or close the platform limitations below.

### Process ownership (follow-up of P08.02.a; P08.02.a itself stays open)

`run` and `spawn` hold a pidfd that the child opened for itself and passed over a private socket
before its target was released. Every signal is `pidfd_send_signal(PIDFD_SIGNAL_PROCESS_GROUP)` and
every wait is `waitid(P_PIDFD)`, so a reused PID or PGID cannot be reached. Before release, the
owner records the child's `(pid, start_ticks)` and boot ID as diagnostic evidence. Each launch
sets `PR_SET_CHILD_SUBREAPER` in the owner process before forking. The flag stays enabled after
individual launches end and allows the owner to adopt orphaned descendants. Adoption grants no
pidfd. `ProcessIdentity`, `identity_of`, `is_same_process` and `group_alive` by number are evidence
only. A comparison before `kill_group` is check-then-kill and grants no authority. No product code
imports `kill_group`.

| Situation | Contract |
|---|---|
| Not Linux, Linux older than 6.9, a missing Python API, an interpreter that is not executable, a `fork_exec` with other parameters, a refused probe, or failure to enable `PR_SET_CHILD_SUBREAPER` | `OwnershipUnavailable` (`process_ownership_unavailable: …`) before anything starts |
| No verifiable pidfd from the child, including an interpreter whose `execve` failed | `OwnershipUnavailable` (`process_ownership_unbound: …`), with the `execve` report as a note; the target never ran, nothing is signalled, and the owner only closes its socket. An exited bootstrap stays a zombie until the owner exits, because no number may be waited on |
| A verifiable pidfd but no child start ticks before release | The target never runs. The verified pidfd is used to discard the bootstrap |
| Working directory that cannot be entered | `OSError` naming the directory. The bound bootstrap reports it, so the target never ran and the pidfd reaps the bootstrap |
| Foreign waiter or `SIGCHLD=SIG_IGN` consumed the status | `process_status_unknown` (`ProcessLookupError`), never a synthetic exit code or `TIMEOUT_EXIT`, also when the deadline has passed; group cleanup still runs through the pidfd and the failure stays in `_cleanup_failures` |
| Callback, pipe or setup failure, or a signal or reap that fails or stays unconfirmed | The caller gets the failure with the cleanup failures as notes. The pidfd stays open in a registry and a worker keeps sending `SIGKILL` through it until the leader is reaped and the group is empty. It closes only then. A status consumed elsewhere ends the retention once the group is empty |
| A failed-start diagnostic that fails, a failure that refuses a note, or a failure whose text cannot be read, on any start, collect, close or deferred path | The caller still gets the primary failure, and the cleanup after it still runs: the child is settled or retained and every descriptor is closed. A note is evidence only and may be lost this way; an unreadable text is recorded as `<unprintable TYPE>` |
| The supervisor thread of `spawn` cannot start | The streams close first, while the selector can still forget each descriptor, then the discard kills through the pidfd and closes what is left. A failed stream close cannot skip the discard. The caller gets the thread failure |
| Wrapping an owner pipe end in a stream fails | It runs before the fork, so no child exists. The caller gets that failure, wrapped streams and raw descriptors are closed once each, and a number the failed `os.fdopen` may have released is closed only if it still names the same pipe |
| A close fails after the fork | The owner still binds the child if it can. Before release the target never runs. After release the target is killed through the pidfd, because a raise hands the caller nothing to own it with. The caller gets the close failure |
| A cleanup worker cannot start, or dies | `_cleanup_failures` records the failure for a `run`/`spawn` child and the pidfd stays in the registry. A `spawn` child needs no new thread: its supervisor thread attends the cleanup after publishing the failure, with a `cleanup_worker_not_started` note. A `run` or a failed start has no thread to lend: the failure carries a `cleanup_worker_not_running` note, a deferred `run` raises instead of returning a plain result with the observed exit code as a note, and the cleanup stays listed. Everything that still runs retries a listed cleanup with one bounded step through the pidfd and then a new worker: a live cleanup worker or supervisor attending a cleanup, every later `launch`, an explicit `recover_cleanups` (it returns the names still without a worker) and the normal exit of the owner, whose step cannot reap afterwards but still sends `SIGKILL` to the group. The log gets `platform.process.cleanup_worker_not_running` once per lost worker and `platform.process.cleanup_worker_recovered` once it is replaced; the log projection keeps the event and the owner's pid, not the child. **Limitation, kept open:** an idle owner with no such activity runs no cleanup until it exits, and `os._exit` or a crash skips even that step, so the child runs on as in an owner crash. Unattended cleanup is therefore not claimed for this case, and this follow-up does not close P08.02.a. The in-memory lists do not survive the owner |
| The owner forks (`os.fork`, a `multiprocessing` fork, a `preexec_fn`, a fork inside an output callback) | Ownership stays with the parent. An `os.register_at_fork` handler gives the child empty registries and new locks, so its `atexit` entry, `launch` and `recover_cleanups` touch only what the child started itself, and it never takes a lock it inherited. Every inherited `OwnedProcess` and `ProcessHandle` refuses before its own lock: `OwnershipUnavailable` (`process_ownership_inherited: …`), and `terminate` returns the reason `process_ownership_inherited`. A cleanup step of the parent reports itself settled there without acting, `close` and the destructor do nothing, and a copy of the supervisor loop stops. The inherited objects stay referenced, so no destructor runs inside the handler. The copy of each pidfd stays open and unused until `execve` (it is close-on-exec) or the child's exit, because the child may have given its number to another file. A child logs no cleanup event, because the log's locks are not reset at a fork. A fork that runs no handler (libc through `ctypes`, an extension) is told by its pid and fails closed: nothing inherited acts, `recover_cleanups` returns nothing, and `launch` refuses with `process_ownership_unavailable` |
| Owner crash | The pidfd closes with the owner. The child and any adopted descendants are reparented by the kernel and can keep running. Recovery treats them as unknown and must not signal by a recorded identity |
| Orphaned descendants, including those that left through `setsid()` | The subreaper can adopt them, but the leader's pidfd still signals only its original group and reaps only the leader. An adopted descendant without its own pidfd can remain a zombie until the owner exits. A descendant in a different session remains out of reach of the group signal, so an empty group is not a containment proof (adapters §5.3) |

No numeric wait exists before or after the bind. `subprocess.Popen` calls `waitpid` on the number when
its child fails before `execve`, and glibc's `posix_spawn` does the same, so `launch` calls
`subprocess._fork_exec` directly and waits for nothing. That function is private: `require_support`
compares its parameter list and refuses another one, so a Python that changes it cannot start
children until this code is checked against it. The `subprocess.Popen` audit event still fires.

## Материализованные источники config P02.05.a

| Файл | Контракт | Владелец |
|---|---|---|
| `src/skm/platform/config/bootstrap.py` | BOOTSTRAP_SEARCH, BootstrapConfig, load_bootstrap, pool_capacity, apply_process_config, validate_worker_host | P02.05.a |
| `src/skm/platform/config/_bootstrap_schema.py` | BOOTSTRAP_URN, validate_bootstrap_document | P02.05.a |
| `src/skm/platform/config/sources/defaults.py` | defaults_layer | P02.05.a |
| `src/skm/platform/config/sources/packs.py` | PackFragment, pack_layers | P02.05.a |
| `src/skm/platform/config/sources/env.py` | env_layers | P02.05.a |
| `src/skm/platform/config/sources/hookd_runtime.py` | Hook daemon runtime path and sandbox overlap checks | P10.05.a → I-09.2c |
| `src/skm/platform/config/sources/cli_overrides.py` | InvocationOverrides, cli_layers, invocation_layers | P02.05.a |
| `src/skm/platform/config/sources/text_values.py` | parse_text_value | P02.05.a |
| `src/skm/platform/config/sources/document.py` | DocEntry, DocumentProblem, ConfigDocument, decode_document, parse_document, render_document | P02.05.a |
| `src/skm/platform/config/diagnostics.py` | `diagnose_config(*, registry, inventory, store, scopes, packs) -> tuple[CheckResult, ...]` — internal configured-state diagnostics | P02.08.b (engine slice) |

`diagnose_config` accepts an already authorized scope inventory (`Iterable[ScopeRecord]`, including empty
and retained scopes) and the existing `ConfigStore`, `ScopeTree`, `PackConfigSource` ports of the caller's
read-only UoW. The caller owns enumeration, completeness, repeatable-read isolation and authorization:
instance-wide coverage requires `config.read` at instance **before** acquiring inventory or findings.
The engine neither grants that permission nor opens a UoW. Supplied inventory must contain one instance,
unique scope ids and canonical ancestors consistent with the scope tree. Results cover that supplied
inventory only; they do not certify that the caller enumerated every authorized scope.

The engine uses a fresh `ConfigLoader` with no invocation, run or process overrides, no path expansion or
host IO, and the supplied pack port/generation. It validates every supplied work/host scope, including
zero-entry descendants, and both chains at instance even without registered hosts. The existing owner
resolver/validators detect unknown/deprecated/misplaced contributions, ignored locks/rows below a lock,
invalid effective values, failed cross-key validators and blocked validator inputs. The stored-row audit
also checks R9 (`spec.lockable`), retaining deprecated aliases' own lockability. An existing registry
startup failure (`InternalError(CONFIG_REGISTRY_INVALID)`) can be supplied instead of a built registry:
all REG codes and problem identifiers are projected and downstream checks are explicitly not performed;
other errors propagate. This does not recover startup or replace its failure with a usable registry.

Findings use the existing kernel `CheckResult` envelope directly, without integrations targets, new wire
schemas or registry/handler wiring. `details.target` identifies the evaluated scope, `details.detail` is
deterministic JSON containing only allowlisted code/chain/generation and key/section/validator/layer
identifiers (including contributing scope/entry ids and lock provenance); `hint` and `details.path` are
null. Messages are engine-owned constants. Raw values, snapshots, arbitrary diagnostic details, labels,
schema rejection text and validator messages/exceptions are never projected; secret references are never
resolved. Identifiers are bounded and JSON-escaped. Invalid configured keys fail, ignored contributions
warn, and a valid checked chain is ok. Registry failures fail without downstream ok findings.
A rejected pack contribution (settings §B.4: unknown, pack-forbidden or invalid key) is one `warn` finding
per pack whose `contributions` is `[{"level": "pack", "pack_id": …}]`. It is never joined to the effective
key's invalid-key metadata (`reason`, `validator`, `blocked_by`, contribution trace), even when the same
key's effective value fails independently under the same `CONFIG_INVALID` code.

Restart-pending remains a separate **current-process** serving-loader observation. This slice emits
`config.restart_pending` with status `warn`, `state=unknown` and
`reason=serving_loader_observation_required`; a fresh loader's missing baseline never proves no pending
restart. The later provider/authorized platform.Doctor handler owns that observation and public composition;
this entrypoint supplies neither fleet visibility nor CLI, handler, provider or scope inventory APIs.

Bootstrap validates the existing v1 schema before profile selection and validates environment overrides
after selection. Credentials remain SecretRef values or environment literals excluded from repr.
The composition caller supplies the existing checkout profile; this source does not discover checkout state.
`pool_capacity` is the `bootstrap.pool_capacity` check after ProcessConfig: it verifies instance/host identity
and computes the surface minimum from restart values and the caller's enabled background service ids.
For workers both pool helpers require `startup_host: EffectiveConfig`: `worker.capacity` is live and is read
from this validated startup slice, whose instance, host and generation must match ProcessConfig. Capacity
does not become a restart key and is not read from the restart-only ProcessConfig.host mapping.
`apply_process_config` materializes the result for pool construction; HTTP mode has no local database pool.
`validate_worker_host` resolves an already registered state_dir/host.json id and refuses unregistered workers
and hooks before effects. None of these functions registers a host or resolves secrets.

The loader consumes defaults_layer and the ordered pack_layers of active PackFragment values; the pack
adapter supplies effective priorities. Invocation is an ordered tuple of layers (env, files, sets), preserving
each contribution for the resolver's existing authority gates and explain. Unknown environment variables
produce a warning once per process/variable. DocumentProblem findings must be rejected before import writes;
CLI files reject locks. JSON export returns a document mapping, TOML export returns deterministic text.
JSON null requires JSON export because TOML has no null value. TOML strings and quoted keys share one encoder:
control characters including DEL are escaped; non-BMP Unicode scalars remain literal for lossless round-trip.

### P02.08.b: serving-process restart observation

`ServingProcessObserver` accepts the existing serving `ConfigLoader` and observes it through `ConfigStore`
and `ScopeTree` from the caller's read-only unit of work. It never calls `start_process` or builds another
loader. `ServingProcessObservation` covers the captured instance work chain and, when present, the exact
captured host-chain target (including an instance-only host chain). It neither enumerates other hosts nor
claims worker, server or fleet coverage. Invocation layers remain those of the serving loader; run bundles
do not participate. Production startup and handler registration are separate composition work.

The states `snapshot_missing`, `instance_mismatch` and `uncommitted` mean restart status is explicitly
unknown. Only `observed` with no pending keys means no restart-pending changes in the covered chains.
An absent `host_target` means no host snapshot was captured, not that host configuration is unchanged.
Cross-instance observation stops before resolving either chain. Changes on another host are outside this
process's observation. The provider observes `CONFIG_RESTART_PENDING` from both applicable chains, retaining
key, chain, target scope and the captured process generation. Invalid changed restart values also produce
pending findings even though selecting startup values removes them from `EffectiveConfig.invalid_keys()`.
The loader compares configured and captured values as JSON kinds at every depth (`true`, `1` and `1.0`
differ inside objects and arrays too). An unchanged restart value that only takes part in a failed cross-key
validator is not pending; only an unreadable or schema-invalid configured value or a different value is.
This provider makes no configured-state validity claim; that checker is separate.

`to_checks()` returns existing kernel `CheckResult` documents. Each pending finding keeps its loader
severity through the §5.2a mapping (`info → ok`, `warning → warn`, `error → fail`); `CONFIG_RESTART_PENDING`
is informational (settings §B.7), so it is `ok` and stays visible by its message, hint and
`CONFIG_RESTART_PENDING; key=…` detail. Unknown status is always `warn`, and an observed empty comparison is
`ok`. The unchanged schema has string-only `details.target` and
`details.detail`, so scope, key, chain, coverage and process generation are rendered there as metadata;
`details.path` is null. No raw configured/startup values, secret references, diagnostic messages or arbitrary
diagnostic details are projected. Observation does not resolve secrets, run host operations, add production
authorization or modify bus context. Later handler assembly can inject the typed bootstrap provider.

### Policy follow-up: empty host conjunction and the read-only subset

`check_tool_call` (policy §5.3 N1) separates `allowlist` that admits no host from `none`: `web.search` stays
allowed and an unknown destination asks, where `none` denies both. `urn:skm:policy:profile:v1#/$defs/network_policy`
needs a host under `allowlist`, and a profile keeps that input rule: it states "no host" as `none`. A view reports
what composition reached, so `urn:skm:policy:view:permission-set:v2` has its own `network_policy`, which admits
`{"mode": "allowlist", "hosts": []}` and still refuses hosts under `none`/`any`. `view_document` states that form,
`policy.effective_permissions` returns it under the catalog default (`policy.ceiling.network = allowlist` with an empty
`network_allowlist`) and `policy.explain_permissions` reports the same value. `permission_set_from_view` restores a
policy that admits no host, with the same `permissions_digest` and the same decisions; `is_subset` against it reports
every requested host and `any` as widening. Decisions and digests do not change.

`policy.ceiling.network = any` alone does not leave this state. The mode takes the strictest value, so
`workspace-contained` stays `allowlist`, and the ceiling always adds `network_allowlist` as a host list, so that list stays
empty. `any` is reached only when the profile and every layer allow it; hosts are admitted only by naming them in
`network_allowlist` and in every other list.

A view may not widen inside a major (`tools/schema_check.py` compares outputs in reverse; a new property on a closed output needs a new major), so the state takes a new major: `permission-set:v2` and
`effective-permissions:v2`, which references it. The `v1` files keep their contract and lose only `x-skm-codegen`, which
is outside the lock snapshot: `PermissionSetView` and `EffectivePermissionsView` are generated from `v2`. The views are not
stored, so no data migration applies. `policy.public.effective_permissions` returns a `PermissionSet` and renders no view.

`is_subset` keeps a pattern of the ceiling when the request lists it verbatim or holds a provably wider one: the same
prefix (which compiles alone), at least the same literal names in the final group, and the same tail `(\s|$)` or none.
Any other shape needs its exact text, so an unprovable inclusion is still reported. Under this proof the built-in
`read-only` document is a subset of the built-in `workspace-contained`, with both profile files unchanged:
[`read-only.toml`](../../src/skm/modules/policy/profiles/read-only.toml) keeps its legacy `ask_patterns`, and the
files stay the packaged profiles under [`profiles/`](../../src/skm/modules/policy/profiles/). Against a composed ceiling the request must still carry
the deny patterns of `policy.ceiling.commands_denylist`.

Steps C3 and C7 also read the wrappers and program of each parsed command, so `'sudo' ls` and `env 'kill' 1` are judged
like `sudo ls` and `env kill 1`; quoted arguments stay words. This is a tightening beyond the text of §5.3. A program
written with a path (`/usr/bin/sudo`, `env /bin/kill`) and the arguments behind a quoted program (`'dd' of=/dev/sda`)
remain outside these patterns: the patterns exclude a preceding `/` by design and the isolation profile is the boundary.

### P09.01.a: the permission proof and the boundary with P09.01.b

`install_candidate` compares each agent profile with the ceiling (`effective_permissions` of `policy.default_profile`)
through `policy.public.is_subset`, and policy alone decides which patterns a request keeps. Under the catalog default
`read-only` is inside `workspace-contained`, and the eleven profiles under [`agent-profiles/`](../../resources/packs/core/agent-profiles/) with the manifest
of [`pack.toml`](../../resources/packs/core/pack.toml) sync. The request is not narrowed to pass: a profile without `requires_host_flag` is composed
with `allow_unconfined = True`, because a flagged host runs it with `none`, and the ceiling stays composed without the flag.
A custom default that itself carries `none` therefore refuses a profile equal to it. That refusal fails closed and is accepted.

The leaf delivers the immutable registry and the builtin sync. External admission stays closed until P09.01.b:

| Path | State after P09.01.a | Owner of the rest |
|---|---|---|
| `extensions.sync_builtin_packs` | installs; resources carry the deterministic 6-check compatibility report (`license`, `provenance`, `injection`, `budget`, `tools`, `layout`) | P09.01.b adds `domain/compat.py: check_resource` |
| `extensions.install_pack` (`operator`, `third_party`), also `dry_run` and a replay | `CAPABILITY_UNAVAILABLE`, `reason: compat_scanner_unavailable`, `owner: P09.01.b`, no rows, no events | P09.01.b: scanner, payload limits, host read |
| `allow_quarantine = false`, a pack without resources | the same refusal | P09.01.b |
| bundle with `agents` | `CAPABILITY_UNAVAILABLE`, `reason: bundle_permission_check_unavailable` | P10 |

`CompatVerdict` has two values and `quarantine` means a `FAIL` (extensions §4.10). Every installed pack,
builtin or external, requires every resource to carry a completed 6-check compatibility scan (`item.scanned`),
and any `FAIL` quarantines the resource version. External admission through `extensions.install_pack` stays
closed with `compat_scanner_unavailable` until P09.01.b wires `domain/compat.py` and host pack reading.

### P09.01.a: an equal digest is no proof of equal files

`resource_digest` stays the normative stream of extensions §4.14: `path`, a zero byte and the content, without length framing. It
stays comparable with legacy `skill_content_hash` and therefore collides: `{a.md: b"1b/two.md\0" + b"2"}` and
`{a.md: b"1", b/two.md: b"2"}` hash alike, and a skill may hold both layouts under `references/`. `install_candidate` keeps the
external digest and compares the stored canonical rows in the transaction of the install, under the registry lock:

| Situation | Result |
|---|---|
| same version and digest, same manifest, same resource pairs, same paths and bytes | `already_installed` |
| same version and digest, other paths, bytes or manifest | `EXTENSION_DIGEST_CONFLICT`, `reason: digest_collision`, no rows, no events |
| new version whose pair already holds that digest with other files, in any pack or state | `EXTENSION_DIGEST_CONFLICT`, `reason: digest_collision`: a pin by digest (§4.12 step 6) must not reach other content |
| new version whose pair already holds that digest with equal files | installed: the same content may arrive in two versions |
| a stored row, file or body is missing, or the stored files no longer prove their metadata and digest | `CAPABILITY_UNAVAILABLE`, `reason: stored_evidence_unavailable` |

Extensions §7.1 step 7 reads as if the digest alone decided; this comparison is stricter and the spec text is owed the same change.
Rows written before this check are not re-examined. The check runs after `_require_compat_scan`, so the refusal of external
admission above stays first, and only behind the `ext.install` authorization of the bus. A replay reads the bodies of every resource
of the version: bounded by the limits of the kinds, and paid only by a replay.
