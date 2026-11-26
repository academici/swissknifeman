---
name: packages-stack
bucket: general
version: 0.1.0
lifecycle: init
description: "Project external-dependency registry methodology: which packages are used and for what, a per-package rule (when to use, what NOT to do by hand), reliance on OFFICIAL docs. Activate when choosing/adding a dependency or mapping the stack at project init; language-agnostic."
risk: read
persona: oss-dev
tags: [dependencies, conventions, navigation, stack, init]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# External dependency registry (methodology)

Keep a short **stack registry**: which external packages are used, **for what**, and the rule tied to each. Language-agnostic; the concrete package list lives in the project's docs/`.ai`, not in the skill registry.

> **lifecycle: init** — for project init / stack choice / adding a dependency, not permanent. Do not keep in CORE/default distribution "forever".

## When to activate
- Choosing or adding an external dependency (composer/npm/pip/…).
- Building/updating the stack map at project start.
- "Which package solves this and how to use it correctly".

## Record per package
1. **Name + purpose** — why it's in the project (one line).
2. **Rule** — how to use it here and **what NOT to do by hand** (e.g. "files via the media package, not `Storage::put()` directly").
3. **Link to OFFICIAL docs** — source of truth for API/version.

## Rules
- If the knowledge base lacks current package info — **go to official docs** before writing code (API changes across majors).
- Don't duplicate package functionality with your own code — first check it isn't already solved.
- Versions/constraints — single source (lock file), not "from memory".
- Keep the registry **short**: only actually-used packages with a non-obvious rule.

## Checklist
- [ ] Each key dependency: purpose + rule + official-docs link.
- [ ] No hand-rolled duplicate of what the package does.
- [ ] Registry in project docs; no concrete project names in the shared skill.

## Related skills
- `oss-dev/dependency-audit` — dependency audit (vuln, licenses, supply-chain) over the registry.
- `python/venv-dependencies`, `php-packages/laravel-packages` — stack-specific dependency management.
