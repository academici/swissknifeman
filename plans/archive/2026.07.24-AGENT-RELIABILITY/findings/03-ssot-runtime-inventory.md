# Finding 03 — SSOT и effective runtime inventory

Независимый read-only аудит выполнен 2026-07-24 по repo sources, generated
bundles и установленному Codex plugin cache.

## Что канонично и чисто

- `packages/skiller/skills/**/SKILL.md`: 216 identities, duplicate
  frontmatter names = 0.
- Canonical task commands: `packages/task/commands/`.
- Generated core/task bundles имеют publication/provider locks и package-local
  hash checks.

Проблема возникает не в canonical registry, а в publication/discovery и
provider projection.

## Effective duplicates

Repo-local `.agents/skills` содержит 30 identities; установленные
`core@0.4.0` + `task@0.3.0` добавляют 20. Пересечение — 12:

`anti-drift`, `context-economy`, `plan-protocol`, `query-craft`,
`session-handoff`, `verify-claims`, `task-design`,
`task-plan-{audit,close,design,exec,run}`.

Текущий session catalog показывает их парами (`anti-drift` /
`core:anti-drift`, root `task-plan-*` / `task:task-plan-*`). Лишние 12
records добавляют 2,381 chars metadata (~19% выборки), увеличивая ambiguity,
truncation и wrong-trigger risk.

## Root adapters нарушают собственный invariant

Из 30 root `.agents/skills/*/SKILL.md` только 17 тонких. 13 являются
ручными full copies: 132,079 bytes / 1,495 lines, без generator/lock.
Они добавлены одним bootstrap commit `e8f5b477`.

В шести копиях найдено 48 blind provider substitutions. Самый опасный
`package-architecture` указывает на несуществующие `.Codex-plugin`,
`.Codex/settings`, `.Codex/skills`, `configs/Codex`,
`scripts/connect-Codex.sh`. Это исполнимо неверная инструкция.

## Hash-green не означает provider-correct

- Installed `core@0.4.0` имеет 9 skills, но потерял 24 runtime snippets.
  `plan-protocol` ссылается на отсутствующие templates.
- Исправленный repo bundle и старый installed cache имеют один
  `(plugin name, version)` при разном tree content.
- Core publication byte-copy’ит Claude bodies: `.claude/rules`,
  `CLAUDE.md`, `/compact`, `/clear`, Haiku/Sonnet/Opus и Claude-native tool
  names остаются в Codex skill.
- Task renderer заменяет ограниченный token whitelist, но сохраняет
  `AskUserQuestion`, `WebSearch`, `.claude/workflows`, `.claude/runs`.
- Capability reference для `task:design` не содержит interactive-user-input,
  хотя command требует `AskUserQuestion`.

Следовательно, существующие locks доказывают reproducible bytes, но не:

- dependency closure runtime tree;
- effective identity uniqueness;
- installed-cache compatibility;
- provider capability/executability;
- behavioral parity.

## Требуемые controls

1. Effective inventory: repo-local + installed plugins + generated sources.
2. Один semantic identity на session; collision fail-closed с provenance.
3. Thin adapter size/body/provenance gate.
4. Immutable `(name, version) → tree hash`; content change требует bump.
5. Runtime dependency closure всех relative references.
6. Structured provider renderer; negative invalid-literal/existence checks.
7. Capability coverage из фактических carrier literals.
8. Behavioral provider eval, не только byte/hash parity.
