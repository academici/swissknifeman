---
id: D18
date: 2026-08-02
status: accepted
item: ''
items: []
supersedes: []
superseded_by: null
---
## Решение

v1 keeps compact English as the sole semantic source for canonical skills, commands, plugins, code comments and development documentation; localized human prose is a key-addressed sparse overlay with English fallback. Stable IDs, schema keys, literals, paths, commands and diagnostic codes are never translated. RAG:✅ 2026-08-02 locale fallback verification in `findings/06-p2-locale-authoring-verification-2026-08-02.md`; RAG:— (repo-grounded: `packages/skiller/scripts/check-translations.sh` and generated-artifact instruction).

## Почему

A complete second source would recreate semantic drift; immutable machine tokens keep parsers and provider adapters interoperable.
