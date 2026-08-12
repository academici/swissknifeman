# Roadmap исполнения — 2026.08.12-№1-TASK-RESILIENCE

**Обновлён:** 2026-08-12 · **Соответствует plan.md:** v1.0.0

## Карта исполнения

| Item | Batch | Запуск | Model class/Effort | Гейт владельца | Примечание |
|:--|:--|:--|:--|:--|:--|
| P0.1 | B0 | plan-run серия | implementation/high | — | identity contract |
| P0.2 | B0 | ↑ | frontier/high | — | block policy design + runtime |
| P0.3 | B0 | ↑ | implementation/high | release authorization уже дан | providers/docs/release prep |

## B0 — единый continue-root batch

| Параметр | Значение |
|:--|:--|
| Model class | frontier |
| Effort | high — максимальный риск P0.2 |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | continue-root |
| Суть | Последовательно закрыть P0.1–P0.3 с отдельными item/bookkeeping commits |
| Команда | `$ task:plan-run 2026.08.12-№1-TASK-RESILIENCE P0.1 P0.2 P0.3` |

## Terminal release steps

P0.1–P0.3 исполнены, audit GREEN и phase close завершены. После archive: переименовать
`[Unreleased]` в `[0.12.0]`, commit release,
создать annotated `v0.12.0`, затем обновить зарегистрированные проекты по существующему channel
и проверить `swissknifeman status --all --json`.
