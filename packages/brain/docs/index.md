---
layout: home

hero:
  name: brain
  text: The Obsidian vault module
  tagline: Find the vault of the machine and the folder of a project, sync documents, and write a note when a plan is closed
  actions:
    - theme: brand
      text: Guide
      link: ./guide/
    - theme: alt
      text: Command reference
      link: ./reference/cli

features:
  - title: Vault lookup
    details: One ladder finds the vault - the machine configuration first, then the deprecated sources. A path that is set but missing is an error, never a silent fallback.
  - title: Document sync
    details: Pull vault documents into a project or push project documents into the vault by glob patterns. Nothing is ever deleted, and a changed vault file is not overwritten without --force.
  - title: Notes from events
    details: The subscriber brain:plan-notes writes one note per closed plan and is idempotent by event id, so a repeated delivery never creates a duplicate.
  - title: Safe by design
    details: The vault belongs to a person. brain writes only a new note or a document you push on purpose; it never removes or overwrites a file of yours.
---

## What is in the module

`brain` is a small command-line tool on the `aicore` foundation (Python 3.9+, standard library only). It has the
commands `vault`, `project`, `docs`, `note`, `doctor` and `version`, the `[brain]` configuration table, the Claude Code
plugin `brain` with the skill `brain-locator`, and one subscription (`brain:plan-notes`).

## What is not in it yet

- The external vault tooling (its own command line, the documents watcher) is not part of this module.
- The event `planner.plan.closed` has no emitter yet: the subscriber is ready and checked against contract fixtures,
  and notes appear when the planner starts to emit the event.
- `maind` keeps its own vault lookup for now; the two will be merged in a later phase.
- The legacy `memory_brain` object of `.swissknife.json` is still read, with a deprecation warning.

## Skills

The module plugin ships `brain-locator`. The sources live in `packages/brain/skills/` and are released with the module.
A project receives them through the host-provided `system` bucket of `skiller`: `skiller connect` enables the plugin
`brain`, and `skiller sync` copies the skills into the project. The `skiller` guide
"Configuration, host buckets and metadata" describes the bucket.
