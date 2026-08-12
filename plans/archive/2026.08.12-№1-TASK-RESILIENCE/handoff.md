# HANDOFF — 2026-08-12 — after P0

**Next:** план закрыт

| Параметр | Значение |
|:--|:--|
| Model class | implementation |
| Effort | low — release и штатный rollout |
| Capabilities | skills.repository · command.filesystem-read · command.filesystem-write · command.git-read · command.git-write |
| Context | continue-root |
| Суть | Выпустить `v0.12.0` и обновить зарегистрированные проекты |
| Команда | `—` |

**Native Codex launch block**

| Model | Thinking | Context | Суть | Команда |
|:--|:--|:--|:--|:--|
| gpt-5.6-terra | low | continue-root | Выпустить `v0.12.0` и выполнить штатный rollout | `—` |

**Done:** roadmap recon, design audit GREEN, P0.1 numbered identity (`8a396de8`), P0.2 continue-first kernel (`401cd251`), P0.3 terminal delivery/provider parity (`756a1bbd`) + audit-candidate repairs (`99d1d0a4`, `cea351e1`).
**Remaining:** release tag и rollout зарегистрированных проектов.
**Sources of truth:** `plan.md` · `phases/P0.md` · `findings/00-roadmap-and-runtime-gap.md` · `research/01-target-design.md`.
**Open risks:** Codex active-thread effort не provider-attested; native launch provenance не выдаётся за telemetry.
**Workarounds/Deferred/Open questions:**
- workarounds: —
- deferred: provider transport heartbeat/final hook, если недоступен package-owned seam.
- open_questions: —

## Чек-лист миграции в архив

- `root/` отсутствует — долгоживущих design-carriers для переноса в `docs/` нет.
- `brief/`, `findings/`, `research/`, `phases/`, `index.md`, `journal.jsonl` и `roadmap.md`
  оставлены в `plans/archive/2026.08.12-№1-TASK-RESILIENCE/` как evidence/provenance.
- Документация продукта уже живёт в `packages/task/docs/continue-first.md` и агрегате
  `docs/task/continue-first.md`; повторное копирование не требуется.
- `plans/ACTIVE.md` сброшен на `—` при закрытии P0.
