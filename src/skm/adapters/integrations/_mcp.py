"""Shared MCP entry projection for Claude Code, Codex, Cursor and Grok targets."""

from collections.abc import Mapping, Sequence
from typing import Any, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import McpServerSpec
from skm.platform.config.secrets import SecretRef

__all__ = ["build_server_entry"]


def _validate_secret_refs(
    server_name: str, raw_refs: Mapping[object, object], *, env_interpolation: bool
) -> dict[str, str]:
    env_out: dict[str, str] = {}
    for raw_var, raw_ref in sorted(raw_refs.items(), key=lambda kv: str(kv[0])):
        var_name = str(raw_var)
        try:
            if not var_name or not isinstance(raw_ref, str):
                raise ValueError("missing environment name or secret reference")
            ref = SecretRef.parse(raw_ref)
        except (ValueError, ValidationFailed) as error:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"MCP server {server_name!r} env entry {var_name!r} must be a SecretRef",
                details={"server": server_name, "env_key": var_name, "reason": "secret_ref_required"},
            ) from error
        if env_interpolation and ref.scheme != "env":
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID,
                f"MCP server {server_name!r} supports only environment secret references",
                details={"server": server_name, "env_key": var_name, "reason": "unsupported_secret_ref"},
            )
        env_out[var_name] = "${" + ref.path + "}" if env_interpolation else str(ref)
    return env_out


def build_server_entry(name: str, spec: McpServerSpec, *, env_interpolation: bool = False) -> dict[str, Any]:
    """Project one MCP server, applying env_refs after env.

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
        validated_env = _validate_secret_refs(
            name, cast("Mapping[object, object]", raw_env), env_interpolation=env_interpolation
        )
        if validated_env:
            entry["env"] = validated_env

    raw_env_refs = spec.get("env_refs")
    if raw_env_refs is not None and not isinstance(raw_env_refs, Mapping):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, f"MCP server {name!r} env_refs must be a mapping")
    if isinstance(raw_env_refs, Mapping) and raw_env_refs:
        validated_refs = _validate_secret_refs(
            name, cast("Mapping[object, object]", raw_env_refs), env_interpolation=env_interpolation
        )
        if validated_refs:
            merged_env = dict(cast("Mapping[str, str]", entry.get("env", {})))
            merged_env.update(validated_refs)
            entry["env"] = dict(sorted(merged_env.items()))

    return entry
