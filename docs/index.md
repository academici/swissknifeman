---
layout: home

hero:
  name: SwissKnifeMan
  text: Swiss knife for working with AI-agents
  tagline: One registry of skills, configs and permissions - installation in any project and any IDE per command
  actions:
    - theme: brand
      text: Start
      link: /getting-started
    - theme: alt
      text: Installation
      link: /skiller/guide/installation
    - theme: alt
      text: GitHub
      link: https://github.com/academici/swissknifeman

features:
  - icon: 🧰
    title: Everything in one place
    # counters «195/45» — landmark, manually maintained; check with `skiller registry`
    # (source of truth - skills.json / .claude-plugin/marketplace.json), should not be considered canon
    details: 195 45 skills bucket-ah, presets permissions, project profiles, adapters for IDE. One source of truth instead of copy-paste between projects.
  - icon: 🎯
    title: Contextual installation
    details: CLI swissknifeman itself determines the project type - Laravel, PHP-package, Obsidian vault — and connects a suitable set of skills. One team - and the project is ready to work with AI.
  - icon: 🔓
    title: Presets permissions
    details: Ready .claude/settings.json with maximum allowed access - git, composer, artisan, npm, docker. No endless permission-prompts in a new project.
  - icon: 🔄
    title: Upstream-sync
    details: External skills are tracked through upstream.json — weekly CI checks for source updates and opens PR with diff.
  - icon: 🧩
    title: Provider-neutral
    details: Skill is a folder with SKILL.md and snippets/. One format works in Claude Code, Cursor and Perplexity via adapters.
  - icon: 📦
    title: Provenance and validation
    details: skills.json stores the source, version and sha256 of each skill. validate.sh checks frontmatter, manifests and profiles locally and in CI.
---
