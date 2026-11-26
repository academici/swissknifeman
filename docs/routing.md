# Source priorities and task routing

## Source reading order

1. **Root `CLAUDE.md` / `AGENTS.md` project** — hub: what kind of project is it, where to look next.
2. **Design `.ai/skills` + `.ai/guidelines`** — highest rule priority (specifics of this particular project).
3. **Laravel Boost** — version-specific skills and guidelines (see [boost-compatibility](/skiller/boost-compatibility)).
4. **Skills swissknifeman** — architecture, practices, processes.

**Rules conflict → wins more specific source: project > Boost > registry.**

Repository bootstrap skills are host-owned and listed in
`configs/repository-bootstrap-skills.json` (schema v2), selected by `bootstrap` in
`configs/skiller-host.json`. Canonical files live in `bootstrap/skills/<identity>/`
or the owner's `packages/<owner>/dev-skills/<identity>/`; these development skills
are excluded from distributed registries and plugins. `skiller registry` generates
the thin `.claude/skills` and `.agents/skills` pointers and
`bootstrap/publication-lock.json`. `skiller registry --check` verifies their paths,
hashes, bytes and complete identity sets. The bootstrap unit version belongs to the
host config; the fixed class-A content version remains separate.

## Architectural layers: what goes where (anti-sprawl stop rule)

swissknifeman — **four-pack umbrella**, and not one «core». Before you add something, decide in which
layer this gets in - it stops spreading (ecosystem goal - *best policy-driven
orchestrator, not the largest set of skills*):

| Layer | What is this | Where does he live? | Examples |
|:--|:--|:--|:--|
| **Content / techniques** | skills, checklists, standards, stack-instructions | package **skiller** (`skills/`, `presets/`, `profiles/`) | github-ops, tdd-discipline, mcp-advisor |
| **Orchestration / policy / memory** | provisioning, graph, namespace-memory, MCP-hub | package **maind** (`lib/maind/`) | sync, health, fleet, MCP-server `maind_*` |
| **Training / lessons** | capturing lessons from runs, cross-project patterns, man-gate | package **analyst** (`lib/analyst/`) | digest, scan, suggest, promote |
| **Environment** | permissions, hooks, wiring MCP-servers, canon of root instructions | package **harness** (`configs/claude-code/`) | presets permissions, directory MCP, `harness instructions` |
| **External engine** | mature runtime, which we don’t write ourselves | connects externally | GitHub CLI, Serena (code graph), agentmemory, browser |

**Rule:** new ability is new **record in one of the layers**, and not the code in maind «just in case
case». Stack instructions, test doctrines, security-checklists, GitHub-work flow → **skill/preset in skiller**,
and not Python in maind. Select MCP-servers for the project → presets `profiles/mcp[]` + skill `general/mcp-advisor`,
and not the second section in the config maind. Mature market engine → connect as external MCP/CLI, is not re-implementable.

Canon by layers - in the packages themselves: [skills architecture](/skiller/guide/skills-architecture) (skiller),
[node composition](/maind/architecture) (maind), [continuous learning](/analyst/) (analyst),
[configs and MCP](/harness/) (harness).

## Skill search algorithm

1. **Profile** — what role solves the problem (`profiles/`): developer, founder, operator, PM.
2. **Bucket** — subject area: `php`, `frontend`, `devops`, `quality`, `architect`, `pm`, `founder`, `operator`, `oss-dev`, `general`, `python`, `blender`, `roles`, `imported`.
3. **Task table** below - direct comparison «doing X → open skill Y».
4. **Tags `skills.json`** — if the table does not cover it, search by tags.

Native scope Claude Code does not replace this algorithm: `when_to_use` specifies the moment of selection,
a `context: fork` transfers the body of individual procedural skills to the child context. Field
`paths:` in the registry is not deliberately rolled out: it did not improve detection in the measured
pilot. So still start with the profile and bucket rather than counting on the file path like
to a single search engine.

## Task type → skill

### PHP / Laravel

| Task | Skill |
|:---|:---|
| I am writing a migration, model, database schema | `php/database` |
| New domain / new Laravel-project (folder structure) | `php/laravel-structure` |
| The project has grown: dozens of domains, several teams | `laravel-architecture/modular-architecture` |
| Use-case / business transaction | `php/laravel` (actions.md) + `php/dependency-injection` |
| Data samples, query-layer | `php/repositories` |
| Rights, roles, RBAC | `azguard/azguard` (universal) / `laravel-auth/laravel-permissions` (policies, gates) |
| Metadata enum (label, color) | `laravel-architecture/enum-attributes` |
| Value Object, DTO, pipeline | `php/php-patterns` |
| Review/refactoring Laravel-code (without Boost) | `php/laravel-best-practices` |
| Code-style PHP | `php/code-style-spatie` |
| Pint / PHPStan / Rector, quality pipeline | `php/static-analysis` |
| Feature/Unit-application tests, database isolation, coverage gate | `laravel-testing/laravel-testing` |
| Browser E2E-tests | `laravel-testing/laravel-dusk` |
| WebSocket / Echo / Reverb | `laravel-data-layer/laravel-broadcasting` |
| Admin-panel Filament | `laravel-filament/filament` |
| File uploads, media, conversions | `laravel-extras/medialibrary` |
| Telegram/chatbot | `botkit/botkit` |
| New Laravel-package (scaffold) | `php-packages/laravel-packages`, `php-packages/laravel-package-scaffold` |
| Service provider package | `php-packages/laravel-package-service-provider` |
| Package tests (Pest + Testbench) | `php-packages/laravel-package-testing` |
| Package documentation | `php-packages/laravel-package-docs` |
| Package release | `php-packages/laravel-package-release` |
| Package Compatibility Matrix (PHP/Laravel/Testbench) | `php-packages/laravel-package-compatibility` |
| Boost-skill inside the package | `php-packages/laravel-package-generate-skill` |
| Edits by myself starter kit laravel-expressive | `php-packages/laravel-package-expressive` |

