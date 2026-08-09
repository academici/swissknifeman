# Decision Request Contract v1

Status: frozen by `P5.1` on 2026-08-09.

The machine-readable contract is
[`decision-request-v1.schema.json`](decision-request-v1.schema.json). It is the only source of field
names, requiredness, closed enums, constants, record limits, and reason codes. This document defines
their meaning and boundaries without maintaining a second schema.

## Decision kinds and authority boundary

The contract recognizes a closed choice between a request for missing facts and a request for the
right to act. A clarification may supply only explicitly missing facts from a named system of record;
it never grants authority, widens the target, adds a side effect, raises privilege, changes the action
class, or reopens a rejection. Authorization is granted only by the pinned authority frame or its
named owner. A case that cannot be classified under the machine enum is escalated; writers must not
invent a third kind.

The model may propose an option and evidence references. It may not choose the action type,
canonicalization profile, material-field registry, decision class, timeout policy, policy version, or
either digest. Those values come from deterministic tooling and the pinned authority-frame instance.

## Request identity and continuation

A request identifies one plan item as its subject and one version of a canonical action. The machine
schema defines the complete request shape and the purpose-bearing substructures for evidence,
attempts, options, and continuation.

Continuation identity is part of v1, not queue metadata added later. It preserves the originating
root session and run, the exact plan/item resume target, and a digest-addressed capability snapshot.
The preferred path is `resume-root`. If a later runtime cannot resume that root, it records a
`cold-start-root` fallback with an exact reason while leaving the original request immutable.

## Canonical action, material change, and digest

The tool constructs the canonical action from the schema's closed material-field registry, serializes
it as sorted-key compact UTF-8 JSON, and records the lowercase SHA-256 digest of those exact bytes.
The model cannot override the registry or assert semantic equivalence.

Changing any material field creates the next action version, a new canonical action, a new digest,
and a new request. A prior response is never carried across that boundary. A pinned deterministic
mapping may declare equivalence only when its version and output participate in canonicalization.

## Options and response application

Each decision class supplies a closed set of substantive options within the machine bounds. The two
reserved outcomes for escalation and rejection are always present. A writer rejects any undeclared
option, including one invented by the model.

A response selects one declared option and records its resolver, reason, policy digest, action digest,
provenance, and time. Immediately before application, the effect boundary reconstructs the action
from trusted records and rechecks the action and policy digests. A mismatch is rejection plus a new
request, not approximate reuse. A response is single-use for its exact decision/action identity.

## Timeout and policy failure

Timeout behavior belongs to the decision class in the authority frame; a request merely carries the
resolved value. The schema fixes the admissible envelope by decision kind. Authorization can only
park on timeout. Applying a default is legal only for a reversible clarification inside an explicitly
preauthorized envelope; it is never implicit approval. Policy errors and unknown options always
reject.

## Clarification reclassification and auto-answer evidence

After every clarification response, the tool canonicalizes and classifies the resulting intent again.
The response is invalid without the recorded new classification, which may now require authorization.
Primary classification never sticks merely because the interaction began as a clarification.

Every automatic clarification response creates a separate append-only typed event. Its machine shape
binds the resolver and system-of-record provenance, before/after digests, policy digest, and the result
of reclassification. Model memory, retrieved prose, issue text, email, and web content are evidence,
not authoritative sources for an automatic answer.

## Record boundary and size limit

Decision records contain typed facts, hashes, and references to plan carriers. The schema's closed
forbidden-content list excludes model reasoning and transcripts, provider payloads, secrets,
environment contents, worker prose, inline evidence bodies, undeclared options, and a copied P4
owner packet. The writer measures compact canonical UTF-8 bytes before append and rejects records
over the frozen machine limit.

## Relationship to the P4 owner packet

P4 owns the return-loop owner packet: fingerprint identity, counter and ceiling, history, judgements,
and attempted resolutions. This contract only wraps a reference to that packet in decision options,
expiry, timeout behavior, and continuation. It neither rebuilds nor changes the frozen P4 payload or
its blocking force.

## Rejected alternatives

- Free-form prose as the decision channel was rejected because it requires natural-language policy
  interpretation at the authorization boundary.
- A third catch-all decision kind was rejected because it silently expands the authority surface;
  unclassified cases escalate.
- A request-selected timeout rule was rejected because it lets an untrusted proposal choose its own
  failure behavior.
- Model-computed digests or model-judged equivalence were rejected because approval would no longer
  bind the bytes executed.
- Cryptographic approval signatures and an external PDP runtime were rejected for v1: git already
  carries the single owner's authorship, and the repository runtime remains stdlib-only.
- Copying the P4 owner packet into the request was rejected because it creates a divergent second
  carrier for the same evidence.

## Verification boundary

Validation parses the JSON contract, proves the two-kind closed world, checks timeout and failure
constants, requires continuation identity and reserved options, verifies the record limit and
forbidden set, and compares the P5 reason-code namespace with the frozen donor. P5.3 owns runtime
resolution; P5.4 owns storage, batching, and subject-local parking; P5.5 owns the adapter over the P4
packet; command integration remains P6.
