"""Shared MCP entry projection for Claude Code, Codex, Cursor and Grok targets."""

from collections.abc import Mapping, Sequence
from typing import Any, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import McpServerSpec

__all__ = ["build_server_entry"]

_SECRET_REF_PREFIX: Final[str] = "secret://"


def _validate_secret_refs(server_name: str, raw_refs: Mapping[object, object]) -> dict[str, str]:
    env_out: dict[str, str] = {}
    for raw_var, raw_ref in sorted(raw_refs.items(), key=lambda kv: str(kv[0])):
        var_name = str(raw_var)
        if not var_name or not isinstance(raw_ref, str) or not raw_ref.startswith(_SECRET_REF_PREFIX):
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"MCP server {server_name!r} env entry {var_name!r} must be a SecretRef ('secret://...')",
                details={"server": server_name, "env_key": var_name, "reason": "secret_ref_required"},
            )
        # Never resolve secrets into project configuration: keep the opaque SecretRef string verbatim.
        env_out[var_name] = raw_ref
    return env_out


def build_server_entry(name: str, spec: McpServerSpec) -> dict[str, Any]:
    """Project one MCP server, preserving SecretRefs and applying env_refs after env.

    Target renderers validate server names and choose their JSON or TOML ownership paths.
    This function only builds the common entry; it never reads or resolves credentials.
    """
    entry: dict[str, Any] = {}
    srv_type = spec.get("type")
    command = spec.get("command")
    args = spec.get("args")
    url = spec.get("url")

    if isinstance(srv_type, str) and srv_type and srv_type != "stdio":
        entry["type"] = srv_type
    if isinstance(command, str) and command:
        entry["command"] = command
    if isinstance(args, Sequence) and not isinstance(args, (str, bytes)):
        entry["args"] = [str(item) for item in cast("Sequence[object]", args)]
    if isinstance(url, str) and url:
        entry["url"] = url

    if "env" in spec and spec["env"] is not None:
        raw_env = spec["env"]
        if not isinstance(raw_env, Mapping):
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"MCP server {name!r} env must be a mapping of SecretRef strings",
                details={"server": name, "reason": "secret_ref_required"},
            )
        validated_env = _validate_secret_refs(name, cast("Mapping[object, object]", raw_env))
        if validated_env:
            entry["env"] = validated_env

    raw_env_refs = spec.get("env_refs")
    if isinstance(raw_env_refs, Mapping) and raw_env_refs:
        validated_refs = _validate_secret_refs(name, cast("Mapping[object, object]", raw_env_refs))
        if validated_refs:
            merged_env = dict(cast("Mapping[str, str]", entry.get("env", {})))
            merged_env.update(validated_refs)
            entry["env"] = dict(sorted(merged_env.items()))

    return entry
