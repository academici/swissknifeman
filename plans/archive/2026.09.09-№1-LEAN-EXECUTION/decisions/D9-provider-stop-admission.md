---
id: D9
date: 2026-09-09
status: accepted
item: P4.1
items: [P4.1, P4.2]
supersedes: []
superseded_by: null
---
# D9 — Use documented provider Stop hooks for terminal admission

**Actor:** design-author/gpt-5.6-sol/high
**Evidence:** RAG:✅ `research/05-p4-terminal-delivery.md`; official OpenAI Codex Hooks and Anthropic Claude Code Hooks documentation verified 2026-09-09

## Решение

Keep terminal policy provider-neutral in Task and use the documented provider `Stop` event as the
only supported Harness enforcement write-site. P4.1 owns the lease, continuity/receipt check, exact
final-message binding and `final-admission-event/v1`; P4.2 only adapts Codex and Claude Code event
fields and provider-native allow/block responses. A missing, disabled, untrusted or undocumented
hook surface remains an explicit capability gap under D5 rather than inferred support.

## Почему

The existing Task delivery receipt validates repository bookkeeping but cannot inspect the actual
assistant response. Current official docs now expose the last assistant message and a blocking
continuation response at `Stop`, so the repository has a real adapter seam that did not exist in
the historical P10.6 evidence. Keeping policy in Task prevents provider forks; keeping transport
claims in Harness prevents a local proof from being mislabeled as universal provider control.

## Consequences

The forty-boundary proof is deterministic local adapter/state-machine evidence with advancing
progress, followed by one exact allowed final response. It is not a claim of forty consecutive live
provider blocks: Claude Code documents an eight-block override, and any provider may require
explicit trust/configuration. Support records name those limits and unsupported surfaces. Raw last
messages remain process-local; persisted events contain only identities, hashes and verdicts.
