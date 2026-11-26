# Porting log

Port behavior and knowledge into owned layers, not legacy imports or packaging.
The donor at `../swissknifeman/` is read-only. Source paths below are provenance
text, not links to a donor tree that may be absent. Component recommendations
are recorded in this log. Current module boundaries are the
[codebase map](architecture/CODEBASE-MAP.md).

## Antigravity and late legacy fixes

Compared the legacy mainline from 2026-10-26 through the published
`417049811` tip. The legacy checkout served as read-only provenance.

| Legacy work | SwissKnifeMan 2 outcome |
|---|---|
| `9e309d952`, `86cf7809f`, `fce72271d`, `8b92cc456` | The AGY wire protocol now uses the owned worker runtime lifecycle, with run-bound identity and read-only worktrees. The legacy native executor's blanket tool approval is out of scope for the new worker's policy guarantees. |
| `dd7721e61`, `0e8c5f0d4`, `96e21d3c9`, `6696c8721`, `a4fc57e6a` | Port terminal auth and individual quota classification, deduplicated error-step recovery and incomplete accounting. The adapter preserves completed responses after transient steps and rejects AGY 1.5.13 partial print-timeout results. Persistent AGY sessions are unsupported. |
| `cd5a4dc53`, `417049811` | Project instructions, migrated bundle rules and skills use the supported `.agents` discovery paths and SKM ownership records. No native hooks or implicit MCP server configuration is installed. The adapter removes private scratch after confirmed termination (and on startup failure) while retaining the redacted transcript; Grok also cleans step `tmp`, and check execution defaults `COMPOSER_PROCESS_TIMEOUT=0`. New pack versions preserve immutable installed copies. |
| `df7140774` | The exact Codex `gpt-6.1-terra` selector is listed in the local cache and admitted for explicit implementation and review routes. The preferred classes retain their existing selectors. |
| `74f40a969` and phase-pilot fixes `13848cb84` through `21278d07a` | Check selection uses attempt rounds and explicit gate state. The legacy conductor's timestamp-keyed retry and local phase wait files have no equivalent in these paths. |
| Review recovery and provenance, including `5128f025c`, `c31b1593b`, `c80ea0f30`, `49d64c68d` | The new engine ties review to an output and uses typed receipts and deterministic result handling. Legacy Markdown/JSON recovery must not bypass these gates. |
| `62e77f772`, `17d2059b7`, `313481f75`, `0866c87d8`, `72a3427ac` | The new checkout fingerprint uses no-follow reads and a checkout/index guard. Evidence lives under worker state. The old filesystem inventory exclusions, batched Git fallback and attempt stream resume logic do not map directly. |
| `ab924db2c`, `a38086afd`, `404279208`, `ab70a3f59`, `d168081fd`, `ba8687842` | Context manifests, role requirements and route pins carry the corresponding authority in SKM 2. Migrating legacy retry flags or scoped route substitutions would change its immutable run inputs. |
| `385ce7512`, `64a17a539`, `db071cbff` and related supervisor fixture fixes | The legacy seccomp/record format is separate. SKM 2 documents the Landlock metadata limit and treats stronger isolation as a separate capability. The provider lifecycle and cleanup regressions use the current process supervisor. |

Manual review of the port is pending. Executor verification and an independent
AGY review are separate.

## P00.06 — documentation and links

This leaf implements a new documentation/tooling contract; no legacy code is
ported. Sources, by name: engineering standards §8, tooling §§2 and 4,
architecture notes 02 through 08, decisions 0001–0024 and the execution addenda.
Those decisions are now the [ADRs](adr/README.md) and the
[architecture pages](architecture/overview.md).

Preserved guarantees: canonical module ownership and DAG, pure domain and explicit
ports, transactional state/events/receipts, fenced ownership, output-bound review,
post-integration acceptance, two-phase context, permission narrowing and read-only
legacy provenance. Execution addenda override historical shorthand. Product paths
start at the root. Proposed ADR statuses are preserved; no review is inferred.

## P01.Z — foundation contract verification

