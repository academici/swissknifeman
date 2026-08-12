#!/usr/bin/env python3
"""CLI for the fail-closed v1 -> v2 plan migrator."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "lib"))

from task.plan_migrate import MigrationError, migrate_safely  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description="Детерминированно перевести plan layout v1 в v2")
    parser.add_argument("plan_dir", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="читать source и писать только в --output")
    parser.add_argument("--output", type=Path, help="новый каталог результата dry-run")
    parser.add_argument("--inventory", type=Path, help="явный путь generated inventory")
    parser.add_argument("--policy", type=Path, help="frozen closed migration-policy manifest")
    parser.add_argument("--apply", action="store_true",
                        help="атомарно применить отдельно проверенный preview")
    parser.add_argument("--preview", type=Path,
                        help="явный Layout-v2 preview для controlled --apply")
    args = parser.parse_args(argv)
    try:
        result = migrate_safely(
            args.plan_dir, dry_run=args.dry_run, output=args.output,
            inventory_path=args.inventory, policy_path=args.policy,
            apply=args.apply, preview=args.preview)
    except (MigrationError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    if args.apply:
        print(f"APPLY: {'installed' if result['applied'] else 'no-op'}; {result['reason']}")
    else:
        print(f"MIGRATED: {len(result['inventory']['item_ids'])} items; "
              f"inventory {result['inventory']['checked']} elements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
