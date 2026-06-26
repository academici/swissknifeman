---
name: resolving-merge-conflicts
bucket: oss-dev
version: 0.1.0
description: "Дисциплина разрешения активного git merge/rebase-конфликта: понять состояние и первичные источники каждого изменения (коммиты/PR/issue), разрешить каждый hunk сохраняя оба намерения где возможно (не изобретать поведение, никогда --abort), прогнать проверки проекта, завершить merge/rebase. Активировать при конфликте слияния/перебазирования."
risk: write
persona: oss-dev
tags: [git, merge, rebase, conflicts]
requires: [git-commit-rules]
produces_for: []
outputs: []
snippets: []
adapters: [claude, cursor, fable]
disable-model-invocation: false
sha256: ""
---

# Resolving Merge Conflicts

1. **See the current state** of the merge/rebase. Check git history, and the conflicting files.

2. **Find the primary sources** for each conflict. Understand deeply why each change was made, and what the original intent was. Read the commit messages, check the PRs, check original issues/tickets.

3. **Resolve each hunk.** Preserve both intents where possible. Where incompatible, pick the one matching the merge's stated goal and note the trade-off. Do **not** invent new behaviour. Always resolve; never `--abort`.

4. Discover the project's **automated checks** and run them — typically typecheck, then tests, then format. Fix anything the merge broke. (Наш стек: `php artisan test` / `phpstan`; `dart analyze` + `flutter test`; `vitest` / `vue-tsc`.)

5. **Finish the merge/rebase.** Stage everything and commit. If rebasing, continue the rebase process until all commits are rebased.

## Связанные скиллы

- `general/git-commit-rules` — формат итогового merge/rebase-коммита (обязательная зависимость).
- `oss-dev/github-flow` — общий поток веток/PR, в котором возникает конфликт.
