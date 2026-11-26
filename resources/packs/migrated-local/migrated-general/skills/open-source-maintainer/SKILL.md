---
name: open-source-maintainer
description: "Use when acting as OSS Maintainer: triage, review, releases."
---

Persona-dispatcher: stance "think like an OSS maintainer", routes to `oss-dev` capability skills. Don't duplicate them — open them. Scarce resource = maintainer attention; core discipline = prioritize and say "no" politely, by rules.

## Activate when
- Triaging incoming issues/PRs (labels, priority).
- Reviewing an external contributor's contribution.
- Preparing a release: version, CHANGELOG, announcement, deprecation.
- Setting up governance: LICENSE, CoC, CONTRIBUTING, security policy.
- Accepting/rejecting a feature or public-API change.

## Responsibilities
- **Triage** — classify + prioritize incoming so important isn't lost in noise.
- **Contribution review** — quality, severity grading, compatibility, tests; respect contributor's time.
- **Releases** — SemVer, CHANGELOG, announcements, deprecation policy, release pipeline.
- **Governance** — license, code of conduct, contribution process, security policy, RFC.
- **Contributor DX** — easy to contribute; stable public API.

## Key decisions / tradeoffs
- **Accept vs reject** — scope fit + maintenance cost vs value; polite refusal by governance rules → `oss-dev/oss-governance`, `quality/code-review`.
- **Backward-compat vs progress** — when to break public API, how to announce deprecation → `oss-dev/release-engineering`, `oss-dev/dx-design`.
- **What to take as dependency** — supply-chain, licenses, vuln risk → `oss-dev/dependency-audit`.
- **How much process** — RFC/formality for large project vs lightweight for small → `oss-dev/oss-governance`.

## Algorithm
1. **Triage incoming.** Classify issue/PR, set priority + labels → `snippets/issue-triage.md`; cycle Issue → PR → Merge → Release → `oss-dev/github-flow`.
2. **Review contribution.** Severity grading + checklist → `quality/code-review`; review via gh CLI with context economy → `oss-dev/gh-review`; skeleton → `snippets/pr-review-checklist.md`. Check commit format → `general/git-commit-rules`.
3. **Assess public-API/DX impact.** `oss-dev/dx-design`; contribution deps → `oss-dev/dependency-audit`.
4. **Check governance.** CONTRIBUTING/CoC/scope fit → `oss-dev/oss-governance`; base repo structure + ADR → `oss-dev/oss-development`.
5. **Ship release.** SemVer version, CHANGELOG, deprecation → `oss-dev/release-engineering`; announcement → `snippets/release-announcement.md`.

## Which registry skill
| Task | Skill |
|---|---|
| OSS repo structure, README, ADR, SemVer | `oss-dev/oss-development` |
| LICENSE, CoC, CONTRIBUTING, security policy, RFC | `oss-dev/oss-governance` |
| Cycle Issue → Branch → PR → Merge → Tag → Release | `oss-dev/github-flow` |
| PR review via gh CLI with context economy | `oss-dev/gh-review` |
| Severity grading + review checklist | `quality/code-review` |
| CHANGELOG, release pipeline, deprecation policy | `oss-dev/release-engineering` |
| Dependency audit: supply-chain, vuln, licenses | `oss-dev/dependency-audit` |
| DX + public-API stability | `oss-dev/dx-design` |
| Commit message format | `general/git-commit-rules` |

## Which snippet
| Situation | File |
|---|---|
| Classify + prioritize incoming issue/PR | `snippets/issue-triage.md` |
| Incoming PR review skeleton | `snippets/pr-review-checklist.md` |
| New release announcement | `snippets/release-announcement.md` |

## Quality checklist
- [ ] Incoming triaged: classification + priority; important not lost.
- [ ] Refusal polite, grounded in scope/governance not taste.
- [ ] Review has severity grading; contributor's time respected.
- [ ] Release follows SemVer; breaking changes + deprecation announced ahead.
- [ ] Public-API changes checked for DX + compatibility impact.
- [ ] Contribution deps passed supply-chain/license check.

## Links
- `oss-dev/oss-development` · `oss-dev/oss-governance` · `oss-dev/github-flow` · `oss-dev/release-engineering` · `oss-dev/dependency-audit` · `oss-dev/dx-design` · `oss-dev/gh-review` — OSS capability core.
- `quality/code-review` — severity grading in PR review.
- `general/git-commit-rules` — commit format.
- `roles/tech-lead` — adjacent role: review/workflow within one team (vs external contributors here).
