"""Command-line surface for the split plan-lint implementation."""
from .common import *
from .policy import *
from .parsing import *
from .engine import *
from .conflicts import *


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="plan-lint.py",
        description="Deterministic validator plan-protocol (plans/<PLAN-ID>/…).",
    )
    parser.add_argument("path", nargs="?", default=None,
                         help="path to plans/<PLAN-ID> or to plans/ (is optional when "
                              "--conflicts — she checks the canon, not a specific plan)")
    parser.add_argument("--json", action="store_true",
                         help="display the parsed model (plans→phases→items) in stdout like JSON")
    parser.add_argument("--baseline", nargs="?", const="HEAD", default=None, metavar="REF",
                         help="git-ref to count NEW errors from the working tree (K, B1/D5/D6); "
                              "without value - HEAD")
    parser.add_argument("--gate", choices=("all", "new"), default="all",
                         help="exit-code for all diagnostics (all, default — back-compat CI) "
                              "or only new ones from --baseline (new); when unavailable "
                              "baseline gate=new degrades to all (red is not skipped)")
    parser.add_argument("--conflicts", action="store_true",
                         help="reconciliation «EN-only canon (SKILL.md) ↔ implementation (registries of this "
                              "module)» without input plan (roadmap plan-audit-loop.md §A.1, "
                              "third leg of the conflict scan); `path`, if passed, ignored")
    args = parser.parse_args(argv)

    if args.conflicts:
        diag = Diagnostics()
        run_conflicts_check(diag)
        for msg in diag.errors:
            print(f"ERROR: {msg}", file=sys.stderr)
        for msg in diag.warnings:
            _core_warn(msg)
        status = "OK" if diag.ok else "FAILURE"
        print(f"plan-lint --conflicts: {status} ({len(diag.errors)} discrepancies, "
              f"{len(diag.warnings)} warnings)")
        return 0 if diag.ok else 1

    if args.path is None:
        parser.error("path is required without --conflicts")

    root = Path(args.path)
    plan_dirs = discover_plan_dirs(root)
    if plan_dirs is None:
        print(f"ERROR: path not found: {root}", file=sys.stderr)
        return 1

    # discover_plan_dirs: single plan is (root/"plan.md").is_file() → [root];
    # we use the same sign here to root-checks (ACTIVE.md/drafts)
    # were not applied to single `plan-lint.py plans/<ID>` (there ACTIVE.md out of sight).
    is_plans_root = not (root / "plan.md").is_file()

    if not plan_dirs and not is_plans_root:
        print(f"no plans to check in {root}")
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
                         f"baseline «{args.baseline}» not available: {reason} — "
                         f"new error count not calculated")
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
        status = "OK" if diag.ok else "FAILURE"
        suffix = f"; new from working tree: {new_count}" if new_count is not None else ""
        print(f"plan-lint: {status} ({len(plan_dirs)} plan(ov), "
              f"{len(diag.errors)} errors, {len(diag.warnings)} warnings{suffix})")

    if args.gate == "new" and new_count is not None:
        return 0 if new_count == 0 else 1
    return 0 if diag.ok else 1


if __name__ == "__main__":
    sys.exit(main())


__all__ = tuple(name for name in globals() if not name.startswith("__"))