### Frontend

| Task | Skill |
|:---|:---|
| Page/form Inertia, where to put the file in `resources/js/` | `frontend-backend/inertia-vue` |
| Vue-component, Composition API | `frontend-vue/vue-composition-api` |
| Type-safe routes at the front | `frontend-wayfinder/wayfinder` |
| Basic configuration Vite | `frontend-vite/vite-module-loader` |
| Two Vite-builds (application + Filament) | `frontend-vite/vite-multi-build` |
| Frontend tests | `frontend-vue/vitest` |
| Code-style JS/TS | `frontend-linting/js-code-style` |

### DevOps

| Task | Skill |
|:---|:---|
| Docker dev vs prod (compose-diversity) | `devops/docker-dev-prod` |
| PHP-image for sale | `devops/docker-php` |
| PostgreSQL in Docker (+ test database) | `devops/docker-postgres` |
| Full service stack (queue, scheduler, reverb) | `devops/docker-services` |
| Vite dev server in Docker | `devops/docker-vite` |
| General containerization, image optimization | `devops/docker` |
| CI/CD pipeline (GitHub Actions) | `devops/ci-cd` |
| Branch strategy, PR-workflow, branch protection | `devops/gitops` |
| Makefile as entry point | `devops/makefile` |
| Node/pnpm on the host before hooks | `devops/node-pnpm-preflight` |

### Quality / Architect

| Task | Skill |
|:---|:---|
| Test strategy, pyramid, coverage policy | `quality/test-strategy` |
| Code review (process, checklist) | `quality/code-review` |
| Refactoring plan | `quality/refactoring-plan` |
| Technical debt audit | `quality/tech-debt-audit` |
| System architecture, ADR, C4 | `architect/architecture` |
| Stack selection | `architect/tech-stack-selection` |
| Design API | `architect/api-design` |
| Data Schema (DBMS agnostic) | `architect/data-schema` |
| Security: auth, OWASP, threat modeling | `architect/security-design` |
| Observability: logs, metrics, SLO | `architect/observability-design` |
| Design AI-agent | `architect/agent-design` |
| Eval LLM-pins | `architect/eval-design` |
| Regulatory (GDPR, AI Act) before launch | `architect/legal-compliance` |

### General / Roles

| Task | Skill |
|:---|:---|
| Commit, PR, message format | `general/git-commit-rules` |
| Edit `.ai/guidelines`, `boost.json` | `general/ai-context-workflow` |
| SSOT skills for several agents | `general/skills-ssot` |
| Decomposition of a complex problem | `general/complex-task-orchestrator` |
| Assigning a task to an agent | `general/task-brief-template` |
| End-to-end modification across multiple layers | `general/cross-layer-change-checklist` |
| Project map, areas of responsibility | `general/project-map` |
| Register of used packages | `general/packages-stack` |
| Ticket domain logic (design) | `general/ticket-workflow` |
| UserRole/Priority (project; new RBAC → `azguard/azguard`) | `general/user-roles` |
| Person: CTO / tech lead / maintainer / solo founder | `roles/*` |

### PM / Founder / Operator

| Task | Skill |
|:---|:---|
| BRD | `pm/brd` |
| PRD from BRD | `pm/prd-from-brd` |
| Requirements audit | `pm/requirement-critic` |
| Business process, FSM, diagrams | `pm/business-process` |
| Roadmap, MVP-phases | `pm/product-roadmap` |
| Monetization | `pm/monetization-design` |
| GTM-strategy | `pm/go-to-market` |
| Unit economics | `pm/unit-economics` |
| Rough idea → hypothesis | `founder/idea-discovery` |
| Competitor analysis | `founder/competitive-analysis` |
| New startup project (full cycle) | `founder/new-project` |
| Risks (RAID, pre-mortem) | `founder/risk-assessment` |
| Pitch deck | `founder/pitch-deck` |
| Product incident | `operator/incident-response` |
| Postmortem after SEV-1/2 | `operator/postmortem` |
| Runbook on alert | `operator/runbook` |
| On-call rotation | `operator/oncall-rotation` |
| Capacity planning | `operator/capacity-planning` |

### OSS / Python / Blender / Imported