This leaf adds verification records, not another port or runtime implementation.
The donor was not accessed or modified. Executor evidence, exact commands,
consumer matrix, successful conductor checks.4 V1 and remaining follow-ups are in
[P01.Z status](status.md#p01z-executor-validation). Claude Opus/high completed
an independent automatic review of checkpoint `601140a3fc7c` with GREEN, no
findings and one documentation question. This documentation update follows that
review and has not been independently reviewed. Separate manual review was not
conducted.

| Component / existing destination | Provenance and retained contract | Focused proof in this execution |
|---|---|---|
| Digest/v1: `src/skm/platform/jsonc/canonical.py`, `digest.py` | P01.03 identifies `packages/aicore/lib/aicore/util/digest.py` and `packages/aicore/schemas/digest/v1/vectors.json` as PORT-AS-IS. The checked-in `tests/fixtures/digest/vectors.source.txt` records donor commit `0d6a393` and snapshot SHA-256 `de6d74a9817c10c9ede14703ca5511b12a5c49f642bbfb42dbaea9d6c2c054eb`. Provenance was checked against the local fixture, without claiming a fresh donor comparison. Canonicalization v1 retains compact UTF-8, code-point key order, no normalization/floats and lowercase `sha256:` tags; API names follow the new owner. | `tests/unit/platform/jsonc/test_digest.py`: 47 passed, including all eight byte-preserved vectors, permutations, malformed tags and checksum corruption refusal |
| Schema compatibility: `tools/schema_check.py` | P01.05 identifies `packages/aicore/lib/aicore/util/schemacompat.py` as PORT-REFACTOR; the product tool declares that recursive comparer lineage. No donor revision/digest beyond available provenance is invented. Current schema graph, offline resolution, reverse output comparison, shared definitions, lock and generation belong to the new repository. | Five direction tests, six generated-drift refusals and one deterministic lock test passed as part of the 24-test selection; drift tests leave generated bytes and lock unchanged even when lock update is requested |
| Filesystem IO: `src/skm/platform/fs/` | Existing implementation is assessed against P01.06 and the current owner contract; this leaf does not certify a byte-for-byte donor port. Same-directory atomic replacement, explicit failure, primary-exception preservation and resolved path containment are retained. A directory-sync failure after replace reports failure even though new bytes are visible. | Eight injected failure stages in `test_atomic_write.py` and four contained/escaping symlink policy combinations in `test_safe_paths.py` passed in the same 24-test selection |
| Process supervision: `src/skm/platform/process/` | Existing implementation uses explicit argv, cwd and filtered environment, bounded capture and process-group cleanup. No shell evaluation or ambient secret inheritance; leader exit alone does not establish descendant cleanup. This leaf asserts only the local scenarios actually exercised, not cross-platform support or real provider admission. | Four selected `test_runner.py` cases passed: literal argv/environment/stdin, simultaneous bounded output with large input, timeout and normal leader exit with descendant writers |

The generated tree matched a read-only `tools/gen.py --check` pass. That initial
pass rewrote no generated output, fixture or schema lock; the later corpus-fixture
correction is recorded below. The 69-test declaration/bus/host
selection verified canonical facade dependencies, atomic command side effects,
replay authorization, rollback, gateway kinds and host lifetime. The P02–P10
inspection resolved 39 Protocol references to their existing owners; 878 product
Python files contained no legacy imports from the inspected package roots.

The global `make gen check`/V1 result belongs to the conductor. The existing
P08.02.b `StreamParser` catalog gap and un-narrowed `HostContext` annotations are
explicitly retained in the status handoff. IO fault injection described here uses
existing isolated tests, not product test hooks. No production runtime or donor
command was executed, no dependency documentation outside the write set was
changed, and no commit or review-state transition was made.

Correction round executor.2: conductor V1 exited 2 at fmt-check; the initial
focused reproduction exited 1. The resumed input explicitly authorizes
`tests/unit/application_bus/test_registry.py`. Its incoming multiline assertion
and import-order correction were preserved: the formatter made no further change,
scoped format/lint checks exited 0, and all 43 registry tests passed. No expected
result or production behavior was changed. V1 has not been rerun by the executor;
the conductor result at that time was exit 2. See the
[correction evidence](status.md#correction-round-executor2-v1-formatting-failure).

Correction round executor.3: the conductor's second V1 passed format/lint and
exited 2 at typecheck. The initial focused Pyright invocation reproduced all 45
errors (exit 1), before the coordinator expanded the scope to those seven files.
The incoming test/registry fixes were preserved. UoW typing uses a private bound
outbox callback and lifecycle counter updates without adding public helpers;
registry runtime guards remain intact. Nested JSON narrowing, read-only test-app
properties, module export access, Mapping support and removal of unnecessary
ignore comments resolve the other diagnostics. Scoped Pyright, Ruff lint and
format checks now exit 0. The
[typecheck handoff](status.md#correction-round-executor3-v1-typecheck-failure)
records every repair path and invariant. The first affected-test run had 187
passes and one failure in the new negative fixture, which accidentally omitted
the subscriber's valid event. After retaining that event, all 43 registry tests
passed; the other 145 affected cases had already passed. No test expectation or
check was weakened. Scope is no longer blocked, but full V1 and independent
review were unproved by those focused runs; the conductor V1 at that time was exit 2.

Correction round executor.4: checks.3 confirmed format/lint and both typechecks
green, then stopped at one stale corpus snapshot (V1 exit 2; 2,929 tests and
282 subtests passed). The exact snapshot test was reproduced separately, exit 1.
Only `tests/fixtures/codegen/current-corpus/schemas.json` differs from its current
source: its event-envelope `stream_kind` enum lacks `runtime`, `hook_delivery`
and `vault_note`, which the product schema, kernel and conventions already agree
on. All other 783 schemas, the 135-example snapshot and the two-document snapshot
match their respective sources. The
[snapshot handoff](status.md#correction-round-executor4-corpus-snapshot-failure)
initially requested this one fixture write path. The resumed input authorizes it
and supplies the corrected snapshot. Comparison with HEAD confirms only those
three enum additions in one event-envelope field; all other objects are unchanged.
The exact original test now exits 0 (1 passed in 0.80s), with its assertions
unchanged. No product schema, generated code or other snapshot was modified.
Earlier repairs are retained. The later conductor checks.4 V1 exited 0:
2,930 passed, 1 deselected, 282 subtests passed, and the separate architecture
suite passed 334 tests. The earlier checks.3 exit 2 remains historical.

The supplied external `review-followups.json` was read with its SHA-256 verified
against `b05f30f55d254dc2c1be5b0fa988a1ed0a969fd9aed34b36539f057d1a6281ad`.
Its [P01 follow-up summary](status.md#external-p01-follow-up-register) preserves
recorded corrections, review limits and unresolved questions without making the
journal normative or declaring its questions current defects. The current nine
service names remain descriptive: `BACKGROUND_SERVICES` is empty, real factories
belong to future leaves, and no full runtime §6 readiness is asserted. Neither
passing tests nor journaled reproductions count as independent manual review of
P01.Z; that review remains not conducted.

## P02.Z — configuration acceptance

This leaf records verification only; it adds no port. The donor tree
(`../swissknifeman/`) is not present in this environment and was not accessed.
The provenance below comes from the settings porting notes §A.16, the aicore
legacy map §4 and the source notes in the test docstrings. It is not a fresh donor
comparison. Current settings behavior is [`modules/settings/`](../src/skm/modules/settings/)
and the [configuration engine](architecture/config-engine.md). Commands, counts, sample
comparison and gaps are in [P02.Z status](status.md#p02z-executor-validation).
Independent manual review was not conducted.

The original P02 phase asks for the main v2 changes to be recorded:

- settings levels `workspace`, `plan`, `run` and `host` replace the
  `machine`/`project` files;
- settings live in the database (entries, history, generation) instead of TOML
  layer files;
- values can be non-scalar (maps, records, arrays with `deep_merge`, `union` and
  `append_unique`);
- `narrow` is a key property in the schema, not a floor table in code.

### Retained legacy scenarios

| Legacy source (§A.16) | Retained scenario | v2 regression proof (passed in this run) |
|---|---|---|
| aicore `test_model.py`; `model.py:1034-1115` `resolve` | Defaults from the schema; a missing key falls through; unset restores the default; the merged value is validated again (fail closed); a forbidden level or unknown key does not apply; resolved values are immutable | `test_resolver.py` (50), `test_merge_replace.py` (26), `test_loader.py` (25), `test_frozen.py` (27) |
| `model.py:686-893` `_State` | Unset, then append, then plain values in one layer; set plus append of one key is refused | `test_sources.py::test_set_append_order_and_invalid_append_cannot_change_scalar`, `::test_document_problems_prevent_ambiguous_or_unknown_writes`. The code is `CONFIG_INVALID`; the reason is `conflicting_ops` (§B.11), not `set_and_append` as §A.16 says |
| `model.py:780-842`, `:872-881` `_unset`/`_reset` | Unset resets to the default and hides farther levels; for a map entry it removes the entry; refused for `narrow`/`union` | `test_merge_replace.py::test_unset_restores_the_default_and_hides_everything_but_the_default`, `test_merge_deep.py::test_unset_resets_to_the_default_map`, `test_merge_narrow.py::test_unset_and_append_are_refused_for_narrow_keys`, `test_merge_union.py::test_unset_is_refused`, `settings/application/test_commands.py::test_unset_is_refused_for_monotonic_keys` |
| aicore `test_env.py`; `model.py:971-1010` `_apply_env` | Variable name from the key path with `__`; an unknown variable warns once; values parse by leaf type | `test_sources.py::test_unknown_env_warns_once_per_process_variable`, `::test_protected_values_are_ignored_and_visible`; manual env → `--config` → `--set` scenario |
| `model.py:650-684` `parse_value` | Integer/number and `true/1/yes/false/0/no` text parsing | `test_text_values.py` (31) |
| aicore `test_explain.py`; `ExplainEntry` | Value, where it was set, overridden contributions | `test_explain.py` (19) with the `explain.txt` golden; `test_queries.py::test_explain_matches_the_example_statuses_on_the_same_levels` |
| aicore `test_maps.py` | Maps merge field by field; entries can be removed | `test_merge_deep.py` (19) including `$unset` at any depth and partial records; `test_frozen.py::test_work_policy_field_merge_lock_unset_and_all_four_frozen_keys` |
| aicore `test_secret_redaction.py`; `secrets.py:18-110`; `model.py:713-727` | A secret is only a reference; its value is never printed; masked `repr` | `test_secrets.py` (564), `test_secret_ref.py` (14), `test_write_rules.py` R5/R6, `test_explain.py` secret cases, CLI `test_secret_reference_round_trip_never_resolves_a_secret` |
| orch `test_authority_monotonic.py` (10 tests); `options.py:99-112`, `:278-305` | An operator level sets the ceiling and nearer levels only tighten it; a revocation reaches frozen runs | `test_monotonic.py` (13 parametrized cases), `test_resolver.py` (ACCESS_WEAKENINGS port), `test_loader.py::test_a_nearer_level_cannot_weaken_a_floor_and_revocation_reaches_frozen_runs` |
| `model.py:1144-1148`, `:1240-1388` layer revision/patch | Compare-and-set on a revision; a stale write changes nothing | `test_commands.py::test_update_checks_the_expected_version_and_a_stale_one_writes_nothing`, `test_import.py::test_cas_digest_guards_the_whole_scope` |
| gui `core/config.py:292-356`, `:423-463` preview/commit | Before/after diff of effective values; refusal without confirmation; the applied change is audited | `test_import.py::test_dry_run_of_the_example_writes_nothing_and_apply_matches_the_preview`, `test_commands.py::test_confirm_keys_need_confirmed`, CLI `test_permissions_and_confirmation_cannot_be_bypassed` |

### Dropped or changed legacy scenarios

| Legacy behavior | Disposition | Reason / owner contract |
|---|---|---|
| TOML layer files (`machine`, project `config.toml`, workspace `local/config.toml`), `schema_version` header and `CONFIG_VERSION_*` | Dropped | Settings are database levels; TOML stays only for import/export and invocation `--config` (§A.16, §B.11) |
| Provenance by file and line (`toml.LineIndex`) | Changed | `LayerRef` with level, label, entry id and row version |
| `toml_edit` comment-preserving editor, `flock`, timestamped backups (10 kept), read-back rollback | Dropped | Writes are database transactions with `expected_row_version` / `expected_entries_digest` |
| `aicore config init/example/paths/migrate-home` and `config.example.toml` drift generation | Dropped | Not in the v2 `skm config` verb set (schema, get, explain, set, unset, remove, lock, unlock, import, export, entries, history) |
| `SKM_<MODULE>_…` env prefix and the `SKM_<MODULE>_ROOT` skip | Changed | `SKM__` prefix without a module id, only for keys with `override = true` |
| `CONFIG_CONFLICT` | Changed | `CONFIG_INVALID` with a reason |
| `<scheme>://<path>` secret references; a global resolver registry | Changed | `secret://<scheme>/<path>`; resolvers are injected objects |
| GUI preview store with a TTL | Dropped | `ImportConfig` dry run returns the preview without storing it |
| Legacy JSON fallbacks (`.swissknife.json`, `.swissknifeman/config.json`, ADR 0050) | Dropped | Optional legacy data import is P14, not part of the engine |

Postgres contracts, DDL and the e2e embedded-Postgres CLI scenario of §A.15
are not proved by this leaf; they belong to P03.06 and P03.03.c. No legacy import
was added. The checks were the focused suites listed in the status record; V1
belongs to the conductor.

On 2026-10-29 the regression proofs in the retained table passed again on
`89a82c05a`, after the test-only pyright fix `d3e26bf81`. The run had 2,095
passed, and no product file changed. The retained and dropped scenarios are
unchanged.

## P03 — M1 config on PostgreSQL (P03.Z)

This leaf records verification only; it adds no port and no legacy import. The
donor tree (`../swissknifeman/`) was not accessed. The scenario implements the
new M1 contract from testing acceptance §9 and the init and config CLI examples, as
[`tests/e2e/test_m1_config_on_postgres.py`](../tests/e2e/test_m1_config_on_postgres.py).
Its steps, the commands actually run
and the pending PostgreSQL proof are in
[P03 status](status.md#p03--m1-config-on-postgresql-p03z). Independent manual
review was not conducted.

Two deliberate differences from the examples, both following the current
product contract:

- The migration count is not hard-coded. The example shows 21 migrations
  (`0001 … 0021`); the test compares against the packaged chain, currently
  0001–0029.
- The explain status of a farther narrow level is the engine's `used`
  (`merge.py` `TraceStatus`), not the example's display word `narrowed`.
- A `config-changed` event may have no `actor_id`. The envelope field is optional,
  and the PostgreSQL events store leaves it `NULL`. The test proves the owner as
  actor through the allowed audit row of the same `request_id`.

## P04 — access and workspace acceptance (P04.Z)

Phase P04 delivers the `access` (M2) and `workspace` (M3) modules and verifies
their end-to-end CLI lifecycle and cross-workspace security boundaries in
`tests/e2e/test_p04_workspace.py` and `tests/security/test_cross_workspace.py`.
Full validation evidence is recorded in
[P04 status](status.md#p04--access-and-workspace-acceptance-p04z). Independent
manual review was not conducted.

### Ported and rewritten components in P04

| Donor source (`../swissknifeman/`, read-only) | Destination in `src/skm/` | Classification | Retained guarantees & intentional changes |
|---|---|---|---|
| `packages/aicore/lib/aicore/workspace/remotes.py` (`normalize_git_remote`, SCP/HTTPS/SSH parsing) | `src/skm/modules/workspace/domain/remote_url.py` (P04.03) | `PORT-AS-IS` (pure domain function) | Normalizes SCP-like `git@host:org/repo.git`, `ssh://`, `https://`, and `git://` URLs to canonical lowercase host + stripped `.git` key; rejects `file://`, local paths, credentials in URLs, and query/fragment parts with `SCHEMA_INVALID`. |
| `packages/workspace/lib/workspace/projects.py` (project-repository attachment rules and mount validation) | `src/skm/modules/workspace/domain/attach.py`, `src/skm/modules/workspace/domain/aggregates.py` (P04.03, P04.04) | `REWRITE-KEEP-IDEA` | Enforces single `primary` repository per project, unique `(project_id, repository_id)` and `(project_id, mount_dir)`, safe relative `mount_dir` (no `..`, absolute paths, or overlapping prefixes), and refuses mutations on archived projects with `PROJECT_ARCHIVED` and cross-workspace repositories with `CHECKOUT_MISMATCH`. |
| `packages/workspace/lib/workspace/gitutil.py` (local git repository inspection) | `src/skm/adapters/git/cli_git.py`, `src/skm/modules/workspace/host/bind_checkout.py`, `src/skm/modules/workspace/host/verify_checkout.py` (P04.03, P04.05) | `REWRITE-KEEP-IDEA` | Subprocess git probe lives exclusively in the host adapter (`GitProbeGateway`); domain and application layers have zero filesystem or subprocess I/O. `verify_checkout` compares `expected_head`, `expected_branch`, dirty tree, and remote URL, then records `observed_head` via `RecordCheckoutsVerified`. |
| New in v2 (`access` RBAC, tokens, scope chain, worker rotation) | `src/skm/modules/access/`, `src/skm/adapters/postgres/access/`, `src/skm/modules/workspace/host/rotate_worker_token.py` (P04.01, P04.02, P04.05) | Green-field v2 contract | SHA-256 hashed `skm_` bearer tokens with 8-char lookup prefix, monotonic scope chain (`instance -> workspace -> project`), worker and assignment-scoped tokens, atomic `0600` token file persistence, and lost-response recovery on token rotation. Worker tokens use `worker-{worker_id}` naming to satisfy PostgreSQL `ck_api_tokens__name`. |

## P05 — planning acceptance (P05.Z)

Phase P05 delivers the `planning` (M4) module (specification v1 schema and
domain model, stable UUIDv7 entity identity across rekeys, 3-way draft rebase,
readiness validation and 68-code legacy finding catalog, execution graph
compiler, PostgreSQL and memory repositories with dual-stored typed tables and
canonical JSONB payloads, atomic change batches, bounded outline and UTF-8
text-window queries, portable JSON export/import, service review-request plans,
and the `skm plan` CLI family) and verifies its end-to-end PostgreSQL lifecycle
in `tests/e2e/test_p05_planning.py`. Full validation evidence is recorded in
[P05 status](status.md#p05--planning-acceptance-p05z). Independent manual
review was not conducted.

### Ported and rewritten components in P05

Per the planning porting notes §16 and the code-by-code
finding table in [planning findings](porting/planning-findings.md), current code is
[`modules/planning/`](../src/skm/modules/planning/). Legacy
`packages/planner/lib/planner/plan/` from `../swissknifeman/` (read-only; not
accessed during P05.Z) is classified as follows:

| Donor source (`../swissknifeman/`, read-only) | Destination in `src/skm/` | Classification | Retained guarantees & intentional changes |
|---|---|---|---|
| `packages/planner/lib/planner/plan/model.py` (key grammar, enums, sort order) and `plan/edges.py` (reference field table) | `src/skm/modules/planning/domain/{display_keys,references,specification}.py` (P05.02.a) | `PORT-AS-IS` / `PORT-REFACTOR` | Key regexes use `re.fullmatch` + `re.ASCII`; `id_sort_key` -> `key_sort_key`; `EFFORT_ORDER` drops legacy `ultra` (mapped to `max` in P14); qualified refs (`PLAN7.P2.4`) allowed only on CLI/API; `DOC-…` -> `material/<key>`; execution task statuses stay in `execution`. |
| `packages/planner/lib/planner/plan/ops.py` and `plan/refs.py` (`merge_patch`, `OWNED_FIELDS`, batch edits, expected revision) | `src/skm/modules/planning/domain/{changes,text_edits,identity,canonical}.py` (P05.02.a, P05.02.c) | `REWRITE-KEEP-IDEA` / `PORT-REFACTOR` | Retains RFC 7396 merge-patch semantics, validate-before-write atomic batch (`1..500` ops, zero partial writes on failure), `expected_edit_version` CAS, and owned-field refusal (`FIELD_OWNED` on `id`, `key`, `item.phase`, `check.owner`); adds `replace_text` by full-field UTF-8 digest and drops filesystem discovery. |
| `packages/planner/lib/planner/plan/{parallel,lifecycle,units}.py` (`ready_set`, `footprint`, `next`, `route_groups`, unit deps) | `src/skm/modules/planning/domain/{compile_graph,ready_preview}.py`, `validation/globs.py` (P05.02.b, P05.03.a) | `PORT-REFACTOR` | Compiles `ExecutionGraph` (`COMPILER_VERSION = 1`) with `UNIT_PARENT`/`UNIT_DEPENDS_ON` edges, item/phase gates, batch barriers (`advisory`, `recommended`, `required`), cycle-witness detection (`dependency_cycle`), and `ready_preview`; lifecycle state transitions move to `execution`. |
| `packages/planner/lib/planner/plan/check.py` (55 check codes + 13 validator/lifecycle codes; `globs_overlap`) | `src/skm/schemas/planning/data/finding-codes.json`, `src/skm/modules/planning/domain/validation/{findings,context,globs,pipeline,rules_*}.py` (P05.01, P05.03.a–b) | `REWRITE-KEEP-IDEA` / `PORT-REFACTOR` | All 68 legacy finding codes are accounted for in `finding-codes.json` and [planning findings](porting/planning-findings.md): 43 mapped into 46 canonical v2 codes (15 new v2-only) across 10 categories, and 25 in `dropped_legacy_codes` (23 schema/execution/checkout drops plus 2 language/repo-specific overlay candidates: `execution_commit_instruction`, `execution_rules_conflict`). `RuleFailure` isolates rule exceptions without silently marking plans invalid. |
| `packages/planner/lib/planner/plan/{query,refs,catalog,stats}.py` and `plan/{store,workspace,gitops,bridges,cli,views,snapshot,templating}.py` | `src/skm/modules/planning/application/queries/*`, `domain/{diff,stats,id_space}.py`, `src/skm/adapters/postgres/planning/*`, `src/skm/entrypoints/cli/commands/plan.py` (P05.05–P05.08) | `REWRITE-KEEP-IDEA` / `DROP` (file store) | Drops split file storage, file locks, and `YYYY.MM.DD-№N-CODE` directories (legacy import moves to P14; Markdown projections move to `exports`; `readiness`, `execution`, `budget`, `scout`, `context` move to `execution`/`context`). PostgreSQL `skm_planning.*` stores dual normalized `revision_payloads.document` and typed tables (`load_typed_document == get_document`). |
| Legacy refusal codes in `lifecycle.py`, `ops.py`, `units.py`, `store.py` (planning §16.2–16.3) | `src/skm/modules/planning/application/commands/*` (and downstream `execution`/`runtimes`/`workspace`) | Mapped / `DROP` | Planning owns `PLAN_NOT_READY`, `INVALID_REFERENCE`, `NOT_FOUND`, `AMBIGUOUS_REFERENCE`, `FIELD_OWNED`, `SCHEMA_INVALID`, `ID_CONFLICT`, `VERSION_CONFLICT`, `BASE_REVISION_CHANGED`, `NO_CHANGES`, `REBASE_CONFLICTS`, and idempotent `archive_plan` (`changed=false`). Execution/runtime/workspace codes (`LEASE_LOST`, `INVALID_TRANSITION`, `BLOCKED_BY_DEPENDENCY`, `NOT_ACCEPTABLE`, `RESULT_INVALID`, `DECISION_REQUIRED`, `ROUTE_UNDERSHOOT`, `REWORK_LIMIT_REACHED`, `CHECKOUT_MISMATCH`) move to their owning modules; file-lock/path/log codes (`PLAN_LOCKED`, `LOG_INVALID`, `PLANS_MIGRATED`, `PLAN_SOURCE_UNBOUND`, `PROJECT_PATH_OVERRIDE_FORBIDDEN`, `DECISION_NOT_OPEN`, `ARCHIVE_EXISTS`, `PLAN_NOT_DONE`, `MESSAGE_REQUIRED`) are dropped. |
| New in v2 (`rebase`, `restore_revision`, `preview_publication`, bounded queries, export/import base guard, service review plan) | `src/skm/modules/planning/domain/{rebase,rebase_helpers,review_request,material_status}.py`, `application/{publication_candidate,revision_writer,source_reader}.py`, `public.py` (P05.04–P05.10) | Green-field v2 contract | Stable UUIDv7 `entity_id` across rekeys (`plan_entity_identities`), 3-way structural rebase in `entity_id` space (`REBASE_CONFLICTS`), `preview_publication` / `--expected-content-digest` CAS (`candidate_changed`), append-only `restore_revision` (`PlanRevisionPublished` + `PlanRevisionRestored`), explicit `source_base_revision_id` on portable export/import, bounded `list_entities` & UTF-8 `read_text` windows, and hidden `purpose='review_requests'` service plans (`publish_review_request_revision`, `get_plan_summary`). |

## P06 — artifacts and Milestone M2 acceptance (P06.Z)

Phase P06 delivers the `artifacts` (M3) module (content-addressed blobs, staging
and two-phase upload coordination, `File` / `FileVersion` lifecycle,
classification lattice and content-safety rules, version-scoped worker grants,
read-only host materialization, janitor/orphan reconciliation, and the `skm file`
CLI) and closes **Milestone M2** ("план с закреплённым артефактом") with
`planning` (M4) in [test_m2_plan_materials.py](../tests/e2e/test_m2_plan_materials.py).
Full validation evidence is recorded in
[P06 status](status.md#p06--milestone-m2-plan-with-pinned-artifact-acceptance-p06z).
Independent manual review was not conducted.

### Ported and rewritten components in P06

Per the artifacts porting notes §16, current code is
[`modules/artifacts/`](../src/skm/modules/artifacts/). Legacy artifact,
content-safety, and blob-handling logic from `../swissknifeman/` (read-only; not
accessed during P06.Z) is classified as follows:

| Donor source (`../swissknifeman/`, read-only) | Destination in `src/skm/` | Classification | Retained guarantees & intentional changes |
|---|---|---|---|
| `packages/workspace/lib/workspace/safety.py:33,139-141` (`SECRET_NAMES`) | `src/skm/modules/artifacts/domain/content_safety.py` (`CS-SECRET-NAME`, default of `artifacts.safety.secret_name_globs`) (P06.01.b) | `PORT-AS-IS` | Retains secret filename patterns (`.env*`, `*.pem`, `*.key`, `id_rsa*`, `*credentials*`, `*secret*`, `.netrc`, `.npmrc`, `.pypirc`) as pure domain rule `CS-SECRET-NAME`. |
| `packages/workspace/lib/workspace/safety.py:42-44,171-196` (`_not_a_secret`, `_secret_finding`) and `packages/aicore/lib/aicore/util/redact.py:15-18` | `src/skm/modules/artifacts/domain/content_safety.py` (`CS-SECRET-CONTENT`) (P06.01.b) | `PORT-REFACTOR` | Defines self-contained pure-domain secret token/key regexes and placeholder exemptions (no `skm.platform.*` import); reports `CS-SECRET-CONTENT` with rule code and line/offset metadata only (never echoes raw secret values in findings or errors). |
| `packages/workspace/lib/workspace/safety.py:157-168,306-316` (`_path_findings`: absolute and home paths) | `src/skm/modules/artifacts/domain/content_safety.py` (`CS-ABSOLUTE-PATH`, `CS-HOME-PATH`) (P06.01.b) | `PORT-AS-IS` | Blocks `CS-ABSOLUTE-PATH` for `portable_document` admission and warns on `CS-HOME-PATH`; regular file uploads and evidence record path findings as informational/warning without blocking raw logs. |
| `packages/workspace/lib/workspace/safety.py:272-317` (`_scan_version`: symlink, size/binary, executable) | `src/skm/adapters/blobs/local/materializer.py` (`LocalUploadSourceReader`), `src/skm/modules/artifacts/domain/{upload_rules,content_safety}.py` (P06.01.b, P06.05) | `PORT-REFACTOR` / `DROP` (exec bit) | `CS-SYMLINK` is enforced in the host upload reader (`O_NOFOLLOW` / `lstat`) before bytes enter staging (`CONTENT_UNSAFE`); size is enforced via `artifacts.upload.max_bytes` (`CS-OVERSIZE` / `FILE_TOO_LARGE`); `CS-BINARY`, `CS-MEDIA-MISMATCH`, and `CS-EXECUTABLE` (shebang / PE / ELF / Mach-O magic) run in pure domain code; legacy filesystem executable-bit check on stored blobs is dropped because blobs are stored mode `0444`. |
| `packages/workspace/lib/workspace/safety.py:26,66-82` (`publish-report v1`, verdict) | `src/skm/modules/artifacts/domain/content_safety.py` (`SafetyReport`, `Admission`, `Admit`, `Reject`, `decide_admission`) (P06.01.b) | `REWRITE-KEEP-IDEA` | Replaces single workspace publish report with typed `SafetyReport` (`findings`, `acknowledged_rules`, `truncated`) and context-specific admission (`upload`, `evidence`, `portable_document`); acknowledging secret rules requires explicit `--ack` and `classification >= confidential`. |
| `packages/workspace/lib/workspace/safety.py:30-31,144-154` (`PS-TOP-LEVEL`, `PS-PROJECT-LEVEL`) | — | `DROP` | Legacy workspace git-layout rules do not apply to content-addressed artifact storage. |
| `packages/aicore/lib/aicore/state/*` (local state / `SKM_HOME` isolation) and `packages/orch/lib/orch/conductor/*` (attempt-bound evidence, symlink hardening `0f826a9`) | `src/skm/adapters/blobs/local/{store,materializer}.py`, `src/skm/modules/artifacts/host/{upload_file,materialize_files}.py` (P06.02, P06.05) | `REWRITE-KEEP-IDEA` | Content-addressed object store `<blobs_root>/<ws_id>/objects/<aa>/<sha256>` (`0444`), create-only `LocalMaterialWriter` (`O_NOFOLLOW`, `0444` files, `0555` dirs, `.ready.json`, Windows reserved-name sanitization `CON.txt` -> `_CON.txt`), and refusal to materialize inside a bound repository or git checkout. |
| New in v2 (two-phase `BlobCoordination`, `skm_planning.revision_file_bindings`, version-scoped worker grants, janitor & orphan prune G22) | `src/skm/modules/artifacts/application/{upload,commands,queries}/*`, `src/skm/adapters/postgres/migrations/sql/{0010_artifacts_files_blobs,0011_planning_file_bindings}.sql` (P06.03–P06.04) | Green-field v2 contract | Streamed `upload_blob` outside DB transactions -> `consume_staged_blob` -> `register_file_version`; FK-backed `revision_file_bindings` (`pinned` / `latest_at_publish`); version-scoped `file_version_access_grants` (`ARTIFACT-01`, stream-open-across-revoke `ACCESS-02`); and G22 no-physical-GC guarantee where `BlobStore.delete_unreferenced` is called only by `ExpireStagedBlobs` and `PruneOrphanObjects` (`report_digest` CAS + 24h min-age + DB reference recheck). |

## P11 — HTTP API and MCP validation (P11.Z)

P11 implements new v2 surfaces with no direct donor component. The HTTP API,
[OpenAPI 3.1 document](../src/skm/entrypoints/api/openapi.json) and generated
[API reference](reference/api.md) share route declarations. Workspace SSE
supports authenticated cursor replay. Live attempt events are buffered in a
single API process.

`HttpSkmClient` connects the CLI and remote worker to the control plane over
HTTP. Project-scoped stdio MCP exposes bounded plan reads and authoring, task
context, questions and notes. `skm serve` starts the API and background
services, while `skm local` supervises the local stack. Bootstrap profiles
carry per-instance backend, state and credentials.

The integration gate passed 213 HTTP API tests, 39 MCP tests, 24 HTTP security
boundary tests and 16 HTTP execution, worker and local lifecycle tests. The
generated API reference and OpenAPI freshness checks found zero drift.
All eight standalone `skm-hook` tests passed, with cold-start p95 at or below
150 ms for each target. Both ENCH4 PostgreSQL process tests passed. The worker
uses host-bound Codex capability evidence for routing. The barrier scenario
verified that publication preserves the active run's inputs and that the new
run receives the published text, checks, route and material pin. After check
evaluation, the new run has fresh `manual_pending` rows for both `V1` and `V2`
on the published revision. The reuse and acceptance fields are unset.
Full xdist `make check` passed 17,387 tests and 396 architecture tests with zero
failures.

The `P11.Z-rev2` remediation binds verified Codex routes to the rendered
launch template and the executable bytes. The launcher snapshots the CLI
and a fixed shebang interpreter, plus the Landlock wrapper and its
interpreter when selected. The security regressions exercise binary,
interpreter, wrapper, sandbox, MCP and session drift. The follow-up keeps
matching evidence for capabilities a partially degraded route relies on
and snapshots `config.toml` in a private launch home. The generated API
reference lists the OpenAPI primary permission before its alternatives.
[Verified launch binding regression](../tests/security/test_verified_launch_binding.py)

The targeted runtime and security suite and both PostgreSQL ENCH4 tests
passed in `P11.Z-revfix`. The full PostgreSQL gate is pending. Completed
`make test-pg` attempts encountered projected-hook timing failures, a shutdown
ownership-marker read failure, and a storage-budget lock timeout during
service-restart recovery. The recovery test passed in isolation.

For the `P11.Z-rev2` follow-up, all 32 targeted security and stage-role
tests passed with PostgreSQL enabled. The active-run ENCH4 case passed
on rerun after an initial runtime-barrier timeout. API reference
regeneration, generator drift check, schema validation and source index
generation passed. Pyright reported zero errors and the touched-files
preflight passed all 396 architecture tests. The full PostgreSQL gate
was outside this run.

P13 owns remaining optional routes and MCP memory, P14 owns legacy import
routes, and P15 owns storage verification, repair and backup routes. The
[phase status](status.md#p11--http-api-and-mcp-validation-p11z) records
executor validation and the independent review status.

## P13 — Optional modules and core independence (P13.Z)

P13.Z adds phase-gate tests for the v2 integration of knowledge, learning and
exports. This leaf has no direct donor component. The tests reuse the
PostgreSQL M3 fixtures and fake runtime, the production bus and outbox relay,
and the local bound vault writer. See the [P13 status](status.md#p13--optional-modules-and-core-independence-p13z)
for executor validation and independent review status.

## P13.01.c — Memory and lessons surfaces

The P13.01.c leaf card identifies `packages/maind/lib/maind/mcp.py` and its MCP parity tests as provenance
for scoped calls and result receipts. Current surfaces are
[`entrypoints/mcp/`](../src/skm/entrypoints/mcp/) and
[`modules/knowledge/`](../src/skm/modules/knowledge/). The tools bind memory to the current MCP
project. CLI and HTTP support explicit shared recall. Handoff replacement checks
the predecessor ID and lesson deprecation checks the row version.

The API ledger assigns `knowledge.list_memory` to P13.01.c and
`knowledge.graph_stats` to P13.02.b.

## Template for each future port

| Field | Record |
|---|---|
| Leaf / destination | Exact item ID and owned product paths |
| Source path / revision | Donor path, commit and line ranges; captured digest where applicable |
| Recommendation | PORT-AS-IS / PORT-REFACTOR / REWRITE-KEEP-IDEA / DROP / MIGRATE AS DATA |
| Preserved guarantees | Invariants, decision ordering and source line citations |
| Error/refusal codes | Each code and its triggering condition |
| Edge cases | Source test names and cases retained |
| Intentional changes | Reason and ADR/owner-contract reference |
| Regression proof | New test paths, actual command and result |
| Fixture provenance | Source path/commit sidecar for legacy-derived golden data |
| Validation / review | Separate executor evidence and reviewer/by/outcome |

Unknown or stale donor goldens are scenario inputs, not automatically correct
expected output. Capture partial progress and limitations explicitly. Owner
instructions govern commits; the template does not require a commit per leaf.
