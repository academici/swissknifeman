# Unified Agent Trace v1 (P3.1)

RAG:✅ 2026-07-24 OTel GenAI vocabulary shape (`findings/05-external-practices.md`;
plan-grounded: D11/D23; repo-grounded: `root/contracts/task-contract-v1.md`,
`root/contracts/execution-state-machine-v1.md`, `root/contracts/risk-review-loop-budget-v1.md`,
`packages/harness/configs/claude-code/hooks/run-report/_lib.py`,
`packages/task/lib/task/journal.py:39-46`).

## Scope

This contract seals **one stdlib-only record shape that links a requirement to its
contract identity, route, dispatch state, findings and public outcome**, so P3.2/P3.3
derive metrics from one instrument instead of re-parsing provider-specific logs per
consumer (`findings/02-telemetry-2026-07-20-24.md`: journal fields do not causally
connect session/run/route/turn/outcome today; raw data exists, completeness is
unknown).

It is a **layer on top of** three frozen contracts, never a copy of them: P0.2 owns the
compiled Task Contract and its `version.content_hash`; P2.1 owns the nine execution
states and fifteen events; P2.1's sibling owns finding identity and `finding_id`. Where
this contract references one of them, it cites `file:line` and stops.

It seals the schema and the normalization boundary only. It implements no metric
arithmetic (P3.2), no eval adapter (P3.3), no canary dispatch (P3.4) — those are named
consumers, not owners, of this contract.

## Machine carriers

| Artifact | Role |
|:--|:--|
| `packages/analyst/lib/analyst/trace.py` | the schema owner: builds, validates and dedups one `TraceRecord`; the sole place `schema_version` is interpreted |
| `packages/harness/lib/harness/provider_trace.py` | thin provider readers: map already-captured provider-specific structures (Claude run-report, Codex session) into the RAW payload keys `trace.py` consumes; no normalization logic lives here |
| `packages/task/lib/task/journal.py` | linkage only: an optional `--trace-ref` on `journal append` lets a journal entry point at a trace identity without duplicating its metrics |

## Frozen upstream

| Fact | Owner | Source |
|:--|:--|:--|
| `version.content_hash` recomputation rule, `supersedes` | P0.2 | `root/contracts/task-contract-v1.md:56-63` |
| The nine declared states, fifteen events, six decision outputs | P2.1 | `root/contracts/execution-state-machine-v1.md:68-126` |
| `finding_id` derivation (`seam`: file/rule_or_contract_locus/defect_class), `reopen_of` | P2.1 sibling | `root/contracts/risk-review-loop-budget-v1.md:91-107` |
| Journal `COMMANDS`, `RESULT_VALUES`, append-only single-write invariant | P1.1 | `packages/task/lib/task/journal.py:35-46,283-298` |
| SCHEMA=2 run-report shape (`tools`/`reads`/`retrieval`/`devloop`/`usage`/`protected_writes`) | harness hook | `packages/harness/configs/claude-code/hooks/run-report/_lib.py:1-25,527-543` |

**Reason codes are never re-minted.** This contract's own errors (`TRACE_*` below) are
distinct from every P0.2/P2.1 code by construction — they guard a different boundary
(record shape, not mutation/final permission) and never fire inside `pre_mutation`/
`pre_final`.

## Field set (closed)

A `TraceRecord` is a dict with exactly these top-level keys — `additionalProperties`
equivalent enforced in code, not merely documented (`TRACE_UNKNOWN_FIELD`).

| Field | Type | Nullable | Carries |
|:--|:--|:--|:--|
| `schema_version` | str | no | literal `"unified-agent-trace/v1"` |
| `trace_id` | str | no | sha256 hex, see § trace_id and dedup |
| `provenance` | object | no | `provider_id`, `raw_ref`, `sha256`, `reader_id`, `reader_version` — same shape as `core.runs.EventEnvelope.provenance`, a **distinct instance** (this contract does not import that envelope: different schema, different consumers) |
| `occurred_at` | str | no | UTC ISO-8601, must end `Z` |
| `plan_ref` | object\|null | yes | `plan_id`, `item_id`, `command` (one of `journal.COMMANDS`) — the journal reference |
| `contract_ref` | object\|null | yes | `contract_id`, `version_hash` — links to a P0.2 `version.content_hash` |
| `route` | object\|null | yes | `model_class`, `effort`, `model` — same vocabulary as `route_evidence.capture_actual` |
| `dispatch` | object\|null | yes | `state`, `event` — must be members of the P2.1 declared sets when present |
| `finding_refs` | array[str] | no (may be empty) | `finding_id` values per the P2.1 sibling contract |
| `public_outcome` | object\|null | yes | `scope` (`public`/`internal`), `check`, `evidence_ref` — same vocabulary as `task-contract-v1.md` `done.public_acceptance` |
| `quality` | object | no | `completeness` (float, expected-fields-present / expected-fields-total), `missing` (sorted field names), `degraded` (bool) |
| `reasons` | object | no | one entry per name in `quality.missing`; every null field is explained, never silently absent |
| `privacy` | object | no | `excluded` — the constant four-class list below, always present and never partial |

