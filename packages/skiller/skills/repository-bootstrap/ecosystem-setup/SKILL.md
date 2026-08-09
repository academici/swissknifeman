---
name: ecosystem-setup
bucket: repository-bootstrap
version: 0.1.0
description: "How to configure/reconfigure THIS academici ecosystem project - decision tree for skills, plugins, memory, namespaces, environment, graph. Use to connect/change skills or plugins, change memory/namespaces, add a role, or diagnose the connection. Pick the OPTIMAL set; ask when unclear."
risk: draft
persona: oss-dev
tags: [ecosystem, setup, maind, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Setting up project `swissknifeman` (academici node)

This project is a node of the **academici** ecosystem, connected to the **mAInd** hub. For
swissknifeman as a self-host repo, this file's canonical source is root-bootstrap
`packages/skiller/skills/repository-bootstrap/ecosystem-setup/SKILL.ru.md` (edit there,
regenerate `skiller registry`, P1.2/D31); the onboarding template
`packages/maind/templates/skills/ecosystem-setup/SKILL.md` is the same content for OTHER
ecosystem projects (`maind onboard`/`maind sync`) — do not conflate the two sources.

**Project state:** type `standalone` · scope `project:swissknifeman` · namespaces `axioma`.

## Main rules (do not violate)

1. **Optimal, not maximal.** Pick the skill/plugin set for the project's stack and role. Don't
   include unrelated roles (`php`/`python`/`mobile` on a frontend, frontend on a backend
   package) — that's noise.
2. **Unclear → ask.** If the optimal set is unclear (hybrid stack, contested buckets) — ask the
   user (2-3 curated options), don't guess and don't install "just in case".
3. **Always ask the skills channel** (connect vs vendor) — it changes what gets committed to the
   repo.

## Decision tree (question → options → action)

**Project type** (`standalone`) sets the base skill profile. If the type is `standalone` — it's
**unrecognized**: don't install everything, pick a profile explicitly (`node-frontend`,
`laravel-project`, `php-package`, `python-backend`, …) or ask.

| Decision | Options | Action |
|:--|:--|:--|
| **Memory** | maind / native / off | `maind onboard swissknifeman --memory <…>` (default maind) |
| **Namespaces** | shared (group) + personal (isolation) + `*` (infra) | `--namespace a,b`; shared memory within a namespace, isolated across |
| **Skills channel** | connect (bucket, not in repo) / vendor (skills in repo + lock) | ask; `skiller connect` or `.swissknifeman/config.json` + `skiller sync` |
| **Role buckets** | by type profile; CORE always | not "everything"; ask when unclear |
| **Environment** | permissions / MCP / auto-approve / brain | delegated to `harness` |
| **Code graph** | Serena on/off | `--with-code` |

## Common tasks

- **Add a role/skills** → ask the channel; connect: `skiller connect --plugins <current>,<new>`;
  vendor: append to `.swissknifeman/config.json` → `skiller sync`.
- **Change the plugin set** → edit `enabledPlugins` in `.claude/settings.local.json` (keep only
  what's relevant to the stack), or `skiller connect --plugins …` (overwrites).
- **Change memory/namespaces** → `maind onboard swissknifeman --memory … --namespace …`.
- **Re-roll artifacts** → `maind sync --project swissknifeman` (or `--only mcp,graph,…`).
- **Check the connection** → `maind health` (round-trip gate), `skiller status`, `maind doctor`.
- **Check the always-on budget** (before adding a skill/agent/CLAUDE.md block/MCP server) →
  `skiller budget --first-turn` (per-project, target ≤7K/warn >10K); fleet — `maind doctor
  --context`; per-session trend — `analyst sessions`.

Full tree of every setup layer — maind doc "Decision tree: project setup"
(`packages/maind/docs/guide/onboarding-decision-tree.md`).

## Project links

- namespaces: `axioma` · scope: `project:swissknifeman` · linked to: —.
- current links: `maind graph --project swissknifeman`.

## Provenance (root-bootstrap, P1.2)

Class-A private/source-only root-bootstrap identity (D31/D38, `plans/2026.07.24-AGENT-RELIABILITY`):
canonical source is this file's `SKILL.ru.md`; thin projections —
`.claude/skills/ecosystem-setup/SKILL.md` and `.agents/skills/ecosystem-setup/SKILL.md` (generated
by `skiller registry`, never hand-edited). Bucket `repository-bootstrap` is private/source-only:
never published as an ordinary unit/core/marketplace entry, never vendored/connected into a
consumer project.
