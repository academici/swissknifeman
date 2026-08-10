# P6 productization recon — 2026-08-03

## Scope and evidence boundary

This pass designs P6 only. P0–P5 remain unexecuted, so no candidate, P4 assurance manifest or P5
GO/NO-GO exists. No package, router, installer, roadmap, docs, generated artifact, provider, fleet
or release state was changed. Product-home outcomes below are predicates for future measured
evidence, not a present recommendation.

## Repository ownership facts

- Root instructions keep `task` plugin-only with no standalone CLI and prohibit a root `task`
  group. Its live code owns plan lint/journal/task-contract/route evidence and provider-rendered
  intent commands, not a durable provider-process supervisor. RAG:— (repo-grounded:
  `packages/task/AGENTS.md`, `packages/task/lib/task/`, `packages/task/commands/`).
- Harness owns project environment configuration and currently exposes provider permissions,
  hooks, instructions, agent packs and a live `run` surface. Its package guide requires explicit
  targets, stdlib-only runtime and thin CLI dispatch. This makes it a legal home only if terminal
  candidate evidence shows no independent transition/state/acceptance owner beyond live Harness.
  RAG:— (repo-grounded: `packages/harness/AGENTS.md`, `lib/harness/cli.py`, `lib/harness/run/`).
- The umbrella router delegates to package launchers. The supplied root canon does not authorize a
  new `artifex` group, and the umbrella installer currently installs only existing standalone CLI
  packages while intentionally excluding plugin-only Task. Package approval and root-router
  approval therefore cannot be inferred from one another. RAG:— (repo-grounded: root AGENTS
  instructions, `bin/swissknifeman`, `install.sh`).
- `core/` is for primitives with real shared consumers, not a staging home. The plan-local
  candidate is one consumer until terminal integration proves another. RAG:— (repo-grounded:
  root shared-core canon and `research/05-package-boundary-and-rollout.md`).
- Generated marketplaces, provider projections, locks and documentation snapshots are changed
  through their owning generators and later checked with `skiller registry --check`; P6 must list
  those generators before integration. RAG:— (repo-grounded: package-architecture skill and
  `packages/skiller/bin/skiller registry --help`).

## Closed home predicates

| P5/ownership evidence | Legal outcome | Authority |
|:--|:--|:--|
| exact NO-GO | `roadmap-only` | existing D19; no product surface |
| GO and only plan compilation/lifecycle remains | `task-extension` | package guide; Task stays plugin-only |
| GO and all durable decisions/state already belong to live Harness; delta is launch/environment | `harness-extension` | package guide; no second scheduler |
| GO and candidate retains store+scheduler+authority+worker lifecycle | `artifex-package` | exact Owner D# for sixth package |
| any branch requests umbrella command | same home plus `root_router=approved` | separate explicit Owner D# clause |

An ambiguous responsibility map is not resolved by line count, file names or preference. It is an
Owner stop. A failed integration cannot silently switch to another branch.

## Preflight integrity observation

`pwd`, `git status --short`, `codex doctor --json`, `maind health --cwd` and plan lint were run.
Codex doctor and mAInd round-trip are green; initial plan lint was 0 ERROR / 0 WARN. The plan is
untracked inside an already dirty tree, so a HEAD baseline cannot attribute its diff. The exact
absolute-target hook dry-run exits 0 but remains non-green: `Статус: warning` with
`harness.codex.lifecycle.hooks` and `.handler` both `stale-source → update (source-changed)`.
P6 does not repair or waive this foreign environment defect; terminal P4/P5/P6 assurance must keep
it fail-closed until separately repaired and revalidated.

## External fact classes and verification status

P6 adds no new library/API/market/service claim. Its load-bearing decisions depend on repository
ownership canons and future terminal P5/P6 evidence. Current provider accounting and permission
facts remain pinned to P3/P5 findings and must be revalidated by those execution-time probes; P6
does not refresh them or substitute documentation for measured terminal artifacts.

## Проверка (verification status)

- RAG: no new external query; repository/package/CLI/generator sources read directly, mAInd memory
  recalled only as an untrusted pointer and not used as verdict authority.
- Непроверено → ПОВТОРНЫЙ ПРОХОД: terminal P5 verdict, candidate responsibility map, exact selected
  package files, Owner D#, compatibility/rollback results and cold audit are execution-time evidence.
- Обходки/[POSSIBLE-DEFECT]: none accepted; hook `stale-source` remains a named non-green gate.
