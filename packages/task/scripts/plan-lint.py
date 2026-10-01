#!/usr/bin/env python3
"""Тонкий лаунчер: добавляет `lib/` (и корень монорепо — для `core/`) в sys.path
и делегирует в `task.plan_lint.main()`. Логика — в lib/task/plan_lint.py
(отдельный импортируемый модуль: имя scripts/plan-lint.py с дефисом нельзя
импортировать напрямую, а тестам нужно дёргать парсер/чеки поштучно, не только
через subprocess).

Вызывается командами протокола (`plan-design`/`plan-run`/`plan-close`):
    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/plan-lint.py" plans/<PLAN-ID>
"""
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent.parent       # packages/task
_MONOREPO_ROOT = _PKG_ROOT.parent.parent                 # корень монорепо (…/packages/task -> …)
sys.path.insert(0, str(_PKG_ROOT / "lib"))
if (_MONOREPO_ROOT / "core").is_dir():
    # core/ опционален (standalone-раскладка пакета — без монорепо-родителя — тоже
    # рабочая: task.plan_lint сам фолбэкается без core.term).
    sys.path.insert(0, str(_MONOREPO_ROOT))

from task.plan_lint import main  # noqa: E402  (после правки sys.path)

if __name__ == "__main__":
    sys.exit(main())
