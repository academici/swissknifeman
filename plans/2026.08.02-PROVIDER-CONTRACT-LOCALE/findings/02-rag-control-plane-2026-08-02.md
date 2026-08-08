# RAG — Provider-neutral control plane

**Date:** 2026-08-02

**Query:** multi-provider developer-tool integration with one source of truth,
generated adapters, idempotent reconciliation, drift detection and legacy migration.

## Extract

- Separate canonical desired state (`spec`) from provider-observed state (`status`).
- Every adapter follows observe → diff → apply owned changes → read-after-write;
  repeated reconcile without semantic change has an empty plan.
- Persist desired canonical state, last applied projection and fresh observed state to
  distinguish semantic change, provider drift and local overrides.
- Version schemas and migrate legacy forms explicitly; ambiguous state stays unresolved.

## Sources

- https://developer.hashicorp.com/terraform/plugin/sdkv2/best-practices/detecting-drift
- https://developer.hashicorp.com/terraform/plugin/framework/resources/state-upgrade

**Confidence:** medium-high. The control-plane mapping is a design inference to validate
with repository prototypes and tests.

