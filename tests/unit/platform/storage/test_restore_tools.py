"""Backup verification runs the PostgreSQL client found on the operator's own search path."""

from collections.abc import Mapping
from pathlib import Path
from typing import IO

import pytest

from skm.platform.storage import backup, restore


class _Stop(Exception):
    pass


def test_dump_verification_keeps_path_for_pg_restore(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / backup.DUMP).write_bytes(b"PGDMP")
    seen: list[tuple[str, dict[str, str]]] = []

    def record(program: str, args: list[str], environ: Mapping[str, str], **_: IO[bytes]) -> None:
        seen.append((program, dict(environ)))
        raise _Stop

    monkeypatch.setattr(backup, "run_pg_tool", record)
    with pytest.raises(_Stop):
        restore._dump_blobs(tmp_path, {"PATH": "/opt/postgresql/bin:/usr/bin", "PGPASSWORD": "not-forwarded"})
    assert seen == [("pg_restore", {"PATH": "/opt/postgresql/bin:/usr/bin"})]


def test_empty_cli_environ_still_keeps_the_operator_search_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from skm.entrypoints.cli.main import _environ_with_operator_search_path

    monkeypatch.setenv("PATH", "/opt/postgresql/bin:/usr/bin")
    monkeypatch.setenv("SYSTEMROOT", "C:\\Windows")
    env = _environ_with_operator_search_path({})
    assert env["PATH"] == "/opt/postgresql/bin:/usr/bin"
    assert env["SYSTEMROOT"] == "C:\\Windows"
    provided = _environ_with_operator_search_path({"PATH": "/custom/bin", "SYSTEMROOT": "no"})
    assert provided == {"PATH": "/custom/bin", "SYSTEMROOT": "no"}
