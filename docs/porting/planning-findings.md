# Planning findings: legacy codes to canonical codes

Port record of the validation rules of `planning` (P05.03.a). Source of truth for the canonical codes, their
severities and legacy ancestry is `src/skm/schemas/planning/data/finding-codes.json`; the rule order and each rule are
in `planning` section 5.7, the legacy table in section 16.1. The donor `check.py` was only read.

Every legacy code has exactly one verdict:

- **retain**: the legacy code is kept under the same name.
- **map**: the legacy code is replaced by one or more canonical codes (`Canonical`).
- **drop**: the condition no longer exists in v2 (the schema forbids it, the state is execution state, or it needs a
  checkout) and the reason is given.
- **overlay**: the condition is a repository- or language-specific heuristic; it is not a core finding and stays a
  candidate for a trusted `planning_rule` plugin (codes `x_<publisher>_<name>`, severity at most warning).

`tests/unit/planning/domain/test_validation.py` parses this table and compares it with the catalog: a legacy code
missing here, a canonical code that is not in the catalog, or a verdict that contradicts the catalog fails the test.

## Legacy to canonical

| Legacy | Verdict | Canonical | Note |
|---|---|---|---|
| `artifact_duplicate` | retain | `artifact_duplicate` |  |
| `artifact_path` | map | `artifact_path_mismatch` |  |
| `authority_identity` | drop | — | schema oneOf: exactly one of gate or label |
| `authority_scope` | drop | — | schema: scope required for gates |
| `backlink_mismatch` | map | `decision_superseded_orphan` | supersedes is the only link; the finding names a missing, repeated or wrongly marked replacement |
| `batch_coverage` | map | `batch_multiple`, `batch_unassigned` | one legacy code splits by what is wrong: an item in two batches is an error, an item in none an info |
| `batch_foreign` | retain | `batch_foreign` |  |
| `batch_id` | map | `duplicate_key` |  |
| `brief_duplicate` | retain | `brief_duplicate` |  |
| `check_cadence` | retain | `check_cadence` | the heavy markers are the setting `planning.validation.heavy_check_markers` (empty by default), not a repository constant |
| `check_overlap` | map | `check_duplicate_command` | only rule (d), an item check equal to a check of its phase, is core (equal `argv`, or `script` after `strip`); rules (a)-(c) name scripts of one repository (`validate.sh`, `test.sh -p`, `--tier all`) and move to an overlay plugin |
| `context_default` | retain | `context_default` |  |
| `context_heavy` | retain | `context_heavy` | limit is `planning.validation.heavy_text_bytes` |
| `context_legacy` | drop | — | legacy projection sections do not exist in v2 |
| `context_unbound` | retain | `context_unbound` |  |
| `cycle` | map | `dependency_cycle` | found on the compiled graph (planning 5.4), so a cycle through a phase gate is found too |
| `decision_fields` | retain | `decision_fields` |  |
| `DECISION_SELF_SUPERSEDE` | map | `self_reference` | a decision in its own `supersedes` |
| `DECISION_SUPERSEDED` | map | `decision_superseded_orphan` |  |
| `dependency_deadlock` | map | `dependency_cycle` | the same graph check: a wait that can never be satisfied is a cycle of the compiled graph |
| `DESIGN_INCOMPLETE` | map | `phase_skeleton` | a skeleton phase is info at publication; an empty detailed phase is `incomplete` |
| `execution_commit_instruction` | overlay | — | per-step commit wording is a regex over English and Russian author text; it encodes one repository's rule that the coordinator commits |
| `execution_prompt_heavy` | retain | `execution_prompt_heavy` | limit is `planning.validation.heavy_text_bytes`; the legacy whole-file read size is execution context assembly, not a planning check |
| `execution_rules_conflict` | overlay | — | a regex over English and Russian rule text ("only targeted tests", "только целевые тесты") tied to one repository's test policy |
| `execution_write_set_empty` | map | `write_scope_empty` | now an item of a writing work kind with neither change hints nor a unit write scope |
| `human_view` | drop | — | there are no plan Markdown views that could be read as inputs |
| `ID_DUPLICATE` | map | `duplicate_id` |  |
| `id_mismatch` | map | `key_prefix_mismatch` | item key must start with its phase, unit key with an existing item key |
| `incomplete` | retain | `incomplete` |  |
| `json` | drop | — | no plan files; malformed input is SCHEMA_INVALID of the command DTO |
| `LINK_INVALID` | map | `ref_unknown` |  |
| `log_target` | drop | — | there is no plan log; events live in skm_core.domain_events |
| `modify_missing` | drop | — | existence needs a checkout: execution readiness rule change_hint_missing |
| `OPTION_UNKNOWN` | map | `decision_fields` |  |
| `orchestration` | drop | — | schema bounds max_parallel_units |
| `path` | drop | — | schema patterns forbid '..', absolute, '~' and drive paths |
| `phase_closure_stale` | drop | — | phase closure is execution state |
| `phase_items` | map | `key_prefix_mismatch` | the phase of an item is a field; the key prefix must agree with it |
| `phase_list` | drop | — | no denormalized lists: the phases array is the list |
| `PHASE_NOT_DETAILED` | map | `phase_skeleton` | info at publication; execution readiness refuses the tasks of a skeleton phase |
| `phase_unclosed` | drop | — | phase closure is execution state |
| `plan_state` | drop | — | pause is run state (execution), not specification |
| `RATIONALE_REQUIRED` | map | `decision_fields` |  |
| `read_missing` | drop | — | existence of repository paths needs a checkout: execution readiness rule required_read_missing |
| `readiness_stale` | drop | — | readiness is an execution report (execution.validate_for_execution) |
| `reads_ref` | drop | — | qualified refs are rejected by the schema pattern; material sections are resolved at context assembly |
| `ref_kind` | drop | — | field patterns in the schema allow only the right kinds |
| `REF_UNKNOWN` | map | `ref_unknown` |  |
| `ref_unknown` | retain | `ref_unknown` |  |
| `result_status` | drop | — | lifecycle status is execution state |
| `review_strategy` | map | `review_reviewer_unset` | a required review with neither reviewer nor `max_rounds`; `none`/`self` need a reason by schema |
| `route` | drop | — | schema dependentRequired model -> runtime; unknown names: route_unknown_* |
| `ROUTE_MODEL_UNKNOWN` | map | `route_unknown_runtime`, `route_unknown_model` | split into the unknown runtime and the unknown model of a known runtime; both warnings |
| `ROUTING_UNAVAILABLE` | map | `route_unknown_model` |  |
| `schema` | drop | — | the document must be schema-valid to be saved at all (SCHEMA_INVALID) |
| `scope_ambiguous` | retain | `scope_ambiguous` |  |
| `sections` | map | `duplicate_key` |  |
| `source_unbound` | drop | — | planning never checks repository paths |
| `unit_command` | map | `unit_command_missing` |  |
| `UNIT_DEPENDENCY` | map | `ref_unknown` |  |
| `unit_files_uncovered` | map | `write_scope_uncovered` | coverage uses the dialect of the write-scope fence (`globs.covers`), not `fnmatchcase` on whole paths |
| `unit_overlap` | map | `write_scope_overlap` | uses the may-overlap rule of `globs.globs_overlap` instead of segment-wise `fnmatchcase` in either direction |
| `unit_parent` | drop | — | self_reference / ref_unknown and the unit_specs parent FK |
| `UNIT_SELF` | map | `self_reference` | a unit in its own `depends_on` or as its own `parent` |
| `units_list` | map | `key_prefix_mismatch` | units carry their item in the key prefix; there is no list to disagree with |
| `validation_carrier` | map | `unit_command_missing` |  |
| `validation_id_clash` | drop | — | check keys are scoped by owner (P1:V1 vs P1.2:V1); results are stored per check id |
| `write_set_no_tests` | map | `write_scope_no_tests` | suffixes come from `planning.validation.code_suffixes`; legacy had four fixed ones |

