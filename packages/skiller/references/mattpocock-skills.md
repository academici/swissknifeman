# mattpocock/skills

- **URL:** https://github.com/mattpocock/skills
- **License:** MIT (© 2026 Matt Pocock)
- **Status:** imported
- **Checked:** 2026-06-26 (HEAD `5d78bd09`)

Battle-tested engineering skills Matt Pocock (TotalTypeScript). Strong methodology
(Ousterhout «Philosophy of Software Design», Feathers «Working Effectively with Legacy Code»),
and not templates. Orientation - Node/TS and one maintainer; we have a multi-stack (PHP/Laravel, Dart/Flutter,
embedded, fintech). Direct replacement is impossible - we take the methodology point by point, localization of examples (PHP/Dart)
as a separate wave (faithful-first).

The source's key finding is explicit **two-tier activation** (`skills/engineering/README.md`):
skills are divided into **user-invoked** (`disable-model-invocation: true` — explicit call only) and
**model-invoked** (rich `description` → auto-trigger). We transfer this classification one-to-one
to our activation conditions.

## What's taken (first wave → upstream.json, strategy notify)

| mattpocock | our target | activation |
|---|---|---|
| diagnosing-bugs | `quality/diagnosing-bugs` | model-invoked (auto) |
| tdd | `quality/tdd-discipline` | model-invoked (auto) |
| codebase-design | `architect/codebase-design` | model-invoked (auto) |
| domain-modeling | `architect/domain-modeling` | model-invoked (auto) |
| implement | `general/implement` | **user-invoked** (writes code) |
| to-issues | `oss-dev/to-issues` | **user-invoked** (posts to GitHub) |
| triage | `oss-dev/issue-triage` | **user-invoked** (via agent) |
| grill-with-docs | `general/grill-with-docs` | **user-invoked** (explicit session) |
| resolving-merge-conflicts | `oss-dev/resolving-merge-conflicts` | model-invoked (auto) |

Source sub-files (DEEPENING/DESIGN-IT-TWICE, CONTEXT-FORMAT/ADR-FORMAT, AGENT-BRIEF/OUT-OF-SCOPE,
tests/mocking, HTML-REPORT) → ours `snippets/` (tier-2 on-demand).

## Spot (EXTEND, without a separate skill)

- **to-prd** → enhances `general/spec-interview` (grilling severity) + form PRD remains `pm/prd-from-brd`.
- **improve-codebase-architecture** → HTML-REPORT.md as optional snippet in `architect/codebase-design`;
  link from `quality/refactoring-plan`. We do not create a separate skill (take refactoring-plan + codebase-design).
- **grill-with-docs** — at the source thin wrapper «`/grilling` + `/domain-modeling`»; with us =
  `spec-interview` (our grilling) + `architect/domain-modeling`, builds CONTEXT.md/ADR inline.

## B harness, not a skill

- **git-guardrails-claude-code** — we have hooks/permissions belong to the package `harness`.
  Script `block-dangerous-git.sh` + PreToolUse-preset → Harness hooks,
  is distributed through `harness hooks` (+ opt. thin `general/git-safety`, `lifecycle:init`).

## Do not take

- **setup-pre-commit** — Husky/lint-staged, JS-specifics (deferred; later PHP-analogue in `devops`).
- **prototype** — partially covered; postponed, note in `implement`/`spec-interview`.
- **scaffold-exercises**, **migrate-to-shoehorn**, **ask-matt** — training/personal tools/personal router.
- **setup-matt-pocock-skills** — bootstrap its repo; study as a model of the future `setup-swissknifeman`.

## Target Buckets

`quality/`, `architect/`, `general/`, `oss-dev/` (methodology, fold-in, without a new bucket).
Distribution - opt-in via `presets/` (`agent-tasks`, `code-quality`, `system-design`, new
`engineering-workflow`), NOT in CORE.

## Chain (embedding, not folders)

`spec-interview → grill-with-docs(+domain-modeling) → to-issues → implement → tdd-discipline → code-review`;
`diagnosing-bugs → code-review`; `codebase-design → refactoring-plan/architecture`. Ribs - through
`requires/produces_for`, agents ship via `skills:` (issue-triager←issue-triage, sprint-planner←to-issues,
review-gatekeeper←diagnosing-bugs/tdd-discipline).
