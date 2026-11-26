---
name: vueuse-functions
bucket: frontend-vue
version: 1.1.0
description: "Select a VueUse composable for an applicable Vue/Nuxt task when VueUse is available."
when_to_use: "Use for an existing VueUse API or a requirement likely covered by an installed composable."
license: MIT
metadata:
    author: SerKo <https://github.com/serkodev>
    version: "1.0"
compatibility: Requires Vue 3 (or above) or Nuxt 3 (or above) project
risk: write
persona: oss-dev
tags: [vue, nuxt, vueuse, composables]
requires: []
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# VueUse Functions

Use for an existing VueUse call or an applicable requirement in a Vue/Nuxt project with VueUse
available. Do not load the catalog for every Vue edit, replace adequate native Vue code, or
install a dependency simply to follow this skill.

1. Check installed package/version and the project's conventions, including SSR/browser scope.
2. Search the [function catalog](references/catalog.md) for the requirement or function name.
   Read only the matching function reference, linked from that catalog, for usage and types.
3. Preserve the catalog's invocation boundary: `AUTO` means applicable within authorized
   scope; `EXTERNAL` needs the external dependency already installed; `EXPLICIT_ONLY` needs
   an explicit user request. A dependency proposal is separate from permission to install it.
4. Confirm the API against installed types/source or versioned primary docs. This catalog is
   a recorded snapshot, not a claim about the newest VueUse release.
5. Validate relevant lifecycle cleanup, reactivity, SSR, permissions, and external effects.
   Report checks actually run; use the existing project test strategy.

The entry is a local navigator derived from the recorded upstream. The full catalog and all
per-function reference files remain available on demand; provenance and transformation notes
are recorded in `upstream.json`.
