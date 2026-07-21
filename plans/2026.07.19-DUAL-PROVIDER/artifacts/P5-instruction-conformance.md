# P5 instruction conformance

**Contract:** `provider-instruction-contract` v1.0.0 (D86)
**Scope:** temporary roots only; no live root/package target was rendered or adopted.

| Check | Result |
|:--|:--|
| Exact scopes / target projections | `root, skiller, harness, maind, analyst, task` / 12 |
| Semantic records / parity | Exact ordered inventory is 49 common + 18 provider-extension = 67 IDs. Missing, extra, duplicate, reordered and provider-mismatched IDs fail before P2; positive common parity and allowed own-provider deltas pass. |
| Canon and compatibility | Every record binds only its common/own-extension fragment with a full content hash. The independent record-level fixture remains sourced from the approved P5.6 review and is validated before P2; current `CLAUDE.md`/`AGENTS.md` are compatibility inputs/managed targets only. |
| Structured obligations | Normalized modality/subject/action/object/boundary records reject duplicate meaning and all frozen conflict classes: opposite modality, broader permission, narrower required coverage, common-owner replacement/shadow and equivalent obligation under another ID. |
| Provider independence | Claude and Codex read common plus only their own extension fragment; no output translation |
| Public seam / diagnostics | Frozen request/result fields are exposed by `plan_instructions`, `check_instructions`, `apply_instructions`, and `repair_instructions`; diagnostics always serialize all 12 stable fields in deterministic order and unknown codes/observations fail closed. |
| P2 provenance | Actual serialized P2 v1.1.0 lock proves all 12 records, exact full contract/catalog/common/own-extension hashes, adapter/provider/target/artifact identity, source/render hashes, two ordered block IDs and the `instructions.project` `native|adapted` requirement. Every record's generic immutable `semantic_metadata` contains D86 `artifact_kind`, instruction/catalog versions, scope/provider, marker/block IDs, semantic sections, capabilities and registry. Exact v1.0.0 records still round-trip without the field. |
| Temp lifecycle | `plan`/`check` are no-write; explicit missing create and stale-source update are bounded; managed drift requires explicit repair hash plus recoverable pre-image; corrupt/newer locks, unmanaged targets and malformed boundaries refuse; outside bytes and two-run results are preserved/deterministic. |
| Compatibility | The independent fixture applies all 12 temporary targets, verifies every one of 67 record assertions in installed consumers, and rejects Claude slash/runtime tokens from Codex (`/task:`, `PreToolUse`, `enabledPlugins`, `.claude/settings`, `.claude/skills`, `outputStyle`, `plansDirectory`). |
| Focused proof | 25 core artifact/lock tests passed; 34 instruction/compatibility tests passed twice in identical order; changed Python compiled; target plan-lint, `git diff --check` and protected P6+/FOREMAN/live-carrier delta checks passed. Full package/registry validation and independent audit were deliberately not run under D80. |

The generated operator reference is `packages/harness/docs/reference/provider-instructions.md`.
P6/P7 consume the frozen `harness.instructions` request/result API without changing D86
markers, observations, hashes or ownership rules.
