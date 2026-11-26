---
name: skill-name
bucket: founder|pm|architect|oss-dev|quality|operator|devops|php|roles|imported
version: 0.1.0
description: "Use when a concise, reusable capability needs a clear trigger and boundary."
risk: read|draft|write|external
invocation_intent: automatic|explicit
capabilities: []
inputs: []
outputs: []
resources: []
provenance: local|upstream
sha256: ""
---

# Skill purpose

State one concrete capability and the outcome it produces.

## Trigger checks

- Positive: use this skill when the stated capability is needed.
- Negative: do not use this skill for adjacent work outside the capability.
- Boundary: invoke explicitly when the declared risk requires explicit intent.

## Inputs and outputs

Name the required inputs and the observable outputs.

## Invariants and risk

Keep only non-obvious safety, product, or domain constraints. Use `explicit` invocation intent
for `write` and `external` risk; `read` and `draft` may be automatic or explicit.

## Workflow

Give the shortest imperative sequence that materially changes the outcome.

## Resources

Link optional detail one level deep: [reference](references/example.md) or
[snippet](snippets/example.md). Load a resource only when it is needed.

## Optional failure modes

Add a failure mode only with a linked observed failure or ablation record; omit generic advice.

## Provenance

Record whether the canonical source is local or upstream and how it is refreshed.
