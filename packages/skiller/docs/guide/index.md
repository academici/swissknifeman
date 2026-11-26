# What is SwissKnifeMan

**SwissKnifeMan** — universal personal registry AI-skills, snippets and configs.
Principle «Swiss knife»: everything you need for productive work AI-agent
in the project, lies in one place and is set with one command - skills, permissions,
profiles, adapters for different IDE.

> **Place in the ecosystem.** SwissKnifeMan — *capabilities layer* (skills + hooks). Shared memory and graph
> ecosystem holds hub **maind**, documentation - **brain**. Philosophy of interaction between three packages
> see in canon: [maind → Ecosystem](https://github.com/academici/maind/blob/main/docs/ecosystem.md).

## Why

When there are many projects and several agents (Claude Code, Cursor, Perplexity),
the same problems occur:

- skills and prompts are copied and pasted between projects and diverge;
- every new project starts with dozens permission-prompts;
- external developments (other people's skills with GitHub) become obsolete without notice;
- there is no single place where you can see what came from where and what version.

SwissKnifeMan solves this with one registry: **one source of truth → installation
to any project and any IDE → tracking external sources**.

## Basic principles

### 1. One source of truth

All skills live in this repository and are distributed across **bucket-am** — thematic
folders:

| Bucket | Skills | Topics |
|---|---|---|
| `architect` | 9 | architecture, API, data, security |
| `devops` | 6 | Docker, CI/CD, GitOps |
| `founder` | 5 | ideas, competitor analysis, pitches |
| `imported` | 12 | external super-skills (upstream-tracked) |
| `operator` | 5 | incidents, runbook, postmortem |
| `oss-dev` | 5 | open-source development + language references |
| `php` | 7 | Laravel, packages, tests, patterns |
| `pm` | 8 | BRD, PRD, roadmap, monetization |
| `quality` | 4 | code review, tests, technical debt |
| `roles` | 4 | persons: tech-lead, startup-cto, ... |

### 2. Provider-neutral format

Skill is a folder with `SKILL.md` (frontmatter + instructions) and `snippets/`.
Format is not tied to a specific agent: specifics IDE is placed in
delta-files `adapters/*.md` inside the skill. More details in
[Anatomy of a skill](./skill-anatomy).

### 3. Selective import from provenance

External skills are taken **selectively** — only what really fits, and not
entire repositories. Each external skill has `upstream.json` with source,
update strategy and sha256 — see [Upstream-sync](./upstream-sync).
The directory of candidate sources is maintained in `references/`.

### 4. Contextual installation

`skiller vendor` determines the target project type by markers (`artisan`,
`composer.json`, `.obsidian/`) and puts the appropriate set bucket-ov - see.
[Profiles](./profiles). Same logic
[`apply-permissions.sh`](/harness/configs/claude-permissions) selects presets
permissions.

### 5. Everything is checked

`scripts/validate.sh` validates frontmatter, `upstream.json`, profiles and
manifests - locally and in CI. Registry `skills.json` stores sha256 and provenance
of each file.

### 6. Compatible kernel (conflict policy)

The registry is **core of mutually compatible skills**: everything that lies in it is not
conflict with each other. This is the main invariant: the project can be vendored by anyone
subset and be sure that the rules do not contradict.

When an external source with their skills is encountered (Laravel Boost, alien
repository) — we are checking it **in pairs** against the kernel and solve:

- **Necessary, complementary, does not conflict, version-stable, not Blade-linked** →
  put into the kernel with `upstream.json` (source fixed, provenance visible).
  First, the skill gets into the registry, and only then is it added to projects.
- **Version-specific, requires render-source context or conflicts** →
  **do not pull into the core**, there is a trust policy: we give the topic to the source, the core
  is just complementary. Rule conflicts are resolved by priority: **project > external
  source > registry**.

**Inversion of update flow.** Generic-external source skills are being updated
**first in the registry** (`./scripts/update-upstreams.sh --check` catches drift
upstream), and from the registry they are pulled into projects. So all projects have one thing
common non-conflicting kernel, not N divergent copies.

Policy Use Cases (from audit Boost × agelto, 2026-06-13):

| Situation | Solution |
|---|---|
| `code-style-spatie` (not-`final` default) ↔ project requires `final` | conflict → do not vendor into such a project |
| `devops/node-pnpm-preflight` (pnpm) ↔ project on yarn | conflict → do not vendor |
| `enum-attributes` (metadata enum) ≠ `laravel-attributes` (Eloquent `Attribute::make()`) | various topics → do not confuse, do not pass one off as another |
| Boost `pennant-development` (static `.md`, stable API) | extract to kernel with upstream.json |
| Boost `folio`/`volt`/`mcp` (`.blade.php` with <code v-pre>{{ $assist-&gt;… }}</code>) | render-context Boost → leave behind Boost |

Full trust matrix Boost — [boost-compatibility.md](../boost-compatibility),
source card - `references/laravel-boost.md`.

## Use Cases

The package is tailored for five working scenarios:

1. **Documentation** — writing and maintaining technical documentation
2. **Obsidian vault** — knowledge management, notes, knowledge bases
3. **Technical specifications** — preparation of technical specifications (BRD → PRD → architecture)
4. **PHP-packages** — development open-source packages, first Laravel
5. **Large Laravel-projects** — architecture, patterns, DevOps, quality

## Repository structure

```
skills/             # skill = folder + SKILL.md + snippets/ (+ upstream.json for external)
profiles/           # project type → set bucket-ov
configs/            # ready-made configs: presets permissions for Claude Code
references/         # directory of external sources (what to take, status)
adapters/           # integration docs: claude-code, cursor, perplexity
scripts/            # validate, update-upstreams, scanner, apply-permissions
generate-skill/     # meta-skill for creating new skills
skills.json         # registry (is generated skiller registry, with provenance)
bin/skiller   # CLI: connect, vendor, update, status, registry
install.sh          # installation CLI symlink to ~/.local/bin
docs/               # this documentation (VitePress)
```

## Where to start

1. [Install skills into the project](./installation) — one command with auto-detection
2. [Tighten up presets permissions](/harness/configs/claude-permissions) — so that the agent works without prompts
3. [View examples](../examples/laravel) — typical scenarios inside and out
