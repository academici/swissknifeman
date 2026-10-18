# P6.1 — dry-run миграции, машина A (2026-10-18)

**Итог: готово к MIGRATE-HOST-A: ДА для 6 проектов (vaulter исключён по D16).** `migrate plan --local-only-secrets` (D17) даёт ready без блокеров
во всех проектах, кроме chatom и vaulter, где остановка — `MIGRATION_IN_PROGRESS` (есть пункты in_progress; для chatom
живых runs нет, `--allow-in-progress` допустим; vaulter не мигрируется). Без `--local-only-secrets` все 7 проектов блокировались `MIGRATION_BLOCKED_SECRET`.

Workspace создан `~/.local/share/swissknifeman/workspace` (`workspace init`), 6 проектов привязаны (`project attach`), маркеры не закоммичены.

## Таблица проектов
| Проект | Папок планов | Блокеры | Живые runs | Warn | Файлов PS-SECRET (local-only) | Большие файлы (local-only) | Остановка migrate plan |
|---|---|---|---|---|---|---|---|
| billium | 1 | нет | нет | PS_HOME_PATH×14 | 2 | 0 | нет |
| commerz | 2 | нет | нет | PS_HOME_PATH×44 | 1 | 0 | нет |
| azguard | 3 | нет | нет (9 stopped) | PS_HOME_PATH×88 | 77 | 0 | нет |
| chatom | 7 | нет | нет | PS_EXECUTABLE×1, PS_HOME_PATH×631 | 61 | 3 | MIGRATION_IN_PROGRESS (1 пункт) |
| corex | 8 | нет | нет | PS_EXECUTABLE×4, PS_HOME_PATH×2079 | 155 | 25 | нет |
| vaulter | 13 | нет | **есть** (conduct VAULTER-KERNEL, PID 3809806) | PS_EXECUTABLE×8, PS_HOME_PATH×1770 | 92 | 43 | MIGRATION_IN_PROGRESS (2 пункта); не мигрируется (D16) |
| swissknifeman | 5 | нет | нет (в state run P6.1 старый «running», процесса нет) | PS_HOME_PATH×60 | 6 | 0 | нет |

## Замечания для владельца
- 3 лога `review-*-debug.log` в `azguard/plans/2026.10.01-№1-AZGUARD-V1/artifacts/P4.10-P4.11-execution/` (уже в git azguard) и часть diff/jsonl артефактов ревью в chatom, corex, vaulter содержат значения, похожие на ключи (UUID, `sk-…`, длинный secret). Если это настоящие ключи провайдеров — заменить. При миграции они остаются local-only и не публикуются.
- Остальные срабатывания PS-SECRET — имена `token`/`password` в тексте и коде планов.
- Обнаруженные в P6.1 дефекты исправлены до закрытия пункта: лимит stdout плагина (cd0294c35), `--local-only-secrets` (2d0ad4e4f, D17).
- В окружении launcher `SKM_WORKSPACE_ROOT` указывает на код модуля: workspace-команды на живых данных запускать с `SKM_WORKSPACE_ROOT=<корень данных>` и из каталога проекта своим launcher.
