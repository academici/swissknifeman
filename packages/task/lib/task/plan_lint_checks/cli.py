"""Command-line surface for the split plan-lint implementation."""
from .common import *
from .policy import *
from .parsing import *
from .engine import *
from .conflicts import *


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="plan-lint.py",
        description="Детерминированный валидатор plan-протокола (plans/<PLAN-ID>/…).",
    )
    parser.add_argument("path", nargs="?", default=None,
                         help="путь к plans/<PLAN-ID> или к plans/ (необязателен при "
                              "--conflicts — та сверяет канон, не конкретный план)")
    parser.add_argument("--json", action="store_true",
                         help="вывести распарсенную модель (планы→фазы→items) в stdout как JSON")
    parser.add_argument("--baseline", nargs="?", const="HEAD", default=None, metavar="REF",
                         help="git-ref для счёта НОВЫХ ошибок от рабочего дерева (K, B1/D5/D6); "
                              "без значения — HEAD")
    parser.add_argument("--gate", choices=("all", "new"), default="all",
                         help="exit-код по всем диагностикам (all, дефолт — back-compat CI) "
                              "или только по новым от --baseline (new); при недоступном "
                              "baseline gate=new деградирует к all (красное не пропускается)")
    parser.add_argument("--conflicts", action="store_true",
                         help="сверка «канон (SKILL.ru.md) ↔ реализация (реестры этого "
                              "модуля)» без плана на входе (roadmap plan-audit-loop.md §A.1, "
                              "третья нога конфликт-скана); `path`, если передан, игнорируется")
    args = parser.parse_args(argv)

    if args.conflicts:
        diag = Diagnostics()
        run_conflicts_check(diag)
        for msg in diag.errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        for msg in diag.warnings:
            _core_warn(msg)
        status = "OK" if diag.ok else "ПРОВАЛ"
        print(f"plan-lint --conflicts: {status} ({len(diag.errors)} расхождений, "
              f"{len(diag.warnings)} предупреждений)")
        return 0 if diag.ok else 1

    if args.path is None:
        parser.error("path обязателен без --conflicts")

    root = Path(args.path)
    plan_dirs = discover_plan_dirs(root)
    if plan_dirs is None:
        print(f"ERROR: путь не найден: {root}", file=sys.stderr)
        return 1

    # discover_plan_dirs: одиночный план — это (root/"plan.md").is_file() → [root];
    # тот же признак используем здесь, чтобы root-проверки (ACTIVE.md/черновики)
    # не применялись к одиночному `plan-lint.py plans/<ID>` (там ACTIVE.md вне видимости).
    is_plans_root = not (root / "plan.md").is_file()

    if not plan_dirs and not is_plans_root:
        print(f"нет планов для проверки в {root}")
        return 0

    diag = Diagnostics()
    models = {}
    for plan_dir in plan_dirs:
        models[plan_dir.name] = lint_plan(plan_dir, diag)

    if is_plans_root:
        lint_plans_root(root, models, diag)

    new_count = None
    if args.baseline is not None:
        base_keys, reason = _baseline_diag_keys(root, args.baseline)
        if reason is not None:
            diag.warning(root, None,
                         f"baseline «{args.baseline}» недоступен: {reason} — "
                         f"счёт новых ошибок не вычислен")
        else:
            diff = Counter(diag.normalized_keys(root)) - Counter(base_keys)
            new_count = sum(diff.values())

    for msg in diag.errors:
        print(f"ERROR: {msg}", file=sys.stderr)
    for msg in diag.warnings:
        _core_warn(msg)

    if args.json:
        print(json.dumps({"plans": models}, ensure_ascii=False, indent=2))
    else:
        status = "OK" if diag.ok else "ПРОВАЛ"
        suffix = f"; новых от рабочего дерева: {new_count}" if new_count is not None else ""
        print(f"plan-lint: {status} ({len(plan_dirs)} план(ов), "
              f"{len(diag.errors)} ошибок, {len(diag.warnings)} предупреждений{suffix})")

    if args.gate == "new" and new_count is not None:
        return 0 if new_count == 0 else 1
    return 0 if diag.ok else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = tuple(name for name in globals() if not name.startswith("__"))
