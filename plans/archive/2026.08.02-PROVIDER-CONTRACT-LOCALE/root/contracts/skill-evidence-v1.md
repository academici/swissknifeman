# Skill evidence contract

**Version:** v1.0.0
**Status:** frozen
**Approval Owner:** repository owner
**Approval:** D77 · 2026-08-14

## Purpose

This contract separates deterministic skill structure from behavioral evidence. It applies one
provider-neutral Skill Core and additive provider adapters. Provider tuning never enters shared
content, and deterministic fixtures never certify model efficacy.

## Minimum evidence record

Every migrated capability records:

- stable capability ID and minimum Skill Core instructions;
- official current provider expectations with source URL and checked date;
- at least three representative real workflows: positive, negative, and boundary;
- for each workflow, `no-skill`, `minimum-core`, and `provider-tuned` outcomes;
- provider, model, date, tool identity, privacy-minimized outcome, and retained evidence reference;
- every non-core instruction with either an observed failure mode or an ablation result;
- independent review and the exact source/projection/rollback identities from the locale authoring
  contract.

The record may be prepared in P4, but release acceptance is produced only by P7 against current
providers and real project workflows. Missing live evidence leaves the capability unadmitted; it
does not authorize synthetic replacement evidence.

## Shared and provider-specific content

The Skill Core contains only provider-neutral meaning: trigger, required capability, invariant,
resource, and expected outcome. Discovery syntax, invocation policy, prompt placement,
distribution, provider-native UI, measurement API, and tuning live in the owning provider adapter.
A third provider consumes the same Skill Core without changing it.

Every instruction beyond the Skill Core MUST have an ablation result or a concrete observed
failure mode. Repetition, generic tutorials, universal Gotchas, and speculative advice are
rejected. Provider tuning in shared content is refused even when it appears harmless.

## Deterministic evidence boundary

Fixtures and repository validators may check schemas, triggers, links, generation, literal
preservation, known regressions, baseline presence, provider/model/date attribution, and ablation
records. They MUST label themselves `structure-only` and MUST NOT claim behavioral efficacy.

## Diagnostics

| Code | Meaning |
|:--|:--|
| `SKILL_EVIDENCE_SYNTHETIC_ONLY` | Deterministic evidence is presented as efficacy proof. |
| `SKILL_EVIDENCE_BASELINE_MISSING` | A workflow lacks its no-skill baseline. |
| `SKILL_EVIDENCE_IDENTITY_MISSING` | Provider, model, date, tool, or evidence identity is absent. |
| `SKILL_EVIDENCE_ABLATION_MISSING` | A non-core instruction lacks ablation or observed failure. |
| `SKILL_EVIDENCE_PROVIDER_TUNING_SHARED` | Provider-specific tuning appears in shared Skill Core. |
| `SKILL_EVIDENCE_SCHEMA_INVALID` | Record shape or workflow coverage is invalid. |

## Versioning and freeze

A v1.0 reader accepts only `1.0.x`. D77 freezes:

- **S1:** minimum provider-neutral Skill Core with additive adapters;
- **S2:** three real workflows and explicit no-skill/minimum/provider-tuned variants;
- **S3:** provider/model/date/tool identities and privacy-minimized outcomes;
- **S4:** ablation or observed failure for every non-core instruction;
- **S5:** deterministic evidence is structure-only; real-project/provider acceptance belongs to P7.

