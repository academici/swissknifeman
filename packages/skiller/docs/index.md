---
title: Skills (skiller)
---

# Skills - package `skiller`

`skiller` — registry AI-ecosystem skills: one source of truth for portable skills
and their distribution to projects (Claude Code / Cursor) two channels (connect/vendor).

- [What is SwissKnifeMan](./guide/) — overview and principles
- [Installing skills](./guide/installation) · [Vendor-mode](./guide/vendor-mode)
- [CLI swissknifeman](./guide/cli) · [Profiles and auto-detection](./guide/profiles)
- [Creating skills](./guide/creating-skills) · [Registry skills.json](./guide/registry)
- [Bucket-audit 2026-07](./guide/bucket-audit-2026-07) — metrics/verdicts across the entire registry (P7.2)
- [Adapters IDE](./adapters/claude-code) · [Examples](./examples/laravel)
- [Compatible with Laravel Boost](./boost-compatibility) · [Local distribution `.ai/` to providers (dev-plan)](./multi-provider-distribution)

> Setting up the environment Claude Code (permissions/MCP/hooks) — in the package
> [harness](/harness/). Memory and Ecosystem Graph - package maind.

## Development clone guard

In a development clone of the repository (an untracked `.swissknifeman-dev` marker in the root) `bin/skiller`
refuses to run against the real `HOME`: exit code 3 and a `SKM_DEV_GUARD` line in stderr. Use a throwaway
environment (`scripts/dev-sandbox.sh` in the repository root) or `SKM_DEV_ALLOW_LIVE=1` as a conscious
exception. Installed copies and checkouts without the marker are unaffected. See `docs/develop.md`
("Ecosystem split branch").
