---
name: package-contribution-protocol
bucket: architect
version: 0.2.0
description: "Change a dependency at its owning source; distinguish authorized bugfixes from new public API scope."
when_to_use: "Use when a consumer task reaches a shared package."
risk: read
persona: architect
tags: [governance, package, monorepo, contribution, semver, anti-bloat, boundary]
requires: []
produces_for: []
outputs: [chat]
snippets: [proposal-issue.md, adr-template.md, claude-md-priority.md, permissions-deny.md]
adapters: [claude, cursor, fable]
sha256: ""
---

# Package Contribution Protocol

Use when consumer work reaches a shared package, or when proposing a shared abstraction.
Inspect the actual owning repository, package guide, current diff, and existing extension
points. Installed `vendor/` copies are delivery artifacts, not the durable repair source.
A monorepo `packages/` path alone does not make authorized package development read-only.

## Scope and authority

- An authorized bugfix or package change proceeds at its owning source with focused tests,
  compatibility checks, and required delivery. Do not ask again for existing authority or
  force a consumer workaround, proposal issue, ADR, or fresh session first.
- Consumer-only convenience or speculative generalization does not authorize an unrelated
  public API expansion. Use an existing contract, event, config, or local implementation when
  that adequately solves the request. Escalate the concrete missing scope when necessary.
- Rule of Three is a heuristic for discovering reusable abstractions: look for three actual
  similar cases before generalizing. It is not a two-consumer admission check for every public
  method and does not prevent fixing a bug reported by one consumer.
- Choose independent investigation/delegation only when useful and authorized; no mandatory
  go/no-go subagent. Preserve concurrent edits and qualify through the owning worktree.

## Minimal contract

Keep consumer-specific configuration in the consumer. Avoid generic base classes without an
invariant, proxy APIs with no value, and reverse imports from package to consumer. A shared
package must not become a hidden communication channel between unrelated consumers.
Compare real alternatives when a contract decision warrants it; do not manufacture two options
or a document for a routine repair.

For a substantial new public contract, use the package's adopted proposal/ADR/review process.
Drafts can make a required decision concrete, but posting an issue or contacting maintainers
still needs the task's authority. Templates below are optional carriers, not extra permission
gates. If blocked, name the missing decision and a useful next action; continue independent work.

## Compatibility and delivery

Apply the package's version policy. Under SemVer:

- Patch: compatible bugfix.
- Minor: backward-compatible added functionality.
- Major: incompatible public behavior requiring consumer adaptation.

Judge the actual compatibility, not whether a file is named `Contracts/`. Adding a required
method to an implemented interface can break implementers; an additive API elsewhere may be
compatible. Check signatures, input/output promises, stored/event formats, config keys, and
extension behavior. Follow documented deprecation/migration policy for breaking changes.

Run affected package checks and relevant consumer compatibility checks. Regenerate managed
outputs with their owner, record release-visible changes in the owning release ledger, and
keep source validation distinct from published/installed/loaded-session evidence. An unshipped
source fix is not proof that the consumer runtime changed.

## Templates and references

- [Proposal](snippets/proposal-issue.md): when a new public contract needs a recorded decision.
- [ADR](snippets/adr-template.md): when a significant decision needs durable rationale.
- [Consumer boundary](snippets/claude-md-priority.md): optional source-owned project guidance.
- [Permissions](snippets/permissions-deny.md): explicit consumer write restrictions; never
  override a real deny merely because this skill permits an owning-source repair.
- `general/anti-drift`: preserve scope and useful progress.
- `architect/api-design`: public contract design when needed.
