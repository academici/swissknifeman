# UPGRADE — после SKM-ROADMAP-005 (2026-07-11)

Гид раскатки на проекты флота: ЧТО поменялось в экосистеме этим планом и что сделать,
чтобы проект получил изменения. Не changelog (детали — в Completion Notes фаз), а карта
«затронуто → как доставить». Для агента, обновляющего проект: не ищи диффы — иди по таблице.

## Что появилось / поменялось

| Область | Что | Как доставляется в проект |
|:--|:--|:--|
| **settings-doctor** (P1) | Конфликт-линтер слоёв настроек Claude Code: `harness settings doctor` (фасад `skiller doctor --settings`); fleet-прогон `maind doctor --audit settings` | Ничего не копируется — команда живёт в harness; достаточно обновлённого swissknifeman на машине |
| **wf status** (P2) | Детерминированный статус-репортер workflow-прогонов: `harness wf status` / фасад `swissknifeman wf status` (+ `--json`, `--watch`) | То же — CLI-команда, раскатки в проект не требует; агентам больше НЕ советовать `/workflows` |
| **workflow-craft** (P3) | Скилл-указатель на канон `packages/task/workflows/` + команда-гейт `/task:make-workflow` (интервью → генерация → статический ревьюер) | Через плагин `task@swissknifeman` — обновить плагины (`maind:plugins` / marketplace pull) |
| **Канон планов** (P4) | plan-protocol 2.1: репо-дом планов по умолчанию (`plans/<ID>/` рядом с docs), канон имён + `supersedes`, дом workflow-скриптов `plans/<ID>/workflows/`, ужесточённый `plan-lint` | Скилл `general/plan-protocol` — через skiller connect/vendor (re-sync скиллов); в проектах с планами завести `plans/ACTIVE.md` |
| **changelog-discipline** (P5) | Скилл-дисциплина CHANGELOG (release-engineering), opt-in commit-гейт `harness hooks --target . --changelog-gate warn\|strict`, `skiller release` / `swissknifeman release` | Скилл — re-sync; гейт — включить ЯВНО per-проект (opt-in, по умолчанию выключен) |
| **ecosystem-glossary** (P6) | `architect/domain-modeling` усилен (триггеры CONTEXT.md, Rule of Two, `## Conformance`); «Glossary impact?» в 5 ревью-паках harness; glossary-измерение в `/task:review` Stage B; скилл-указатель `axioma/axioma-glossary`; каркас term-index в Brain `02-Knowledge/00-Strategy/Ecosystem_Glossary.md` | Скиллы — re-sync (connect/vendor); ревью-паки — ре-рендер agent-packs (`harness agent-packs render`) в проектах с review-gate |
| **roadmap-чистка** (P7) | `ephemeral-discipline` удалён (перенесён в ROADMAP), витрины `roadmap/README.md` сверены | Только этот репо, раскатки нет |

## Рецепт раскатки на проект (типовой)

1. Обновить swissknifeman на машине (git pull + `install.sh` при необходимости) — даёт P1/P2 CLI.
2. `maind sync` (или `skiller connect`/`vendor` re-sync per-проект) — обновлённые скиллы:
   `plan-protocol`, `domain-modeling`, `axioma-glossary`, changelog-дисциплина.
3. Обновить плагины marketplace (`task@swissknifeman` — даёт `/task:make-workflow`, glossary-измерение review).
4. Проекты с agent-packs/review-gate: `harness agent-packs render` — ре-рендер ревью-паков
   («Glossary impact?»).
5. Опционально per-проект: `harness hooks --target . --changelog-gate warn` (дисциплина CHANGELOG).
6. Проекты с планами: проверить соответствие канону 2.1 (`plan-lint`), завести `plans/ACTIVE.md`.

## НЕ раскатано этим планом (хвосты)

- CHANGELOG-строки P3–P6 этого репо не внесены (permission-deny сред) — внести перед релизом.
- Наполнение term-index — roadmap `ecosystem-glossary` (тайм-гейт: код dev-волны ECOSYSTEM P4).
- `workflow-craft` ч.2 (fleet-синтез), maind-провижионер `plans-doc` (D30) — deferred.
