---
name: shared-memory
bucket: system
version: 0.4.0
description: "Use when prior project decisions or a current handoff may change the work. Canon = MODE=manual: private project scope by default, shared namespaces only by explicit scope, no SessionStart digest."
risk: write
persona: architect
tags: [memory, cross-project, topology, recall, context, coordination]
requires: [local-topology]
produces_for: []
outputs: []
snippets: []
adapters: [claude]
sha256: ""
---

# Shared Memory (constellation shared brain)

Hook `~/.claude/hooks/memory/` = shared brain for one group (`brain`) only. Structure like `auto-approve`: switch `memory.sh`, mode in `env.ini` (`MODE`), groups/members in `config.json`, backends in `modes/`. Member resolution via topology (`local-topology`).

## When to use

- **Recall when prior state can change the work** — active handoff, a known decision, or an
  explicitly cross-project task; skip routine isolated edits:
  ```bash
  ~/.claude/hooks/memory/memory.sh recall "<task topic: domain, pattern, bug>"
  ```
- **Remember after** — record a cross-project-useful fact (decision, divergence, shared-package candidate):
  ```bash
  ~/.claude/hooks/memory/memory.sh remember --type project "<fact in one phrase + why>"
  ```
- **Inspect:** `memory.sh status` (mode, group, members, fact count), `memory.sh members` (who's in group).

Only what's useful to **another** project in the group (dups, divergent impls, shared decisions, shared-package candidates). Local/one-off → skip.

## Modes (backends) — `env.ini` MODE

- **manual** ← **canon for application projects.** mAInd memory stays available through MCP/CLI;
  project recall is private and no digest is injected at SessionStart. Shared scopes require an
  explicit `scope=ns:<name>` and separate `memory_namespaces` permission.
- **maind** — explicit legacy auto-context mode: same daemon plus SessionStart digest.
- **file** — one shared store per group (markdown).
- **federation** — file-based: per-member `memory/` + shared store. Git-transparent, no daemon. For **infra nodes** (brain/swissknifeman) only; NOT the same as maind graph-federation.
- **agentmemory** — old direct daemon proxy (bypassed API/scope) — **do not use**, replaced by `maind`.
- **off** — disabled.

> ⚠️ Write/read project memory only via `maind memory` or MCP `maind_memory_*` — bypass writes
> lack the scope marker and aren't found by scoped recall.

## Groups & members (membership)

- **MODE=manual/maind:** graph membership uses `projects[].namespaces`; permission to address a
  shared memory scope uses `projects[].memory_namespaces`. Ordinary recall remains project-only.
- **MODE=file/federation (infra):** `brains` → `{ name: { members, store, agentmemory } }`; member sees a brain only if in its `members`.

## Per-project override (like auto-approve)

Global: `~/.claude/hooks/memory/env.ini` (MODE) + `config.json`. In project: `<project>/.claude/memory.env.ini` (MODE) and `<project>/.claude/memory.config.json` (group/members); plus `memory_brain` in `<project>/.swissknife.json` — project's default group.

## SessionStart auto-load (digest) & native-vs-maind routing

`MODE=manual` removes the digest hook and disables native auto-memory. `MODE=maind` is an explicit
opt-in to SessionStart digest. Per-project: `maind onboard <id> --memory manual|maind|native|off`
(default `manual`).

**Routing rule — one fact in one store, no dups:**
- **maind** (`maind memory` / `maind_memory_*`) — private project memory by default; shared scope
  only when explicit. Use `key=active-handoff` for continuity; it replaces the previous slot.
- **native MEMORY.md** — off when `MODE=manual|maind`. If `--memory native`: only small
  always-handy invariants, **no copies** of maind facts.
- **file-federation (`MODE=file/federation`)** — legacy, infra nodes only (brain/swissknifeman).

## Discipline

- Recall only when the task benefits from prior state; remember only durable decisions or one
  current `active-handoff`. Keep progress/checkpoint journals in the repository.
- Fact = one phrase + **why**.
- **Don't duplicate** a fact across native and maind — one store per routing rule above.
- The `active-handoff` slot replaces only the previous slot in the same project scope. No secrets.

## Quality checklist

- [ ] Recall was used only when prior state could change the task.
- [ ] Only cross-project-useful fact recorded (not local trivia), with "why".
- [ ] Fact in correct scope (private by default; `--share`/shared only if useful to home).
- [ ] Project uses `MODE=manual`; `maind health` is green, and `--deep` is reserved for diagnosis.

## Links

- `~/.claude/hooks/memory/` — the hook (`memory.sh`, `env.ini`, `config.json`, `modes/`, `CREDITS.md`).
- `local-topology` (system bucket) — member resolution via `maind topology show --json`.
- `cross-project-coordinator` (system bucket) — source of cross-project findings (dups/divergences/shared-package candidates) worth `remember` for the group.
- `general/session-handoff` — adjacent: one-off context handoff between sessions, vs shared-memory = persistent shared group store.
- Install hook files: `harness hooks --global` (harness package).
