# P8.3 — Паспорт релиза v0.9.0

## Диапазон

Последний тег в origin — `v0.8.0` (commit `34e2694`). CHANGELOG.md последний раз правился
коммитом `dffd610` (settings-doctor, SKM-ROADMAP-005 P1) — но тег `v0.8.0` был поставлен
**без** среза релиз-хединга (в CHANGELOG.md нет секции `## [0.8.0]`, весь SKM-ROADMAP-005
P2–P7 и весь `2026.07.12-CONTEXT-ECONOMY` P1–P8.2 копились в `[Unreleased]` не документируясь
построчно — доуже существовавший разрыв в репо, не внесённый этим item'ом). Диапазон
`dffd610..HEAD` (до коммита P8.3) — 98 коммитов; из них с явным тегом плана
`2026.07.12-CONTEXT-ECONOMY` — 19 (перечислены ниже), остальные принадлежат уже закрытому
и заархивированному плану `SKM-ROADMAP-005` (P2–P7) — их фичи в `[Unreleased]` предметно НЕ
описаны построчно (см. Known Deviations) и в рамках P8.3 не бэкфиллились (вне Scope Included
этого item'а — версии/CHANGELOG/registry/validate ИМЕННО этого плана, не ретроактивная
документация чужого закрытого плана).

## CHANGELOG

- `CHANGELOG.md` (root): добавлена группа `### Added (2026.07.12-CONTEXT-ECONOMY — …)` (13
  записей, по одной на значимую фичу P1.1–P8.2) + `### Changed` (P5.4 Skip by decision, D7);
  весь накопленный `[Unreleased]` (старый контент, включая недокументированный
  SKM-ROADMAP-005-хвост) срезан в новую секцию `## [0.9.0] - 2026-07-12`; `[Unreleased]`
  оставлен пустым.
- `packages/maind/CHANGELOG.md`: добавлена группа `### Added (2026.07.12-CONTEXT-ECONOMY —
  тощий старт сессии)` (3 записи — digest-бюджет P1.1, тихий health-хук P1.2, `doctor
  --context` P5.2); накопленный `[Unreleased]` срезан в `## [0.3.0] — 2026-07-12`.
- `packages/skiller/CHANGELOG.md` / `packages/harness/CHANGELOG.md` — не существуют
  (подтверждено `os.path.exists`); D9 не требовал их создания, версии этих пакетов фиксируются
  только в `package.json` + записи в корневом `CHANGELOG.md`.

## Версии (D9)

| Пакет | Было | Стало |
|:--|:--|:--|
| `packages/maind/package.json` | 0.2.1 | **0.3.0** |
| `packages/skiller/package.json` | 0.3.0 | **0.4.0** |
| `packages/harness/package.json` | 0.1.0 | **0.2.0** |
| `packages/analyst/package.json` | 0.1.0 | без изменений (D9 не включает analyst) |
| Тег монорепо | v0.8.0 | **v0.9.0** (ставится в P8.4, только с approve Owner) |

## Финальный прогон гейтов

| Гейт | Команда | Результат |
|:--|:--|:--|
| validate.sh skiller | `bash packages/skiller/scripts/validate.sh` | 🟢 216 skills OK (66 ожидаемых burn-down WARN), 379 тестов OK, registry --check без дрифта |
| validate.sh maind | `bash packages/maind/scripts/validate.sh` | 🟢 415 тестов OK |
| validate.sh harness | `bash packages/harness/scripts/validate.sh` | 🟢 OK (agent-pack render/upgrade смоук зелёный) |
| идемпотентность `skiller registry` | прогнан после версии/CHANGELOG правок | 🟢 PASS — `git status --porcelain` не показал новых изменений от registry (215 skills, 54 plugins, без дрифта) |
| `git status` до коммита | `git status --porcelain` | 🟢 чисто по Scope: `CHANGELOG.md`, `packages/maind/CHANGELOG.md`, `packages/{maind,skiller,harness}/package.json` — 5 файлов |

## Известные отклонения (Known Deviations)

- Тег `v0.8.0` был поставлен без среза `[Unreleased]` в CHANGELOG (разрыв существовал ДО этого
  плана — не создан и не устранён им; устранять задним числом историю v0.8.0 вне Scope P8.3).
- Фичи `SKM-ROADMAP-005` P2–P7 (workflow-craft, plan-protocol 2.0, `wf-status`, changelog-gate,
  release-engineering, domain-modeling, `ecosystem-map`, glossary-conformance и др.) сейчас
  попадают под релиз v0.9.0 фактически (были в `[Unreleased]` до среза), но НЕ описаны
  построчно в новой группе Added — это чужой уже закрытый и заархивированный план; бэкфилл его
  документации — отдельный кандидат (не в Scope Included P8.3: «версии/CHANGELOG/registry/
  validate ИМЕННО этого плана»), отмечено в Pending Work handoff.
- `package-lock.json` (maind/skiller) не тронуты — версии в них уже были рассинхронизированы с
  `package.json` ДО этого item'а (напр. maind lock `0.1.0` при package.json `0.2.1`); вне Files
  этого item'а, править лок-файлы вручную (без `npm install`) рискованно и не запрошено.

## Вердикт

Дерево готово к тегу `v0.9.0` при явном approve Owner (P8.4 — отдельный ручной стоп-гейт,
эта работа его не предвосхищает и не заменяет).
