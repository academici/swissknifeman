---
name: api-design
bucket: architect
version: 0.2.0
description: "Design or evolve an API contract: compatibility, auth, errors, pagination, and retry semantics."
when_to_use: "Use when creating or changing an API contract."
risk: draft
persona: architect
tags: [api, architecture, rest, contracts]
requires: []
produces_for: []
outputs: ["docs/03_Dev/API_Endpoints.md"]
sha256: ""
adapters: [claude, cursor, fable]
---

# API Design

Use for a new or changing API contract. Read the existing schema, clients, conventions, and
adopted compatibility policy first. Do not redesign the API style, version scheme, or document
layout during an unrelated endpoint repair.

## Contract decisions

- Identify callers, authentication, resource authorization, required/optional input, output,
  validation, and error behavior. Distinguish absence from denial according to the security
  contract; never rely on a hidden UI control for authorization.
- Choose REST, GraphQL, RPC, streaming, or webhooks from actual interaction needs. Preserve an
  established style unless changing it is part of the task.
- For REST, consistent resource names, methods, status codes, and error shapes aid callers.
  Plural nouns, shallow nesting, snake_case JSON, and `/api/v1` are conventions to adopt, not
  universal acceptance gates. Action endpoints are valid when they express a real operation.
- Define compatibility and rollout for consumers. Versioning may use URLs, headers, schema
  evolution, or an existing deployment contract; a version prefix is not mandatory on day one.
- Paginate potentially unbounded collections. Choose cursor/offset semantics from ordering and
  consistency needs; total counts are optional when expensive or not meaningful.
- Define retry and idempotency semantics for effects that may be repeated. Payments and job
  submission need explicit duplicate handling; an `Idempotency-Key` header is one mechanism,
  not a mandatory header on every POST. Specify key scope, retention, payload mismatch,
  concurrency, and atomicity when using it.

## Security and failure behavior

Keep credentials out of URLs and logs. GET must not cause a caller-requested mutation. Use
established auth mechanisms suitable for actual clients and sessions; JWT is not a universal
default. Check cross-user/tenant object access, input limits, abuse/rate controls, and bounded
responses. For callbacks/webhooks, consider signature validation, replay protection, delivery
ordering, and duplicate effects when those paths exist.

## Deliver

Update the existing OpenAPI/schema/docs with representative requests, success/errors, auth,
pagination/retry behavior, and compatibility notes relevant to the change. Test existing
callers and failure paths at the changed boundary; add no speculative endpoints or webhooks.

[REST conventions](snippets/rest-conventions.md) and
[OpenAPI stub](snippets/openapi-stub.yml) are starting examples, not a new project policy.
Use `architect/security-design` for a changed trust boundary and
`architect/package-contribution-protocol` when the contract belongs to a dependency.
