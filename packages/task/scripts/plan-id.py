#!/usr/bin/env python3
"""Тонкий лаунчер: следующий номер плана (`№N` дня + Short ID `PLAN<N>`).

Логика — в lib/task/plan_numbering.py (тот же шаблон, что у scripts/plan-weight.py).

Вызов:
    python3 packages/task/scripts/plan-id.py --codename TASK-RESILIENCE
    python3 packages/task/scripts/plan-id.py --date 2026.10.01 --plans-root plans
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

from task.plan_numbering import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
