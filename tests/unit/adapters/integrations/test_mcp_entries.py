"""All four target renderers share MCP entry semantics and opaque SecretRef validation."""

import json
from collections.abc import Mapping
from copy import deepcopy
from typing import cast
from uuid import UUID

import pytest

from skm.adapters.integrations.claude_code.mcp import render_mcp as render_claude
from skm.adapters.integrations.codex.mcp import build_mcp_servers as build_codex
from skm.adapters.integrations.cursor.mcp import render_mcp as render_cursor
from skm.adapters.integrations.grok.mcp import build_mcp_servers as build_grok
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId
from skm.modules.integrations.domain.contracts import McpServerSpec
from skm.modules.integrations.domain.desired import ProjectionInputs
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.target import TargetId


@pytest.fixture(params=tuple(TargetId), ids=lambda target: target.value)
def target(request: pytest.FixtureRequest) -> TargetId:
    return cast("TargetId", request.param)


def _servers(target: TargetId, servers: Mapping[str, McpServerSpec]) -> dict[str, dict[str, object]]:
    inputs = ProjectionInputs(
        project_id=ProjectId(UUID("01928f6e-7a3b-7c41-9d2e-5b8a1f3c4d60")),
        target=target,
        instructions_core={"enabled": False},
        instructions_project={"enabled": False},
        skills=(),
        permissions={},
        profile=PermissionProfile.WORKSPACE_CONTAINED,
        hook_modes={},
        host_subscription_events=(),
        mcp_servers=servers,
        agents=(),
        inputs_digest="sha256:" + "0" * 64,
        config_generation=1,
        diagnostics=(),
    )
    if target is TargetId.CODEX:
        return build_codex(inputs)[0]
    if target is TargetId.GROK:
        return build_grok(inputs)[0]
    rendered = render_claude(inputs) if target is TargetId.CLAUDE_CODE else render_cursor(inputs)
    assert rendered is not None
    return cast("dict[str, dict[str, object]]", json.loads(rendered.managed_bytes)["mcpServers"])


@pytest.mark.parametrize("transport", ["stdio", "sse"])
def test_entry_projection_preserves_refs_and_override_order(target: TargetId, transport: str) -> None:
    spec: McpServerSpec = {
        "type": transport,
        "command": "mcp-server",
        "args": ["--limit", 3],
        "url": "https://example.test/mcp",
        "env": {"TOKEN": "secret://env/BASE", "Z": "secret://env/Z"},
        "env_refs": {"TOKEN": "secret://env/OVERRIDE", "A": "secret://env/A"},
    }
    original = deepcopy(spec)
    projected = _servers(target, {"docs": spec, "disabled": {"enabled": False, "env": "ignored"}})
    expected: dict[str, object] = {
        "command": "mcp-server",
        "args": ["--limit", "3"],
        "url": "https://example.test/mcp",
        "env": {"A": "secret://env/A", "TOKEN": "secret://env/OVERRIDE", "Z": "secret://env/Z"},
    }
    if target is TargetId.CLAUDE_CODE:
        expected["env"] = {"A": "${A}", "TOKEN": "${OVERRIDE}", "Z": "${Z}"}
    if transport != "stdio":
        expected["type"] = transport
    assert projected == {"docs": expected}
    assert list(cast("dict[str, str]", projected["docs"]["env"])) == ["A", "TOKEN", "Z"]
    assert spec == original


@pytest.mark.parametrize(
    ("spec", "env_key"),
    [
        pytest.param({"env": "literal-secret"}, None, id="env-shape"),
        pytest.param({"env": {"TOKEN": "literal-secret"}}, "TOKEN", id="env-literal"),
        pytest.param({"env_refs": {"TOKEN": "literal-secret"}}, "TOKEN", id="refs-literal"),
        pytest.param(
            {"env": {"TOKEN": "literal-secret"}, "env_refs": {"TOKEN": "secret://env/TOKEN"}},
            "TOKEN",
            id="override-cannot-hide-literal",
        ),
        pytest.param({"env_refs": {"": "secret://env/TOKEN"}}, "", id="empty-name"),
        pytest.param({"env": {"TOKEN": 17}}, "TOKEN", id="non-string-ref"),
    ],
)
def test_each_target_rejects_invalid_secret_refs(
    target: TargetId, spec: McpServerSpec, env_key: str | None
) -> None:
    with pytest.raises(ValidationFailed) as raised:
        _servers(target, {"docs": spec})
    error = raised.value
    assert error.code is ErrorCode.CONFIG_INVALID
    expected = {"server": "docs", "reason": "secret_ref_required"}
    if env_key is not None:
        expected["env_key"] = env_key
    assert error.details == expected
    assert "literal-secret" not in str(error)
