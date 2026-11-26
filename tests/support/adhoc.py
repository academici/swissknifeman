"""Real composed bus and pack resources for the ad hoc surfaces."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from contracts.context.harness import core_pack
from contracts.execution.harness import ExecSide, MutableBuiltinPacks, make_exec_side
from contracts.extensions.harness import pack_payload
from skm.kernel.json_types import JsonObject
from skm.modules.access import public as access
from skm.modules.extensions import public as extensions
from skm.modules.extensions.ports import BuiltinPacks

ROOT = Path(__file__).resolve().parents[2]


def workflow() -> JsonObject:
    return {
        "schema": "urn:skm:execution:workflow:v1",
        "id": "standalone-pipe",
        "version": "1.0.0",
        "applies_to": ["research"],
        "stage": [
            {"id": "setup", "type": "prepare_environment", "for_kinds": ["adhoc"]},
            {"id": "respond", "type": "agent_step", "role": "executor", "for_kinds": ["adhoc"]},
            {"id": "finish", "type": "acceptance_gate", "for_kinds": ["adhoc"]},
        ],
    }


def assembly() -> JsonObject:
    return {"role": "executor", "runtime_id": "codex_cli", "model": "gpt-5", "context_window_tokens": 32000}


@pytest.fixture
def adhoc_side(tmp_path: Path) -> Iterator[ExecSide]:
    for side in make_exec_side("memory", tmp_path):
        gateway = cast("MutableBuiltinPacks", side.app.gateways.get(BuiltinPacks))
        version = "1.2.0"
        files = {item.path: item.content.decode() for item in core_pack(version).files}
        files["workflows/quick-fix.toml"] = (
            ROOT / "resources/packs/core/workflows/quick-fix.toml"
        ).read_text()
        gateway.current = (pack_payload("core", version, files=files),)
        side.client.dispatch(extensions.SyncBuiltinPacks(), idempotency_key="install-adhoc-test-pack")
        yield side


def token(side: ExecSide, *, permissions: tuple[str, ...] | None = None) -> str:
    result = cast(
        "Any",
        side.client.dispatch(
            access.CreateToken(
                name=f"adhoc-{side.new_id()}",
                principal_id=None,
                scope_id=side.proj,
                permissions=permissions,
            )
        ),
    )
    return cast("str", result.secret)
