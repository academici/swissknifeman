# Target architecture synthesis

The canonical project configuration expresses user intent only: selected capabilities,
locale policy, safety policy and explicitly declared local overrides. It does not store
provider caches, generated content or provider observations.

The resolver computes an immutable desired snapshot. Claude Code and Codex adapters each
observe only their own state, render their own projection, reconcile only assets they own,
and write adapter-scoped status. No adapter may alter the other's files or mutate canonical
intent during a reconcile pass.

Locale surfaces are `response`, `plan`, and `diagnostics`. Each resolves from
command/session → environment → project → user → `en`. English is complete canonical
authoring; Russian is a rendering overlay. Structural IDs, schemas and machine literals
remain language-neutral. The resolved locale and fallback path are observable.

Legacy same-name skills are classified as canonical-equivalent, local override, stale
managed copy, broken link or ambiguous. Only equivalent assets are auto-relinked; other
state is preserved and reported.

Sources: `findings/01-rag-locale-2026-08-02.md`,
`findings/02-rag-control-plane-2026-08-02.md`,
`findings/03-current-defects-2026-08-02.md`.

