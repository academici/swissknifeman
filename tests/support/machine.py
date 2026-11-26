"""Configure a worker's separate PostgreSQL store through the local operator CLI."""

import json
from collections.abc import Mapping
from io import StringIO
from uuid import uuid4

from skm.adapters.postgres.machine import PostgresMachineStore
from skm.entrypoints.cli.main import main
from skm.kernel.json_types import JsonValue


def machine_operator(environ: Mapping[str, str], dsn: str) -> dict[str, str]:
    installation = uuid4()
    PostgresMachineStore(dsn).initialize_installation(installation)
    return {
        **environ,
        "SKM_INSTALLATION_ID": str(installation),
        "SKM_MACHINE_DATABASE_URL": dsn,
    }


def set_machine_setting(environ: Mapping[str, str], key: str, value: JsonValue) -> None:
    out, err = StringIO(), StringIO()
    code = main(
        ("--json", "config", "machine-set", key, json.dumps(value)),
        environ=environ,
        stdout=out,
        stderr=err,
    )
    assert code == 0, out.getvalue() + err.getvalue()
