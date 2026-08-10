#!/usr/bin/env python3
"""Тонкий лаунчер: добавляет `lib/` (и корень монорепо — для `core/`) в sys.path
и делегирует в `task.plan_weight.main()`. Логика — в lib/task/plan_weight.py
(отдельный импортируемый модуль: имя scripts/plan-weight.py с дефисом нельзя
импортировать напрямую, а тестам нужно дёргать резолвер/замер поштучно, не только
через subprocess). Тот же шаблон, что у scripts/plan-lint.py.

Вызов:
    python3 packages/task/scripts/plan-weight.py plan plans/<PLAN-ID>
    python3 packages/task/scripts/plan-weight.py item plans/<PLAN-ID> Pn.m --json
    python3 packages/task/scripts/plan-weight.py sweep plans/
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

from task.plan_weight import main  # noqa: E402  (после правки sys.path)

if __name__ == "__main__":
    sys.exit(main())
