---
name: release-discipline
bucket: repository-bootstrap
version: 0.1.0
description: "Завершение любого содержательного изменения в этом репозитории: validate.sh → skiller registry → CHANGELOG [Unreleased] → PR; правила semver-тегов. Активировать перед каждым коммитом/PR и при подготовке релиза."
risk: draft
persona: oss-dev
tags: [release, changelog, validate, root-bootstrap]
requires: []
produces_for: []
outputs: [chat]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Дисциплина завершения изменений и релизов

Внутренний скилл (не экспортируется). **Процедура** финализации; что именно
генерируется и чем — в [package-architecture]; канонический раздел
Releases & Tagging — в `CONTRIBUTING.md`.

[package-architecture]: ../package-architecture/SKILL.md
[skill-authoring]: ../skill-authoring/SKILL.md
[docs-maintenance]: ../docs-maintenance/SKILL.md
[field-feedback-loop]: ../field-feedback-loop/SKILL.md

## Когда активировать

- Перед любым коммитом/PR в этом репозитории.
- При подготовке релизного тега.

## Алгоритм завершения изменения

1. `bash packages/<пакет>/scripts/validate.sh` зелёный для затронутого пакета
   (`skiller`/`harness`/`maind`; CI гоняет те же скрипты). В корне общего `scripts/validate.sh` нет.
2. Изменялось что-то под `skills/`, `generate-skill/`, `buckets.json` →
   `skiller registry`; регенерированные артефакты коммитятся **вместе**
   с изменением (валидатор падает на устаревших манифестах).
3. Генерируемые файлы никогда не правятся руками (список —
   [package-architecture]).
4. Содержательное изменение → запись в CHANGELOG `[Unreleased]` в стиле
   существующих записей (группировка, жирный лид, русский текст).
   Тривиальное (опечатки, форматирование) — без CHANGELOG.
5. PR.
6. Прогнать решение по [docs-maintenance] (нужно ли обновлять docs/).

## Теги и версии

- Аннотированные semver-теги: `git tag -a vX.Y.Z -m "..."`.
- **minor** — возможности фреймворка (CLI, установщик, sync/registry,
  валидатор, схемы); **patch** — контент скиллов и исправления.
- При теге: `[Unreleased]` → `[X.Y.Z]` в CHANGELOG; пуш тега — вручную.
- Теги — маркеры для людей: версии плагинов Claude Code резолвятся в git SHA
  и от тегов не зависят.

## Чеклист

- [ ] validate зелёный.
- [ ] Регенерированное закоммичено вместе с изменением.
- [ ] Генерируемые файлы не правились руками.
- [ ] CHANGELOG обновлён (или изменение тривиально).
- [ ] Решение по docs/ зафиксировано ([docs-maintenance]).

## Связанные скиллы

[package-architecture] (карта), [skill-authoring] (авторинг),
[docs-maintenance] (handoff), [field-feedback-loop] (частый источник
изменения — отклонение, пойманное в полевой работе).

## Ссылки

`CONTRIBUTING.md` (Releases & Tagging), `CHANGELOG.md`.

## Провенанс (root-bootstrap, P1.2)

Класс A private/source-only root-bootstrap identity (D31/D38, `plans/2026.07.24-AGENT-RELIABILITY`):
канонический источник — этот файл; тонкие проекции — `.claude/skills/release-discipline/SKILL.md`
и `.agents/skills/release-discipline/SKILL.md` (генерируются `skiller registry`, не редактируются
руками). Бакет `repository-bootstrap` — приватный, не публикуется как обычный unit/core/marketplace,
не вендорится/коннектится в проекты-потребители.