`quality.completeness`'s denominator is the six nullable fields above (`plan_ref`,
`contract_ref`, `route`, `dispatch`, `public_outcome`, plus `finding_refs` counted
non-empty vs empty) — **not** `provenance`/`occurred_at`, which are never optional and
whose absence is a build-time error (`TRACE_MISSING_IDENTITY`), not a quality signal.
This is what the P0.3 bank's F6 floor (`trace_completeness ≥ 0.99`) measures once P3.2/
P3.3 run a live bank pass; this item proves the instrument, not the number
(`artifacts/reliability-bank-v1/bank-manifest.json::floors[F6].note` — deferred until a
live paired run exists).

## Provenance and privacy (fail-closed)

`provenance.sha256` is checked against `source_bytes` exactly like
`core.runs.EventEnvelope` and `analyst.readers`: a caller-declared hash that does not
match its bytes is `TRACE_CORRUPT_RECORD`, never silently trusted.

`privacy.excluded` is a **constant**, not a measurement: `["raw_transcript",
"chain_of_thought", "tool_payload", "secret"]`. `build_trace_record` refuses (rather
than redacts) any raw input carrying a key that plausibly names one of these classes
(`prompt`, `reasoning`, `chain_of_thought`, `tool_input`, `tool_result`, `secret`,
`token`, `api_key`) — `TRACE_PRIVACY_VIOLATION`, mirroring `ANALYTICS_REDACTION_FAILED`
rather than inventing a second redaction vocabulary. This is Scope Excluded's
"no chain-of-thought, no inferred zeros" as an executable gate, not prose.

## `trace_id` and resume/fork dedup

`trace_id = sha256("provider_id=<id>|project_id=<pid>|identity=<stable>|turn=<tid>")`
where `stable` is the provider's session identity and `tid` is the turn/call boundary
the provider itself assigns. Recomputing the same natural key always yields the same
id — this is the direct fix for the corrected-dedup method already used once
(`artifacts/source-evidence/precomputed/baseline.json::method`: "resumed/forked JSONL
events are deduplicated by stable turn_id/call_id before aggregation"), generalized so
every consumer gets it from the schema instead of re-deriving it per report.

`dedup_records(records)` groups by `trace_id` and keeps the entry with the higher
`quality.completeness` (ties keep the first-seen) — a resumed session's later, more
complete record supersedes its earlier partial one instead of both existing side by
side. This is `SCOPE INCLUDED`'s "resume/fork dedup"; it is not a merge (no field-level
union) — merging partial records would hide which provenance produced which field.

## Provider reader boundary

`harness.provider_trace.build_raw(provider_id, ...)` maps an already-captured
provider structure into RAW payload keys; it contains no validation and no
completeness math — those live only in `analyst.trace.build_trace_record`. The Claude
reader consumes the SCHEMA=2 run-report shape (`_lib.py` `tools`/`reads`/`retrieval`/
`devloop`/`usage`) for `provenance.raw_ref`/`occurred_at`/best-effort `dispatch`
inference; nothing here re-implements `_lib.py`'s parsing, it only reads its already-
parsed dict. The Codex reader has no equivalent captured source in this repository yet
(no Codex hook ships a comparable structure) — every Codex-sourced field the reader
cannot fill degrades to `null` + `reasons[field] = "codex-hook-not-integrated"` rather
than inventing a placeholder value; this is the fail-closed default this plan requires
(§2 Execution Rules: "Missing evidence/route/capability остаётся unknown/red").

## Journal reference

`journal.py` gains one **additive, optional** field: `journal.append(...,
trace_ref=<trace_id or None>)` and CLI `--trace-ref`. When supplied, the written entry
carries an extra `trace_ref` key beyond `journal.REQUIRED_FIELDS`; when omitted the
entry is byte-identical to today's shape — `entry_validation_errors` only checks
required-field presence/type and does not reject extra keys, so this is additive by
construction, not a P1.1 schema reopen. The journal does not gain trace metrics: a
consumer wanting `tools`/`reads`/`usage` follows `trace_ref` to the trace store instead
of the journal duplicating them (Code Guidance: "linkage only in task journal").

