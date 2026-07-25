# P6.4 analytics contribution review

Status: accepted under D79/D90 before the first shared-core edit.

## Rule of Three

The requested primitive has three current independent consumers: `analyst` normalizes and
stores events, `maind` reads neutral pending-lesson/run summaries, and `harness` supplies
generated capture bundles. None can own the neutral identity/provenance envelope without
introducing a dependency from another package back to that consumer.

## Alternatives

1. Keep the lookup and envelope in `analyst` — rejected: `maind` and generated harness
   consumers would either import analyst storage policy or duplicate identity validation.
2. Put parsing, storage and migration into `core` — rejected: this would make a shared
   package own provider-specific raw schemas and policy, contrary to D90.
3. Add a minimal immutable lookup/envelope validator to `core.runs` — accepted: it exposes
   only the frozen semantic identity/provenance boundary; analyst retains readers, redaction,
   persistence, retention and migration.

## Dependency direction and public consequence

`core` imports no consumer. `analyst`, `maind`, and harness-generated bundles depend only on
the additive primitive. The API is new and backward-compatible (minor/additive public surface);
no existing function, format, or SemVer promise changes. Python remains stdlib-only.

## Approval

D79 delegated authority and D90 frozen `provider-analytics-contract v1.0.0` approve
Alternative 3 for P6.4. Any change to the contract's identity, provenance, privacy, storage,
reader isolation, or migration semantics requires a new versioned decision.
