# Roadmap

Implemented 2026-10-04: Task executor/reviewer separation with optional reviewer selection,
digest-bound owner-review packets, bounded transport/review rounds and invariant-model checks.
See [Task tooling](task/reference/plan-tooling.md#independent-review-transport).

## Roadmap audit — 2026-10-04

All twelve dated local roadmap records were checked against code and regression evidence,
not their prose status alone. Earlier fixes were retained; remaining runtime defects were repaired
in the working tree. This is source qualification, not a release or consumer rollout.

| Record (`2026-10-04-*.md`) | Previously implemented | Audit result / additional work |
|:--|:--|:--|
| `executor-reviewer-coupling` | Separate executor/reviewer, bound packets and completed-round budget | Verified; no extra incomplete-attempt budget or silent reviewer substitution |
| `optional-reviewer-all-task-commands` | Only partly reflected in execution defaults | Reviewer optional; explicit review/audit inherits actual captured native route; cancellation is not GREEN |
| `committed-predecessor-review` | Immutable first-closure proof | Verified and extended with small source blobs and additive legacy source recovery |
| `review-candidate-tracking-state` | Inventory-based freshness | Verified; staging/commit presentation remains non-material; product/input/dependency changes still invalidate |
| `plan-run-owner-invocation-normalization` | Shared parser and exact workset/route matching | Verified; original invocation and full-group suffix behavior retained |
| `plan-run-reviewer-native-transport` | Native ACP for explicitly sized context | All new automatic Grok reviews now use native ACP; concrete Files expansion and route proof preserved |
| `long-running-review-liveness` | Selected-session activity, heartbeat and native usage accounting | Verified; no-context routes also receive inactivity-only monitoring; old headless archives remain readable |
| `declared-phase-execution-order` | Declared chain, predecessor edges and frontier ordering | Verified by existing order regressions; no replacement numerical heuristic introduced |
| `plan-run-future-read-budget` | No selected-workset lint scope | Added selected-item + recursive producer scope; future bundle/budget failures visible but non-gating; full/fleet lint unchanged |
| `plan-close-only-whole-plan` | Public phase/item close and phase lifecycle still existed | Whole-plan-only admission, checked acceptance, idempotent plan closure, legacy-history compatibility and safe successor reconciliation |
| `azguard-plan-run-diagnostics` | Several owning fixes already committed | Remaining source issues above repaired; no product execution or edits in the consumer repository |
| `codex-plan-run-reviewer-session-audit` | Diagnosis and earlier route/freshness fixes | Added exclusive candidate/attempt validation DAG, native read ledger, source witnesses, compact results/provenance and machine terminal reconciliation; comparative live efficiency/quality eval remains unmeasured |

Qualification includes the Task suite (1,403 tests, one existing skip), generated-command parity
and canonical registry checks. Local logs: `/tmp/skm-roadmap-final-validation.log`,
`/tmp/skm-roadmap-registry-check.log`, and `/tmp/skm-roadmap-real-p43-proof.log`.
The original AzGuard P4.3 closure `554126502890563c02a3ef9b5a19fd71982c3cd0` was also exercised
in an isolated Git snapshot: two additive Gate/Response witnesses restored historical proof after
live vendor deletion without changing the original packet, receipt or journal. That closure has no
immutable `composer.lock`; its recovery explicitly reports `original-lock-not-bound` and invents no
package version. New packets bind archived lock/package identity when Composer sources are used.

Remaining field work: install/release the qualified source when requested, apply source recovery
to consumer plans explicitly, and run matched live review/executor quality and latency comparisons.
Unit regressions, isolated historical proof and coverage ranges are not evidence of model understanding
or measured token/time savings. No consumer rollout, hosted CI, push, commit or release was performed.

Directions only; order within a block is rough priority. Work starts on measured need, not in anticipation of it.

## Near term

- **Session efficiency.** Accumulated tool results, not the resident skill set, dominate Codex session growth; duplicate skill names exist in the umbrella and in Vaulter. Next: safe pilots that trim tool-result carry-over and remove the duplicates.
- **Task: structural headings are English, localized names never block.** Task 0.26.2 rejected a plan whose names were Russian: Routing `Почему` (≠ `Why`), Meta `Поле | Значение`, `Title` prefix `План №1`, decision bodies `## Решение/Почему/Последствия` (≠ `## Solution/Why`), Phase Handoff tables. Task 0.24.3 had accepted them, so P10 ran and P05 then stopped before any write (`BATCH_AMBIGUOUS` → routing → `PLAN_DESIGN_GATE_BLOCKED`). Worse, the one-cell fix changes the design fingerprint, so a plan with `Design Audit: required` also needs a repeated whole-plan audit. Rule: templates, scaffolds and `plan-design` always emit English headings (content stays in the plan language). Next: parse headings through an alias map (`Почему`→`Why`, …) or warn-and-normalize in `plan-lint`/`task_contract`/`plan_decisions`, keep localized headings out of the design fingerprint (or normalize before hashing), and never make an alias mismatch a stop reason. A `plan-lint --fix-headings` migration should cover existing plans. Also: `plan-work.py` needs an absolute `--plan-dir` (a relative `.` gives an empty plan name), and the cached `task/<ver>` copy lacks sibling `core/` (`ModuleNotFoundError: core.provider`).
- **Provider parity.** Plugin/skill reconcile plus Cursor/Grok field residue after the provider-aware `budget`/`doctor` work. Grok is a managed provider (Codex-shaped hooks/MCP TOML, Cursor-shaped skill discovery); fleet health still requires only Claude/Codex/Cursor.
- **Own skills migration.** Analyze local projects listed in `.skills-scanner.json`, move the universal part into the registry (via the [scanner](/skiller/guide/scanner) or by hand), connect it back with `skiller connect` / `skiller vendor`, delete local copies.
- **Vendor skills in packages.** Apply the [publication mechanism](/skiller/guide/vendor-skills) in own open-source packages: `resources/skills/` + ServiceProvider publication + a full-cycle test (`composer install → vendor:publish → agent sees the skill`).
- **`configs/` content.** Preconfigured subagents (`.claude/agents/`), hooks (auto-format, pre-commit validation), other IDE configs — see the [configs overview](/harness/configs/). Verified `.mcp.json` presets already ship (`context7` + a curated subset), see [Integrations](/harness/integrations/).

## Strategic

- **Cross-project optimizer** — the read-only overview ships as `system/cross-project-coordinator` plus the `code-coordinator` agent. Next: turn findings into action (auto-extraction to a shared package, PRs to target projects) and write cross-project facts to shared memory.
- **Skills Marketplace UI** — web UI over the registry: tag search, snippet preview, "Install to project". Minimum: VitePress + GitHub API.
- **Skill Composition** — `extends: laravel` in frontmatter: the agent loads the parent context first.
- **Versioned Snapshots** — SemVer tags on the repository and a version pin in `skiller vendor` (`swissknifeman@1.2.0`); sha256 in the registry already exists.
- **Skill Chains** — the `requires` / `produces_for` graph already exists in frontmatter; visualize it as a DAG and run a chain in one call.

## Technical

- **Snippet auto-scoring** — GitHub Action runs phpcs/phpstan/hadolint on new snippets and writes a score to `index.json`; candidates below threshold are blocked.
- **Obsidian plugin** — `skills.json` in the sidebar, open SKILL.md, insert a snippet with `/skill`.
- **MCP server for skills** — `get_skill(name)`, `list_skills(bucket)`, `search_snippets(query)` instead of file reads.
- **Quality badges** — generated per-skill badges: `snippets: 5`, `used_in: 3 projects`, `last_tested: <date>`.

## Experimental

- **LLM gap analysis** — a monthly agent reads PRs/issues of working projects, finds patterns no skill covers, drafts new SKILL.md files.
- **Snippet leaderboard** — track which snippets are copied into projects and how stable they stay.
- **Skill health monitor** — scheduled Action checks that snippets compile/lint on current PHP, Node and Docker versions.