## Boundaries (И1–И3)

| Not touched here | Owner (plan AND item) | Reason | ПРОХОД |
|:--|:--|:--|:--|
| `packages/analyst/lib/analyst/events.py`/`runs.py`/`readers/` (D90 normalized analytics envelope) | outside this plan (`fix(analytics)` lineage) | different schema, different consumers (usage/tools counts, not contract/route/dispatch/finding linkage); importing `EventEnvelope` here would couple two unrelated freezes | a genuine need to unify → D# + a proposal against that lineage's owner, never a silent reuse |
| The frozen P0.2/P2.1/P2.1-sibling contracts | P0.2, P2.1 (terminal) | this contract cites, never restates, their fields | a divergence → D# with `supersedes`, never a silent sync |
| `packages/task/lib/task/journal.py`'s REQUIRED_FIELDS/schema semantics | P1.1 | the field set this item adds is additive and outside the required closed set | a required-field change → D# against P1.1's schema, not an edit here |
| Codex-side raw capture (an actual hook emitting a comparable structure) | future item, unnamed here | no Codex hook comparable to `run-report/_lib.py` exists in this repo today | a real need for live Codex traces → new item, not an invented capture here |

**Freeze semantics (И2).** Frozen as `v1` at the close of P3.1; extension additive: a
new top-level field is a **major** bump (the closed-set check breaks every consumer's
exhaustiveness), a new value inside an existing nullable object is **minor**, a
reason-string or note edit is **patch**.

## Contribution gate (D23)

- **Existing extension points surveyed first.** `task-contract-v1.md` already owns
  contract identity/hash; `execution-state-machine-v1.md` already owns state/event;
  the P2.1 sibling already owns finding identity; `journal.py` already owns the run
  vocabulary; `analyst.events`/`readers` already own a DIFFERENT normalized-event
  schema. None of them links requirement→contract→route→dispatch→finding→public
  outcome into one record — that is the one gap this contract fills.
- **Named consumers (Rule of Three satisfied):** `P3.2` (metrics/digest derives only
  from this trace), `P3.3` (system eval adapter reads trace refs), `P3.4` (canary
  records traces per case), `P4.3` (reports the measured result).
- **Alternatives considered (≥2).** (a) *Extend the D90 analytics `EventEnvelope`
  with contract/route/dispatch/finding fields* — rejected: that envelope's consumers
  (`analyst.events`/`runs`/`readers`) are owned by an unrelated lineage outside this
  plan: widening a foreign closed schema here would be exactly the cross-boundary
  edit `plans/README.md` § «Владение поверхностями» forbids. (b) *Duplicate
  contract/route/dispatch fields directly onto `journal.jsonl` entries* — rejected:
  P1.1's schema is sealed with an exact `REQUIRED_FIELDS` tuple; growing it for every
  new linkage need is exactly the "second decision engine" pattern
  `execution-state-machine-v1.md` § Supervisor already rejected once for FOREMAN. A
  sibling record referenced by an additive optional key is additive (И10) instead.
- **SemVer/ADR result:** new schema at `v1`, additive to the frozen set; no existing
  contract changes version. `analyst` and `harness` each gain a public module — a
  **minor** package-API bump is owed (`0.1.0` → `0.2.0`, `0.3.0` → `0.4.0`) but
  `packages/*/package.json` is outside this item's declared `Files`, so the bump is
  recorded here as owed and left as Pending Work for the item that next touches those
  manifests, rather than an out-of-scope write in this item's commit (Execution Rules:
  "Каждый item коммитит только exact `Files`"). `packages/task/lib/task/journal.py`
  gains one optional parameter/flag with no required-field change, so `task`
  plugin/routing `plugin_version` is **not** bumped by this item — precedent:
  `plan.md` §7 Exported records that the version-first mechanism gates
  `commands/`/`adapters/` surface, not `lib/`-only additions (the F10 reconciliation
  note on the P2.4 row). The ADR is this section.

## Consumers

`P3.2` derives paired reliability metrics only from committed `TraceRecord`s (never
from re-parsing provider logs a second way); `P3.3` cites `trace_ref`s in benchmark
evidence; `P3.4` writes one trace per canary case as part of its evidence; `P4.3`
reports the measured trace completeness against F6. No consumer may introduce a
thirteenth top-level field of its own: the set above is closed, and widening it is a
D# against this contract, not a local extension.
