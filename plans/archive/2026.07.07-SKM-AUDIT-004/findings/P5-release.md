# P5.1 — Паспорт релиза

## Предыстория: недокоммиченные фиксы P3/P4/P6

На момент старта P5.1 `git log ea8e4d3..HEAD` останавливался на `8167d8e`
(последний коммит до плана) — фиксы P3.3/P4.3/P6.2/P6.3, описанные в Update
Log плана как «закрыты», физически лежали НЕзакоммиченными в рабочем
дереве (Update Log их не фиксировал коммит-хэшами, в отличие от P2.1/P2.2).
Расхождение с ожиданием item'а («CHANGELOG на уже чистом дереве») не
architecture-уровня — устранено как часть release-discipline (шаг 1 её
алгоритма: коммит фикса до CHANGELOG), четырьмя коммитами по смыслу
(Conventional Commits RU, без нового кода — только оформление уже
написанного и провалидированного в своих item'ах):

| Коммит | Что |
|:--|:--|
| `e9fb8e1` | docs(skiller): CORE_SKILLS 8→9, roadmap/analyst-fleet-coverage.md (P3.3) |
| `63d4cdd` | fix(harness): perplexity-web permission-промпты (P4.3) |
| `59d4784` | feat(maind): провиженер Laravel PAO (P6.2) |
| `9dbfa6a` | feat(maind): doctor --audit pao (P6.3) |

## CHANGELOG

`[Unreleased]` дополнен 6 группами записей (Added/Fixed/Changed) по
изменениям этого плана — PAO-провиженер+fleet-гейт, perplexity-web
permission-фикс, `SKILL_MANAGED_MARKER` round-trip + registry idempotence,
analyst Laravel-раннеры/guard-паттерны, `norm_path` симлинки, docs
(`task` в корневом CLAUDE.md, CORE_SKILLS 9-й). Стиль — по существующим
записям (жирный лид, русский текст, группировка). Тривиальные nit-коммиты
россыпью не перечислены (по правилу skill `release-discipline`).

## Финальный прогон гейтов (9/9, итоговый HEAD)

Тем же способом, что P1.1/P2.3, на дереве после коммитов P3.3/P4.3/P6.2/P6.3
+ CHANGELOG:

| Гейт | Команда | Результат |
|:--|:--|:--|
| validate.sh skiller | `bash packages/skiller/scripts/validate.sh` | 🟢 PASS |
| validate.sh harness | `bash packages/harness/scripts/validate.sh` | 🟢 PASS |
| validate.sh maind | `bash packages/maind/scripts/validate.sh` | 🟢 PASS |
| validate.sh analyst | `bash packages/analyst/scripts/validate.sh` | 🟢 PASS |
| validate.sh task | `bash packages/task/scripts/validate.sh` | 🟢 PASS |
| core tests | `PYTHONPATH=. python3 -m unittest discover -s core/tests` | 🟢 PASS (151) |
| идемпотентность `skiller registry` | прогнан, `git status --porcelain` без неожиданного diff | 🟢 PASS (207 skills, 53 plugins, diff только ожидаемый — CHANGELOG уже застейджен вручную) |
| stdlib-гейт (grep импортов) | см. Code Guidance P1.1 | 🟢 PASS (0 нарушений — тот же паттерн `from core import ...` не в счёт) |
| gitignore/git status | `git status --porcelain` | 🟢 PASS (см. ниже) |

Рабочее дерево после прогона:

```
 M CHANGELOG.md
 M plans/ACTIVE.md
?? .claude/analyst/
?? plans/2026.07.07-SKM-AUDIT-004/
```

`CHANGELOG.md` — предмет этого item'а (коммитится вместе с закрытием).
`plans/ACTIVE.md`/`plans/2026.07.07-SKM-AUDIT-004/` — артефакты ведения самого плана
(как и в P1.1/P2.3). `.claude/analyst/` — session-специфичные
`audit.ndjson`/`events.ndjson`/`lessons` этого же класса, что и находка N1
(P1-review.md), но для СОБСТВЕННОГО `.claude/` репозитория (не шаблона
harness) — не relate к пакетам, гитигнор для корневого `.claude/analyst/`
вне scope P5.1 (не находка гейтов, не блокирует релиз; кандидат на
отдельный follow-up, отмечен в handoff).

## Версия и тег

Схема тегов репо (`git tag -l`): единый зонтичный `vX.Y.Z` (не per-package),
монотонный ряд `v0.3.0 → v0.4.0 → v0.5.0 → v0.7.0 → v0.7.1`. Последний тег —
`v0.7.1` (2026-06-28).

Semver-оракул скилла `release-discipline`: **minor** — возможности
фреймворка (CLI, установщик, sync/registry, валидатор, схемы); **patch** —
контент скиллов и исправления. Накопленный `[Unreleased]` содержит
несколько minor-уровня возможностей и до, и в рамках этого плана:
Lean-tiering агент-паков, `harness safe-dirs` (новый CLI), whole-server MCP
allow, новые скиллы/профили (уже были в `[Unreleased]` до плана) — и теперь
**новый CLI-гейт `maind doctor --audit pao`** + новый провиженер `maind pao`
(P6.2/P6.3, framework capability, не просто контент скилла). Breaking
change отсутствует (весь диапазон плана — feat/fix/docs, без изменений
публичных контрактов; подтверждено P1.3 вердиктом соответствия философии).

**Предлагаемая версия: `v0.8.0`** (minor, `v0.7.1 → v0.8.0`).

## Вердикт

Дерево готово к тегу при условии коммита CHANGELOG.md (эта запись —
последний шаг P5.1 перед закрытием item'а). Approve и сам тег — P5.2.
