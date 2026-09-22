# P3 owner/authority threat model

## Boundary and decision

The constrained principal is the coding agent process. It can control ordinary
environment variables, repository files, local transcript paths and Task library
calls. Hashing those bytes proves consistency, not owner identity.

Neither inspected provider exposes a provider-issued, cryptographically verifiable
owner-attestation envelope to these local adapters. Codex exposes session/turn/hook
metadata and approval policy; Claude Code exposes session identity and permission
flows. Those are useful workflow observations, but the current process can read or
influence their local carriers. Therefore both built-in adapters are classified as
`workflow-guard`, never `security-boundary`.

Protected or irreversible actions require an independently verified
`provider-attestation/v1` envelope and fail closed while no such adapter is installed.
Reversible repository-local diagnostics may use the labelled workflow guard, backed
by durable local replay/commitment state. A declared owner gate is protected and does
not activate from that evidence. No signing service or agent-held secret is added.

Primary-source sanity check (2026-09-22):

- OpenAI documents local hook inputs such as session/turn IDs, transcript paths,
  model and permission mode, plus managed/local hook trust. It does not document a
  signed owner-intent assertion consumable by this package:
  <https://developers.openai.com/docs/hooks>.
- OpenAI documents approvals and sandbox policy as execution controls, not signed
  action attestations: <https://developers.openai.com/docs/sandboxing>.
- Anthropic documents session IDs, permission modes and external permission-prompt
  tools, but not a signed owner-intent envelope for local consumers:
  <https://code.claude.com/docs/en/cli-usage>.
- Anthropic's security model places approval and review responsibility at the user/
  organization permission boundary: <https://code.claude.com/docs/en/security>.

## Assets, principals and entry points

| Asset | Principal / writer | Entry point | Required property |
|:--|:--|:--|:--|
| Exact owner intent | provider/user boundary | Codex or Claude owner invocation capture | Never upgraded from local bytes to authenticated identity |
| Canonical action | Task policy + trusted observation | `canonical_action()` / `evaluate()` | Observed facts override caller claims; unknown facts require approval |
| Commitment budget | Task authority store | `authorize()` | Item-lifetime aggregation survives restart and concurrent processes |
| Response/nonce use | Task authority store | `apply_response()` / attestation verification | One atomic consume per plan/item/action/version/nonce |
| Owner grant activation | plan authority transaction | `materialize_owner_invocation()` | One plan lock; activation published last; partial work stays inactive |
| Provider evidence | provider adapter | `capture_current()` | Exact schema and explicit boundary classification |

## Provider support matrix

| Provider | Observed channel | Current classification | Protected mode |
|:--|:--|:--|:--|
| Codex | Local thread state selected by `CODEX_THREAD_ID`; exact prompt/cwd/route | `workflow-guard` | Denied: no provider-issued signature/MAC and external nonce service |
| Claude Code | Local project JSONL selected by `CLAUDE_CODE_SESSION_ID`; exact command/cwd/route | `workflow-guard` | Denied: no provider-issued signature/MAC and external nonce service |
| Future provider adapter | Exact `provider-attestation/v1` plus independent verifier/store | `security-boundary` only after verifier success | Allowed once issuer, audience, subject, action, time and nonce all verify |

## STRIDE analysis

| Threat | Category | Mitigation / acceptance evidence |
|:--|:--|:--|
| Forged environment or transcript impersonates the owner | Spoofing | Adapters label local evidence `workflow-guard`; protected verification rejects it |
| Missing/extra fields or altered action binding | Tampering | Exact versioned attestation schema; canonical action digest; mismatch rejects |
| Owner/agent disputes which response was consumed | Repudiation | Durable keyed consume record under the plan authority lock |
| Transcript or secrets copied into activation evidence | Information disclosure | Persist digests and bounded identifiers only; never raw transcript bodies |
| Store corruption/lock contention silently downgrades checks | Denial of service | Fail closed with a typed denial; diagnostic evaluation remains explicit and side-effect free |
| Caller labels risky work reversible and self-delegates | Elevation of privilege | Policy uses `observed_action`/`verified_provenance`; unverifiable predicates require approval |
| Crash leaves message/decision that a resolver treats as active | Tampering / Elevation | Prepare under one plan lock and publish a durable activation record last; resolver requires it |
| Response or nonce is reused by another process | Replay / Elevation | Atomic read-check-write consume in the durable store; duplicate key rejects after restart |
| Multiple small grants cumulatively exceed declared scope | Elevation of privilege | Durable aggregation key `(plan_id, item_id, decision_class)` and union/intersection policy |

## Chosen implementation boundary

1. Add an exact provider-attestation contract and explicit adapter capability.
2. Keep local provider evidence usable only as a labelled diagnostic workflow guard;
   it cannot activate an owner gate.
3. Add a small plan-local locked durable store for workflow commitment and response
   consumption; stateless operation is diagnostic-only.
4. Keep caller observations diagnostic; enforced mode requires approval until a real
   analyzer derives verified facts.
5. Materialize owner grants under one lock and require an activation-last record.
6. Preserve old decisions/messages as readable legacy records, but never treat an
   unactivated record as a protected grant.

The local store improves replay and crash behavior for workflow guards; because the
agent principal can write the project, it is deliberately not described as a security
root. A future protected adapter must own verification and nonce consumption outside
that principal.
