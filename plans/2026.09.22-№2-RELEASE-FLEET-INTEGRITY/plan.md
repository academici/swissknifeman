# 2026.09.22-№2-RELEASE-FLEET-INTEGRITY — План №2 — Целостность релиза и fleet-доставки

## 0. Meta

| Поле | Значение |
|:--|:--|
| Plan ID | 2026.09.22-№2-RELEASE-FLEET-INTEGRITY |
| Short ID | PLAN3 |
| Title | План №2 — Целостность релиза и fleet-доставки |
| Layout | v2 |
| Document Type | Executable Master Plan |
| Authoring Model | gpt-6/high |
| Repository | swissknifeman |
| Related Packages | skiller · harness · maind · task · analyst |
| Execution Mode | one end-to-end item with parallel read-only discovery |
| Target Operator Classes | P1: frontier/high |
| Approval Owner | repository owner |
| Home | repo:swissknifeman |
| visibility | private |
| Paused By | — |

## 1. Context

Релиз `v0.24.0` зафиксировал Task `0.21.0`, хотя владелец установил актуальную
версию Task `0.24.0`. Release snapshot и attestation сравнивали согласованные
старые generated-данные и дали ложный GREEN. Одновременно package runtime,
plugin manifests, publication locks, provider caches и downstream bundles могут
иметь независимый version drift, а fleet из зарегистрированных проектов смешивает
marketplace и legacy vendor delivery. План исправляет owning generators и gates,
готовит следующий локальный release candidate без изменения опубликованного тега,
безопасно мигрирует все enabled projects на согласованные Claude/Codex/Cursor
проекции и делает повторяемым следующий release-to-fleet цикл. Исходное разрешение
и запреты сохранены в `brief/00-owner-brief.md`.

## 2. Execution Rules

- До product writes снять полный read-only baseline и dirty-state всех enabled projects.
- Generated/provider artifacts изменять только штатными generators/repair/sync commands.
- Версии сравнивать по ownership и SemVer; umbrella version не навязывать независимым units.
- Published `v0.24.0` и его tag не изменять; новый tag/push/GitHub Release не выполнять.
- Legacy удалять только при lock/preimage/readback ownership proof; user-owned conflicts блокируют конкретный проект.
- Не менять downstream business code и не перезаписывать unrelated dirty changes.
- Release gate раздельно проверяет snapshot byte consistency, expected unit freshness и cross-surface coherence.
- Release workflow после локального candidate автоматически обновляет fleet и инвалидирует superseded managed caches.
- Внутри одного item порядок жёсткий: baseline → owning fix/release candidate → fleet apply → final gates.
- Финальный GREEN требует идемпотентный fleet dry-run и отсутствие противоречащих обязательных проверок.

## 3. Routing

| Batch | Items | Model class/effort | Exec | Review | Почему |
|:--|:--|:--|:--|:--|:--|
| solo | P1.1 | frontier/high | manual | light | required: один непрерывный проход от baseline до release/fleet acceptance без lifecycle-перезапусков |

## 5. Decision Log

Каталог решений: `decisions/`; собрать:
`python3 packages/task/scripts/plan-views.py decisions --plan-dir plans/2026.09.22-№2-RELEASE-FLEET-INTEGRITY`.
