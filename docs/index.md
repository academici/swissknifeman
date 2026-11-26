---
layout: home

hero:
  name: SwissKnifeMan
  text: Local, provider-neutral control layer for AI-assisted development
  tagline: Typed plans, a deterministic conductor for coding-agent CLIs, and a reproducible environment — on one machine
  actions:
    - theme: brand
      text: Start
      link: /getting-started
    - theme: alt
      text: How it works
      link: /overview
    - theme: alt
      text: Installation
      link: /skiller/guide/installation
    - theme: alt
      text: GitHub
      link: https://github.com/academici/swissknifeman

features:
  - icon: 🧰
    title: Everything in one place
    # counters «209/47» — landmark, manually maintained; check with `skiller registry`
    # (source of truth - skills.json / .claude-plugin/marketplace.json), should not be considered canon
    details: 209 skills in 47 buckets, permission presets, project profiles, adapters for IDE. One source of truth instead of copy-paste between projects.
  - icon: 🎯
    title: Contextual installation
    details: CLI swissknifeman itself determines the project type - Laravel, PHP-package, Obsidian vault — and connects a suitable set of skills. One team - and the project is ready to work with AI.
  - icon: 🔓
    title: Presets permissions
    details: Ready .claude/settings.json with maximum allowed access - git, composer, artisan, npm, docker. No endless permission-prompts in a new project.
  - icon: 🔄
    title: Upstream-sync
    details: External skills are tracked through upstream.json — weekly CI checks for source updates and opens PR with diff.
  - icon: 🗺️
    title: Plans and a conductor
    details: Plans are JSON (phases, items, checks, write sets); the orch conductor runs their items through narrow roles — scout, executor, reviewer, triager — with checks, review and resumable stops. See How it works.
  - icon: 🗄️
    title: Portable workspace
    details: The plans of all projects live in one git repository of their own, outside product history; a marker in each project names its store, and a migration moves existing plans without losing a write. See Portable workspace (workspace.md).
  - icon: 🧩
    title: Provider-neutral
    details: Skill is a folder with SKILL.md and snippets/. One format works in Claude Code, Cursor and Perplexity via adapters.
  - icon: 📦
    title: Provenance and validation
    details: skills.json stores the source, version and sha256 of each skill. validate.sh checks frontmatter, manifests and profiles locally and in CI.
---
