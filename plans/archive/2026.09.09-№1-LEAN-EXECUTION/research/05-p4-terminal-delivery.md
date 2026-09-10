# P4 terminal delivery synthesis

## Sources

- `artifacts/source-roadmap/2026.08.11-terminal-final-continuity-receipt.md`
- `artifacts/source-roadmap/2026.08.11-terminal-handoff-recommendation-receipt.md`
- `artifacts/source-roadmap/2026.08.14-p10.6-provider-final-incident.md`
- `artifacts/source-roadmap/2026.08.15-owner-decision-same-session-continuity.md`
- `findings/05-p4-design-baseline.md`
- [OpenAI Codex Hooks](https://developers.openai.com/codex/hooks)
- [Anthropic Claude Code hooks](https://code.claude.com/docs/en/hooks)

## Vertical decomposition

1. **P4.1 owns the policy and durable local evidence.** A Task lease starts only for an admitted
   Task plan command and binds provider-neutral session, run, plan, subject and command identities.
   Each material continuation refreshes monotonic sequence/progress. At pre-final time, one pure
   reducer consumes the P1.3 continuity verdict, rebuilds the current delivery receipt and compares
   the exact machine-authored final response. It emits `final_allowed=false` plus a named continue,
   waiting-owner or recovery reason until every terminal invariant matches; only then does it emit
   `true` and release the lease. RAG:—.
2. **P4.2 owns event translation and activation.** Harness adds one semantic
   `lifecycle.terminal-admission` surface with separate Codex and Claude Code payload/response
   adapters. It calls the worktree-local Task CLI, keeps the last message in process memory, and
   maps false to the provider-native blocking continuation. With no applicable lease it is a no-op;
   malformed applicable state fails closed with a stable diagnostic. RAG:✅ for provider event
   and response shapes; RAG:— for local ownership.
3. **The proof is bounded and honest.** A deterministic fixture drives forty artificial stop
   boundaries with advancing sequence/progress, asserts forty false events, then submits the exact
   terminal template and asserts one true event. This proves local contract continuity and adapter
   translation, not unbounded live transport control. Claude Code's documented eight consecutive
   block override is recorded as a provider limit. RAG:✅ for the limit; RAG:— for the fixture.

## Ownership and alternatives

- Extending `plan_delivery.py` alone is rejected: it cannot observe a provider stop attempt or the
  actual response bytes. It remains the receipt owner and becomes an input to terminal admission.
- Putting terminal policy in each hook is rejected: providers would fork plan/continuity semantics
  and could disagree on the same receipt. Hooks normalize and render only.
- Recomputing whether to continue in P4 is rejected: P1.3 owns the session/work decision. P4 binds
  its typed output to the active lease and enforces it.
- Persisting full transcript text is rejected: exact comparison can be performed in memory while
  evidence stores the expected/observed hashes and verdict.
- Treating every `Stop` as a Task run is rejected: absence of an applicable lease must not block an
  ordinary conversation.
- An unbounded retry promise is rejected: provider caps, disabled hooks and untrusted projects are
  named capability gaps under D5/D9.

## Lease and transition contract

The lease is project-local ignored runtime state, not a plan carrier. Its minimum identity is
schema version, repository realpath, provider/session, Task run, plan/subject/command, lifecycle
state, sequence, progress fingerprint, continuity-decision identity, issued/refreshed/expiry times
and last event identity. Atomic replace plus sequence compare-and-swap prevents two stop callbacks
from both admitting final. Events are append-only and contain those identities, expected/observed
message hashes, `final_allowed`, reason, recovery/continuation and provider provenance—never the raw
message.

Transitions are closed: `armed -> active|waiting-owner -> terminal-candidate -> released`; named
abort/recovery handles crashed, expired or ambiguous state. No lease is `not-applicable`. An
applicable stale/invalid lease is an error/capability verdict and cannot return true. Terminal
admission requires the exact run/subject/command, terminal P1.3 decision, current valid delivery
receipt, current persisted recommendation and byte-exact canonical final response.

## Coupling and order

P4.1 follows P1.3 because it consumes rather than recreates continuity. It lands schemas, reducer,
CLI and Task command wiring first. P4.2 then adds the Harness surface, provider adapters, capability
manifest and generated artifacts. One phase-local manual high-route batch reuses terminal fixtures
while preserving two item commits and validations. The P4 audit owns the cross-package invariant:
each supported Stop payload produces the same Task verdict and only provider-specific response
syntax differs.

## Pre-mortem and stop conditions

- **Stale lease blocks unrelated work.** Mitigation: exact repository/session/run applicability,
  expiry and named recovery; no lease is a no-op. Stop if a fixture blocks a different session.
- **Two policy owners drift.** Mitigation: adapters cannot decide terminality and golden tests compare
  both providers against one Task event. Stop if a hook contains plan-state heuristics.
- **Receipt passes but response lies.** Mitigation: bind the canonical expected response and compare
  exact bytes in memory. Stop if tests admit a paraphrase or omit the persisted recommendation.
- **Retry loop becomes infinite or contradicts a provider cap.** Mitigation: advancing-progress
  fixture, provider retry fields, expiry and documented Claude limitation. Stop if validation claims
  forty unchanged live blocks.
- **Evidence leaks transcript content.** Mitigation: only hashes/identities/verdicts persist. Stop if
  a raw sentinel from a test message appears in runtime files.
- **Generated provider artifacts drift.** Mitigation: change owner inputs, regenerate, and run
  renderer/provider-doc checks. Stop if any generated file requires a hand edit.

## Проверка

The initial P4 design pass used an official-domain WebSearch fallback because its session did not
expose Context7 or Perplexity. Finish reconciliation repeated the fact classes through Context7
(`/openai/codex`, `/websites/code_claude`), three official-source Perplexity queries and direct
official-page checks on 2026-09-09; detailed evidence is in
`findings/08-finish-external-verification.md`. The re-pass confirms the documented Stop payload and
continuation semantics, Claude Code's eight-consecutive-block cap and its documented
`CLAUDE_CODE_STOP_HOOK_BLOCK_CAP` override. Repository claims remain code-grounded. No support claim
extends beyond configured, trusted CLI hook surfaces.

- RAG: Context7 ×3 OK · Perplexity official-source synthesis ×3 OK · direct official pages ×3 OK.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: live provider enforcement outside configured/trusted CLI hooks; intentionally an execution-time capability verdict in P4.2, not a design assumption.
- Обходки/[POSSIBLE-DEFECT]: none; the forty-boundary deliverable remains a local deterministic proof, not a promise of forty unchanged live provider blocks.
