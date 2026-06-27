---
name: implement
bucket: general
version: 0.1.0
description: "Implement a chunk of work from a spec/PRD/issue via a minimal chain: tdd-discipline on agreed seams, regular typecheck/tests, a full run at the end, code-review, commit to the current branch. Invoke EXPLICITLY (writes code) — the final step after spec-interview/grill-with-docs/to-issues."
risk: write
persona: oss-dev
tags: [workflow, implementation, tdd, review]
requires: [tdd-discipline, code-review]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
disable-model-invocation: true
sha256: ""
---

# Implement

Реализуй работу, описанную в ТЗ / PRD / issue. Минималистичный скилл: ценность — в дисциплине
цепочки, а не в объёме. Вызывается **только явно** (`disable-model-invocation: true`).

## Алгоритм

1. **Контекст.** Прочитай ТЗ/issue. Если трогаешь схему БД — сначала проверь миграции
   (`php artisan migrate:status` / состояние схемы), потом реализуй.
2. **TDD где возможно.** Используй скилл `tdd-discipline` на **заранее согласованных seam'ах**
   (red→green→refactor вертикальными срезами). Не пиши все тесты вперёд.
3. **Частая обратная связь.** Регулярно гоняй typecheck и отдельные тест-файлы; полный прогон —
   один раз в конце. Конкретные команды по стеку:
   - Laravel/PHP: `php artisan test` (или `./vendor/bin/pest`), `phpstan`/`./vendor/bin/phpstan`.
   - Dart/Flutter: `dart analyze`, `flutter test`.
   - TS/Vue: `vitest`, `tsc --noEmit` / `vue-tsc`.
4. **Ревью.** По завершении — скилл `code-review` (или команда `/code-review`) по получившемуся диффу.
5. **Коммит.** Закоммить в **текущую** ветку (Conventional Commits, на русском).

## Связанные скиллы

- `general/spec-interview` / `general/grill-with-docs` — откуда берётся ТЗ (вход этого скилла).
- `oss-dev/to-issues` — если работа пришла набором issue вертикальными срезами.
- `quality/tdd-discipline` — как реализуем срез (обязательная зависимость).
- `quality/code-review` — финальная проверка (обязательная зависимость).
- `general/git-commit-rules` — формат коммита.
- `oss-dev/github-flow` — если дальше Issue→PR→Release.
