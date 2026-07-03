---
description: "Управлять allowlist'ом доверенных директорий (safe-dirs): где auto-approve разрешает rm/rmdir."
---
Управляй machine-owned allowlist'ом `safe-dirs.json` (живёт В КОРНЕ монорепо swissknifeman, gitignored; шаблон — `safe-dirs.example.json`; лестница поиска хуком: `$SKM_SAFE_DIRS_CONFIG` → корень монорепо → legacy `~/.swissknifeman/`) — внутри его корней (рекурсивно) auto-approve пропускает `rm`/`rmdir` мимо deny_hard (код под git — удаление обратимо). Вне корней rm блокируется как раньше.

```
harness safe-dirs init                                    # создать конфиг с дефолтами
harness safe-dirs list                                    # эффективный allowlist глазами хука
harness safe-dirs add <path> [--exclude] [--dry-run]      # добавить корень (или изъятие)
harness safe-dirs remove <path> [--exclude] [--dry-run]   # убрать корень (или изъятие)
harness safe-dirs prune-ask [--global] [--target P] [--all-projects]
```

- Дефолт `include_registered_projects=true` — пути онбордженных проектов из `~/.swissknifeman/projects.json` включаются автоматически.
- `add` откажется от `/`, `$HOME` и предков `$HOME` (тот же гард в самом хуке).
- `prune-ask` снимает статические ask-правила `Bash(rm -r *)`/`Bash(rm -rf *)` из settings — hook-allow их не пробивает, без чистки rm в safe-dirs продолжит промптить.
- Защиты внутри safe-dirs: сам корень не удаляется, `.git` защищён (`protect_git`), глобы валидируются по статическому префиксу (`allow_globs`).

Разбери намерение из «$ARGUMENTS»; после первичной настройки подскажи: `harness hooks --global` (обновить файлы хука) и перезапуск сессии Claude Code.
