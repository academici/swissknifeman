# Триаж: Universal Framework (2026-06-23)

- **Источник:** Perplexity-аудит, оригинал `memster/agent-universal-framework.md` →
  архив [raw](./2026-06-23-universal-framework.raw).
- **Тема:** профили-наследование, генерация агентов, AI Skills Index, path-scoped
  rules, spec-first (spec-kit), task-graph (Task Master), 18-пунктовая таблица.

## Главный вывод

Бо́льшую часть «добавить» аудит предлагал поверх воображаемого состояния — а в репо
механизмы уже есть (hub = AI Skills Index; профили как данные; reestr). Берём
**дисциплину и идеи**, отклоняем **движок-генерацию** (против агент-driven стойки).

## Триаж

| # | Идея | Вердикт | Куда / почему |
|---|---|---|---|
| 1 | AI Skills Index авто-в CLAUDE.md | ✅ absorb | уже hub; расширяем (Фаза 1), boost-aware |
| 2 | Mustache `.tpl` + `generate-agents` | ❌ reject | против агент-driven; шаблоны = реальные `.md` в паке |
| 3 | Наследование `laravel→php-backend→base` (рендер) | ⏸ defer | как данные `extends`, не рендер |
| 4 | `.swissknife.json` схема | ✅ absorb | только данные `shape/stacks/skills_map` (Фаза 3) |
| 5 | path-scoped rules | ✅ absorb | **нативно** (офиц. docs/en/memory); Фаза 3 |
| 6 | spec-first гейт | ✅ absorb (опц.) | role-agent `spec-writer`, `tech-spec.md`, не глоб.гейт |
| 7 | task-graph tasks.json | ⏸ defer | на maind/agentmemory, не Task Master |
| 8 | `skiller init` | ⏸ defer | свернуть в `integrate` |
| 9 | file-lock протокол | ❌ reject | хрупко; one-branch/worktree |
| 10 | <500-char промпты | ✅ absorb | гайдлайн, не лимит |
| 11 | Нумерация `01_`,`02_` | ❌ reject | проверено: не влияет на `/agents` |
| 12 | `generate-agents` | ❌ reject | seed-агенты + playbook, не движок |
| 13 | `validate-agents` | ✅ absorb | валидатор имён `skills:`/дублей/scope (Фаза 3) |
| 14 | explore-субагент | ✅ absorb | есть; seed в роли |
| 15 | spec-kit `sdd` скилл | ⏸ defer | уже задокументирован как внешний опц. тулчейн |
| 16 | maind ↔ tasks.json | ❌ reject | не связывать maind с чужим форматом |
| 17 | `maind next-task` | ⏸ defer | фича maind отдельно |
| 18 | complexity scoring 1–10 | ❌ reject | церемония |

## Куда легло

Фазы 1 (hub-фикс), 2 (pack-система), 3 (роли/rules/валидатор/схема) плана
`stateful-waddling-tulip`. Решения зафиксированы в
[decisions-ledger](../agent-framework/decisions-ledger).
