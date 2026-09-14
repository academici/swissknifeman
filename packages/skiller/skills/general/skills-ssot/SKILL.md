---
name: skills-ssot
bucket: general
version: 0.3.0
description: "Resolve duplicate or drifting skill delivery by inspecting each source, generator, and provider owner."
when_to_use: "Use when skills drift between agent tools."
risk: write
persona: oss-dev
tags: [ai-context, skills, ssot, workflow, conventions, ai]
requires: []
produces_for: []
outputs: []
snippets: ["gitignore-ai.txt", "symlink-sync.sh", "boost-json.example", "skills-lock.example.json"]
adapters: [claude, cursor, fable]
sha256: ""
---

# Skills: One Source per Identity

Use when skill copies drift, discovery has duplicates, or generation ownership is unclear.
SSOT means one semantic owner per capability; it does not mandate `.ai/`, symlinks, Boost,
ignored agent files, or a particular distribution channel in every repository.

## Discover ownership first

Read project instructions, generation markers, config/locks, selected plugin manifests, and
actual provider paths. For each identity record its source, publisher, output, selection, and
local modifications. Distinguish project-local authoring, managed vendored skills, native
plugins, user skills, and provider-generated adapters. Matching names alone do not justify
removing a local skill; compare meaning and preserve unowned edits.

In Swissknifeman, registry skills are authored under `packages/skiller/skills/`; registry and
provider projections are generated. Consumer projects may select native plugins or managed
copies. Use their existing `.swissknife.json` / `.swissknifeman/config.json` and the owning
worktree-local Skiller CLI; inspect its help for the operation. Do not mix both delivery
channels for the same identity or change the chosen channel by accidental cleanup.

## Edit and regenerate

1. Change the owning semantic source, not a generated projection. A handwritten `AGENTS.md`
   is a valid source when the project owns it directly; generation markers define managed
   blocks. Preserve handwritten sections when a file has mixed ownership.
2. Run the established generator for the affected output. Laravel Boost's presence alone
   does not give it ownership of every `AGENTS.md`, skill, setting, or hub. Verify installed
   commands, configuration, and package documentation before prescribing `boost:update`.
3. Keep generators from overwriting each other's output. Put integrations into source-owned
   extension points or compose through the existing pipeline.
4. Check generated drift, links, selected identities, and actual provider discovery. Filesystem
   presence is not proof a running session loaded the new rules.
5. Commit/ignore according to project policy. Many repositories intentionally commit generated
   manifests or bootstrap files. Never mass-untrack `AGENTS.md` or provider settings merely
   because a sample `.gitignore` lists them.

Prefer one version-appropriate delivery for overlapping framework guidance. In a Boost
project, compare its selected framework guidance with Skiller's fallback before disabling a
copy; retain unique domain and safety requirements. A general skill catalog should not be
repeated in a resident hub when native discovery already provides it.

## Narrow references

[Source layouts](references/ssot-source-layout.md) shows optional compositions.
[Scenarios](references/ssot-scenarios.md) routes related tasks.
[Gitignore example](snippets/gitignore-ai.txt), [symlink publisher](snippets/symlink-sync.sh),
[Boost example](snippets/boost-json.example), and [vendor lock](snippets/skills-lock.example.json)
are examples to inspect, not commands/configuration to apply blindly. The symlink example is
only for projects that explicitly choose `.ai/skills` as its source and those target roots.
