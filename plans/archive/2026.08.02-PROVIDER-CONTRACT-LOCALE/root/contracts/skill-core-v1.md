# Skill Core contract

**Version:** v1.0.0-draft
**Status:** draft
**Owner:** skiller canonical registry

## Purpose

Skill Core is the minimum provider-neutral statement of one reusable job. It is immutable input
to provider adapters. It contains observable meaning only; discovery metadata, invocation syntax,
provider target paths, model or effort controls, tool spellings, packaging and measurement belong
to additive provider adapters.

Normative words `MUST`, `MUST NOT`, `SHOULD`, and `MAY` are literal.

## Exact record

A Skill Core record has exactly these required fields, in canonical JSON terms:

| Field | Contract |
|:--|:--|
| `contract_version` | Supported `1.0.x` contract version. |
| `skill_id` | Frozen publication identity `<bucket>/<frontmatter-name>`. |
| `job` | One concrete observable job, not a provider invocation. |
| `trigger` | Exact `positive`, `negative`, and `explicit_only` boundary. |
| `inputs` | Non-empty ordered semantic input IDs; no provider paths. |
| `outputs` | Non-empty ordered semantic output IDs; no provider paths. |
| `invariants` | Non-empty ordered non-obvious safety/product/domain constraints. |
| `capabilities` | Ordered stable capability requirements with accepted `native`/`adapted` levels. |
| `workflow` | Shortest non-empty ordered imperative sequence that changes the outcome. |
| `resources` | Ordered one-level references/scripts/assets loaded only on demand. |
| `provenance` | Exact source identity, digest, and refresh policy. |

`failure_modes` is the only optional field. When present it is a non-empty ordered list of
evidence-backed failure records. Empty boilerplate is invalid.

The positive fixture envelope has exactly `contract_version` and `cases`, uses supported `1.0.x`,
and has globally unique `skill_id` values before any keyed projection is built. Input and output
IDs use `^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$`; provider/rendered/target/path segments and
provider target path syntax are forbidden.
Skill IDs use exactly `^[a-z][a-z0-9-]*/[a-z][a-z0-9-]*$`. Capability, Native Extension,
resource and provenance semantic identities retain the separate dotted grammar. An adapter MUST
reuse the canonical `<bucket>/<frontmatter-name>` unchanged; translation to a dotted/provider path
identity is semantic replacement. Colon and underscore are never accepted substitutes.
All human strings and list items are strip-nonempty; trigger examples, invariants, workflow steps,
and other contract-declared unique lists reject duplicates.

`trigger.positive` and `trigger.negative` are both non-empty ordered intent examples. A near-miss
must be distinguishable without provider metadata. `trigger.explicit_only` is a boolean semantic
risk boundary; it is not an invocation flag.

Capability requirements have exactly `id`, `accepted_levels`, and `required`. Support levels come
only from the frozen capability manifest. `unsupported` is never an accepted level. Optional
requirements remain visible provider-qualified limitations when unavailable.
Accepted levels are the exact non-empty canonical subsequence of `adapted`, then `native`.

When present, each `failure_modes` item has exactly `code`, `condition`, and `outcome`; codes are
unique machine codes and both human fields are strip-nonempty.

Resources have exactly `id`, `kind`, and `ref`; `kind` is `reference`, `script`, or `asset`.
References are source identities or project-relative canonical paths, never rendered provider
targets. Progressive disclosure is one level deep: a resource cannot silently introduce another
mandatory skill body.

## Provider neutrality

The complete forbidden provider-control field set is:

`provider`, `provider_id`, `providers`, `model`, `model_class`, `effort`, `invocation`,
`frontmatter`, `target_path`, `target_roots`, `discovery`, `renderer`, `measurement`, `replay`,
`claude`, `claude-code`, and `codex`.

Those keys are forbidden at every depth. Provider target path fragments such as `.claude/`,
`.codex/`, `.agents/`, `CLAUDE.md`, and `AGENTS.md` are forbidden in semantic strings. A renderer
MUST reject leakage; it MUST NOT strip the field and continue.

Generic model behavior, broad style advice, repeated verification reminders, exhaustive examples,
provider-native optimizations, and compatibility ritual are not Skill Core meaning unless an
official requirement, repository invariant, observed failure, or ablation result names the exact
retained constraint.

## Immutability and adapters

An adapter receives a validated Skill Core by value and may only add its own discovery,
invocation, layout, capability, measurement, replay, and diagnostic projection. It MUST NOT delete,
weaken, duplicate, shadow, reorder, or replace the Skill Core job, trigger boundary, inputs,
outputs, invariants, capabilities, workflow, resources, or provenance.

A rendered skill, provider manifest, provider target, lock, observation, status row, diagnostic,
or another adapter's projection is never a Skill Core source.

## Validation and versioning

Validation fails closed for unknown fields, unknown major/minor, duplicate IDs, non-canonical
ordering, missing trigger boundaries, empty required collections, forbidden provider fields or
paths, invalid resource depth, and adapter replacement markers.

- **major:** changes exact fields, identity/job/trigger meaning, provider-neutrality, or immutable
  adapter boundary;
- **minor:** adds an optional field old readers can safely reject;
- **patch:** editorial clarification or fixtures with identical outcomes.

`skill-core-positive.json` contains accepted records. Every case in `skill-core-negative.json`
changes one invariant only and declares its exact refusal code. Synthetic fixtures prove schema
and boundaries; live provider replay and ablation remain the outcome evidence.
