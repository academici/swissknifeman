from pathlib import Path

import pytest
from tools.check_sql import check

from skm.kernel.errors import SkmError


def test_static_checker_uses_migrator_rules_for_bootstrap_and_chain(tmp_path: Path):
    bootstrap = tmp_path / "runner_bootstrap.sql"
    migration = tmp_path / "0001_core_roles.sql"
    bootstrap.write_text("SELECT 1;")
    migration.write_text("SELECT 'COMMIT'; -- ROLLBACK")
    assert check(tmp_path) == 1
    bootstrap.write_text("BEGIN;")
    with pytest.raises(SkmError):
        check(tmp_path)
    bootstrap.write_text("SELECT 1;")
    migration.rename(tmp_path / "0002_core_roles.sql")
    with pytest.raises(SkmError, match="chain"):
        check(tmp_path)