| Task | Skill |
|:---|:---|
| OSS-repository: structure, README, ADR | `oss-dev/oss-development` |
| LICENSE, CoC, CONTRIBUTING | `oss-dev/oss-governance` |
| SemVer, CHANGELOG, release pipeline | `oss-dev/release-engineering` |
| DX: quick-start, ergonomics, CLI UX | `oss-dev/dx-design` |
| Dependency audit, SBOM | `oss-dev/dependency-audit` |
| Structure ML/DS-project | `python/ml-project-structure` |
| venv and dependencies Python | `python/venv-dependencies` |
| 3D-model via MCP Blender | `blender/mcp-blender-workflow` |
| Model specific rules | `blender/model-rules` |
| Thread for 3D-print | `blender/threading` |
| Traps Blender 5.0 API | `blender/version-gotchas` |
| Domain-wide tasks (marketing, sales, finance, legal, research…) | `imported/*` (by bucket name) |

## Model-routing pins task-commands

Each `/planner:*`-command pins `model`/`effort` in frontmatter `packages/planner/commands/*.md`,
interrupting session settings (SSOT-tier matrix - skill `general/plan-protocol` §9, here **not
duplicated**, and is justified per-command). Section captures **rationalized each pin + verdict
audit P3.1** — provenance to
not second-guess'resend pins. Optimization axis - **token-saving** (Opus dominates out:
8.1M vs Sonnet 5.4M — the most expensive lever). Axis downgrade — **only Opus → Sonnet 5**: Fable 5
more expensive Opus (out $50 = 2× Opus, up-tier for frontier-complexity) → has been excluded as a downgrade target.

**Pin rule (when editing `model`/`effort`):** update the line synchronously «Pinits X/Y» in `description`
of the same file (out of sync = defect) and run `skiller registry` (description goes to
`marketplace.json`, don't straighten it with your hands). Downgrade correctness-critical commands = bet on
quality in ALL ecosystem projects → **only with Owner-approval**, not for the price.

| Command | Pin (act.) | Rational | Verdict P3.1 |
|:--|:--|:--|:--|
| **design** | `opus/high` | Synthesis research-fanout → durable plan/ADR; cross-source reasoning, SSOT architecture (propagates to all projects). Bad design replicates ecosystem-wide. Fanout already Sonnet. | **keep-Opus** — correctness-critical, downgrade-risk HIGH, quality-no telemetry; Sonnet 5 (~93% Opus) — only *plausible* Owner-A/B, not blind downgrade |
| **dev** | `sonnet/high` | Opus-pin was a thin planning layer (vertical slicing + risk/blast-radius); impl-subagents have already Lean-tiered (Sonnet impl / Opus xhigh on HIGH-review / Haiku trivial). Planning = coding-agentic domain. | **downgrade-candidate → applied P3.2** (Owner-delegated): Sonnet 5 par/overtakes Opus on agentic (80.4 vs 74.6); bad cutting recoverable per-slice via review-gate → risk MODERATE |
| **make-workflow** | `sonnet/high` | Procedural circuit: matching 1/4 templates → slot-fill → static output reviewer (RED blocks). Low open-ended synthesis; The gate catches the cut mandatory stages. | **downgrade-candidate → applied P3.2** (Owner-delegated): «copy of the template + slots + checklist-gate», static reviewer - safety-net → risk LOW-MODERATE |
| **plan-design** | `opus/high` | Master Plan Authoring; heavy circuit/RAG-markers/DoR/pre-mortem; SSOT, the cheap model will perform WITHOUT chat. Bad plan → cheap-performers crash without chat. | **keep-Opus** — highest lever, Owner-blessed; downgrade-risk HIGH. Do not touch |
| **research** | `opus/high` | Multi-source retrieval + verification + synthesis with quotations; fanout Sonnet, Opus reduce/synthesizes. | **needs-Owner** — Sonnet 5 near-par, but fidelity quotes + cross-source reasoning — zone where Opus a little ahead. Possible A/B `sonnet/high` → **OQ-4** (Decision pending), low priority |
| **plan-audit** | `opus/xhigh` | Adversarial-closed phase audit; ~15 finding-types, no-op-detector, scope-drift, re-run Validation. | **keep-Opus/xhigh** — bug-finding = strongest zone Opus 4.8 («stronger real-bug finding»); under-audit misses defects quietly; xhigh acquitted. Don't touch |
| **review** | `sonnet/high` | Risk-scaled read-only review: quick for docs/small diff, standard usually, adversarial only by observed hard-risk boundary. | **downgrade applied** — default review no longer pays for registry-wide conformance and xhigh; a separate independent pass remains for security/data/concurrency/public-contract risk |

Audit facts (RAG:✅ 2026-07, canonical `claude-api` reference + `perplexity-web`): Sonnet 5 ≈93%
abilities Opus 4.8 when ~60% prices, outperforms by autonomous-agentic (80.4/74.6); Opus 4.8 leader
SWE-bench Pro (69.2/63.2) + SOTA bug-finding. **Limitation:** `analyst token-report --by phase`
not implemented (`token_report.py:38-41`) → ROI specific downgrade not quantified, priority
trial'ov **quality** (by downgrade-risk), not based on measured savings.
