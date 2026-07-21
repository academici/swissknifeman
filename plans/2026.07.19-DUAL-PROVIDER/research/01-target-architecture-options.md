# Target architecture options

**Основание:** `findings/upstream-patterns-2026-07-19.md`,
`findings/provider-capabilities-2026-07-19.md`,
`findings/repository-baseline-2026-07-19.md`.

## Вариант A — symlink-first

Один физический файл виден из provider-каталогов через symlink.

- Плюсы: почти нет копий, локальная правка мгновенно видна.
- Минусы: plugin caches, Windows, архивы, vendoring и project boundaries могут ломать
  ссылки; невозможно выразить provider-specific transformation; provenance слабый.
- Вердикт: только optional developer mode, не distribution contract.

## Вариант B — независимые provider trees

Claude и Codex каталоги поддерживаются руками.

- Плюсы: просто начать, каждый формат нативен.
- Минусы: два источника истины, неизбежный semantic drift, двойная стоимость updates.
- Вердикт: отклонён.

## Вариант C — canonical contract + deterministic adapters

Semantic source хранится один раз; provider adapters генерируют нативные manifests,
instructions, skills/commands, hooks/settings и lock metadata. Overrides накладываются
по явному precedence contract; doctor сравнивает source hash и rendered hash.

- Плюсы: единый канон, provider-native output, воспроизводимые install/update/repair,
  capability matrix получается из того же manifest.
- Минусы: сначала нужен renderer/domain model; требуется строгий запрет ручной правки
  generated artifacts.
- Вердикт: рекомендован и принят как D2.

## Предлагаемые bounded contexts

1. `core/providers` — IDs, capability vocabulary, config resolution, diagnostics.
2. `skiller/publication` — semantic package registry и provider marketplace adapters.
3. `task/command-contract` — provider-neutral workflow semantics и routing tiers.
4. `harness/rendering` — provider-native config/hooks/permissions/MCP/agents.
5. `maind/deployment` — project target loop, trust and sync.
6. `analyst/events` — neutral run/session/event schema plus provider readers.

Provider adapters зависят от shared contracts; shared contracts не импортируют конкретный
Claude/Codex renderer. Это dependency-direction gate для детализации P1–P6.

