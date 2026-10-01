# agent-packs — versioned packs agent-practitioner

Pack = versionable bundle Claude Code artifacts (agents/work flow/hooks/settings/docks),
which the agent installs and updates in the project. **Distributes not code, but data**:
installation/adaptation/upgrade is executed by the agent `pack.json` + `CHANGELOG.md` + lock,
without Python/Mustache engine (see skill `system/agent-packs` in skiller).

## Pack structure

```
<pack>/
  pack.json        # manifest: version, stack-detect, requires, interview[], files[]
  CHANGELOG.md     # per-pack semver + agent-facing Migration notes
  agents/          # templates .md (name: {{PACK_PREFIX}}-<role>)
  workflows/       # templates .js
  hooks/           # review-gate.sh (verbatim) + .env.ini (template)
  settings/        # settings.fragment.json (merge in .claude/settings.json)
  docs/            # guideline-template
```

## Placeholders

`{{PLACEHOLDER}}` in files `kind: template` are substituted from interview responses
(`pack.json:interview`). Blocks `<!-- pack:if KEY -->...<!-- pack:endif -->` agent
leaves/removes based on a Boolean response. Files `kind: verbatim` are copied without edits.

## Installation / upgrade

**Deterministic path (recommended)** — CLI `harness agent-packs`: resolves interview
from `detect:`-samples+defaults WITHOUT agent, renders, writes lock. Yes `maind sync`/`maind onboard`
roll out packs automatically (project type profile names `agent_pack`):

```bash
harness agent-packs list
harness agent-packs render  --auto --pack <pack> --target . [--answer KEY=VAL ...]
harness agent-packs upgrade        --pack <pack> --target .
harness agent-packs doctor  [--pack <pack>]
```

**Agent-driven path (fallback)** — skill **`system/agent-packs`** (skiller): for ambiguous
cases (`needs-agent`/`conflict`) or prose adaptation. Both paths write ONE format
`.claude/agent-pack.lock.json` (sha256 rendered) — are compatible. Upgrade — by
CHANGELOG-delta with 3-way reasoning via sha256, without diff-engine.

## Review role registry (`configs/common/agent-packs/review-roles.json`)

Separate extension-table (not `role-bindings.json` — he carries provider-binding
`{pack_id, role_id, model_selector, color}` and does not touch, D126) by key
`(pack_id, role_id)`, next to the canon of role bodies `configs/common/agent-packs/roles.json`.
Five entries `role_id: "reviewer"` — **index** review procedure carrier (not a copy of the rules):
`projection`/`overrides` — path to `agents/reviewer.md` and `rules/reviewer-overrides.md`
(compatibility-assets, byte-in-byte canon projection), `required_sections`/`sections` —
four required sections and their ACTUAL headers in the pack (are not reduced to one form -
this is a content edit, outside scope), `dimensions` — review measurements from a closed dictionary.
`skills` is NOT in the registry - this is a verbatim double `roles.json.skills`, canon is read directly.
Validator `harness.reviewroles` (`PYTHONPATH=lib python3 -m harness.reviewroles --check`,
step `[8/8]` `scripts/validate.sh`) checks the registry against disk and canon: two-way
default-deny (pack on disk without recording And the role of canon without recording), existence projection/
overrides, literal match of headers with `roles.json` `content` (and not with projection -
divergence of canon and projection separate violation), `dimensions` ⊆ dictionary,
`roles.json.skills` ∈ `packages/skiller/skills.json`, `review_version` checked against
fixed composition fingerprint. Found drift between packs (different headers of the same
sections, different set `skills`) — is not repaired by this mechanism, it is an actual map
discrepancies (see).

## Packs

| Pack | Shape | Stack | Version |
|---|---|---|---|
| `_common` | agnostic | orchestrator (delegate-only) — general prerequisite | 0.4.0 |
| `backend-laravel` | backend | Laravel/PHP (application) | 0.11.1 |
| `laravel-package` | backend | Laravel-composer-package (incl. monorepo `packages/*/src`) | 0.1.0 |
| `node-frontend` | frontend | Vue/Vite/TS (SPA/Inertia/Nuxt) | 0.4.1 |
| `dart-flutter` | mobile | Flutter/Dart (mobile/POS/embedded) | 0.4.1 |
| `python-backend` | backend | Python (FastAPI/Django/Flask) | 0.4.1 |
| `role-tech-lead` | role | tech-lead (sprint/delegation/review) | 0.2.1 |
| `role-cto` | role | startup-CTO (architecture/tech-radar/AI-viability) | 0.1.1 |
| `role-founder` | role | solo-founder (discovery/MVP/cadence) | 0.1.1 |
| `role-maintainer` | role | OSS-maintainer (triage/review/release) | 0.2.1 |

Each profile (`packages/skiller/profiles/<type>.json`) calls `agent_pack` (string OR
list - **composition**: stack pack + `_common`). Fullstack = composition by concern
(`backend-laravel` + `node-frontend`). Roles are universal, stack selects profile; model
shooting ranges - from `profile.model_tiers`. PostToolUse-validators (tsc/eslint, dart analyze, ruff) —
advisory (inject errors, do not block).

### Role-packs (`role-*`) — cross-stack, by person

`role-*` — **person-pack** (`shape: role`): subagents per role, NOT per stack. Cross stack
(no `stack.project_type`/`detect` → NOT auto-linked by project type). Delivery
(**option A+C**): project declares active roles in `config.json` (`project.roles: ["tech-lead"]`),
and hub map `role_packs` (`{"tech-lead":"role-tech-lead", …}`) mappit role → pack; `maind sync`
adds a pack additively to the profile stack pack (`maind/lib/maind/sync.py:_resolve_agent_pack`).
Subtle selection of one role in the project - also through vendor (`roles/<role>`, field `role_agent_pack`
in frontmatter skill). Model shooting ranges - **literals** in `model:` agents (opus — heavy
judgments: architecture/planning/validation; sonnet — routine: triage/review/cadence), because
standalone-delivery not received `profile.model_tiers`.