## Canonical codes with no legacy ancestor

New in v2: they come from planning rules that legacy never had (typed references, mounts, batches against the graph,
materials, routing catalogs).

| Canonical | Severity | Rule |
|---|---|---|
| `entity_kind_changed` | error | rules_structure |
| `plan_relation_unresolved` | warning | rules_references |
| `batch_order_conflict` | error | rules_dependencies |
| `mount_unknown` | error | rules_scope |
| `write_scope_overlap_cross_item` | info | rules_scope |
| `forbidden_path_conflict` | error | rules_scope |
| `research_question_missing` | warning | rules_readiness |
| `criterion_unlinked` | error | rules_acceptance |
| `criterion_check_mismatch` | error | rules_acceptance |
| `requirement_unimplemented` | warning | rules_acceptance |
| `criterion_missing` | info | rules_acceptance |
| `check_manual_rerun_after_integration` | error | rules_checks |
| `material_unavailable` | error | rules_context |
| `material_stale` | warning | rules_context |
| `skill_unknown` | warning | rules_routing |

## Choices of the port

- **Failure of a rule is not a finding.** A rule that raises is recorded as a `RuleFailure`; it blocks publication
  when it is a built-in rule, and when it is a plugin rule only by `planning.validation.external_failure`. The
  legacy `check.py` caught nothing and "never raises" was a convention; v2 makes it the pipeline's job.
- **Graph rules wait for a sound placement.** `dependency_cycle`, `batch_order_conflict` and both `write_scope_overlap`
  codes stay silent while an item or unit key contradicts its phase or item (`key_prefix_mismatch`): a cycle found in a
  misplaced graph is an artefact of the misplacement.
- **A cycle closed only by a batch barrier is `batch_order_conflict`.** `dependency_cycle` is looked for on the graph
  without batch ordering; the batch rule then names the earlier batch that waits for a later one.
- **Only declared footprints overlap.** A task without a declared write scope conflicts with everything at scheduling
  time (planning 5.5) but is not reported as an overlap.
- **`write_scope_no_tests`** looks at the change hints of an item (`create`/`modify` paths with a code suffix); the unit
  write scopes stand in only when the item has no hints. A test path anywhere in the item (hints or unit scopes) ends the
  finding.
- **Severity** is the catalog's; `planning.validation.require_acceptance_links = false` lowers `criterion_unlinked` to a
  warning. `warn_unknown_models` and `warn_unknown_skills` switch the catalogs off at the caller (`None`), not in the rule.
