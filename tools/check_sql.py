"""Check the packaged migration chain and transaction hygiene without opening a database."""

import argparse
import sys
from pathlib import Path

from skm.adapters.postgres.migrations.runner import (
    MigrationDatabase,
    check_migration_sql,
    discover_migrations,
)
from skm.kernel.errors import SkmError

SQL = Path(__file__).resolve().parents[1] / "src/skm/adapters/postgres/migrations/sql"


def check(root: Path, *, database: MigrationDatabase = "project") -> int:
    chain = discover_migrations(root, database=database)
    if not chain:
        raise ValueError("empty migration chain")
    for name in ["runner_bootstrap.sql", *(item.filename for item in chain if item.kind != "py")]:
        source = (root / name).read_text(encoding="utf-8")
        if not source.strip() or "\0" in source:
            raise ValueError(f"{name}: empty SQL or NUL byte")
        check_migration_sql(source, file=name)
    return len(chain)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()
    try:
        project_root = SQL if args.root is None else args.root
        count = check(project_root)
        print(f"Verified {count} migrations and runner bootstrap in {project_root.name}")
        if args.root is None:
            count = check(SQL.with_name("machine_sql"), database="machine")
            print(f"Verified {count} migrations and runner bootstrap in machine_sql")
    except (OSError, ValueError, SkmError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
