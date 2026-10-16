# ADR 0017: Boundary between aicore.provider and the orch engines; error taxonomy

## Status

Accepted

## Context

Provider facts, error classification and retry logic are mixed between modules.

## Decision

`aicore.provider` owns provider facts (capabilities, models, authorisation routes), a normalised error taxonomy
(`authentication`, `authorization`, `quota`, `rate_limit`, `invalid_request`, `model_unavailable`,
`content_policy`, `transport`, `provider_internal`, `timeout`, `unknown`, with `retryable`, `retry_after`, `scope`
and `safe_message`) and usage parsing. The `orch` engines own the process transport, run lifecycle, retries and
backoff by error class from run-policy, never by message text. Four things are kept apart: feature capability,
resource (current quota), policy (allowed) and health (dependency works). A capability record gets `source`
(`declared`, `probed`, `inferred`), probe freshness and remediation.

## Alternatives considered

- Classify errors inside each engine: rejected, each engine would diverge.

## Consequences

- One error registry for all consumers; retries stop depending on parsing text.
- The capability record of `exec/v1` grows by optional fields.

## Supersedes

None.
