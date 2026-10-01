"""Internal documentation."""
import json
from dataclasses import dataclass
from pathlib import Path

from core import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, ProviderId, plan_artifact_render, sha256_digest)

from .common import die, parse_flags, warn
from .settings import write_json


def available_mcp(env):
    """Internal documentation."""
    d = env.mcp_dir
    return sorted(p.stem for p in d.glob("*.json")) if d.is_dir() else []


def parse_mcp_flag(raw):
    """Internal documentation."""
    return [s.strip() for s in raw.split(",") if s.strip()] if raw else []


def block_mcp(env, target, servers, dry):
    """Internal documentation."""
    servers = servers or []
    print(f"MCP-servers: {', '.join(servers) if servers else 'pass'}")
    if not servers:
        return
    f = target / ".mcp.json"
    data = {}
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{f}: invalid JSON: {e}")
    mcp = data.setdefault("mcpServers", {})
    added = []
    for name in servers:
        preset = env.mcp_dir / f"{name}.json"
        if not preset.exists():
            warn(f"  no preset MCP '{name}' ({preset}) — pass")
            continue
        if name in mcp:
            print(f"  MCP '{name}' is already in .mcp.json — pass")
            continue
        mcp[name] = json.loads(preset.read_text(encoding="utf-8"))
        added.append(name)
    if added:
        write_json(f, data, dry)
        print(f"  added MCP: {', '.join(added)}")


def cmd_mcp(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--mcp": "str", "--list": "bool", "--dry-run": "bool",
    })
    if opts["help"]:
        print("harness mcp [--target P] [--mcp name1,name2] [--list] [--dry-run]")
        return
    if opts["list"]:
        for name in available_mcp(env):
            print(name)
        return
    if not opts["target"]:
        die("needed --target P (or --list)")
    from pathlib import Path
    block_mcp(env, Path(opts["target"]).expanduser(),
              parse_mcp_flag(opts["mcp"]), opts["dry_run"])


# deliberately keeps this seam small. The legacy functions above own the
# Claude merge/write behaviour; the records below are immutable planning data
# for both providers and never infer one provider's output from another.
@dataclass(frozen=True)
class McpServer:
    id: str
    transport: str
    capability_id: str
    secret_refs: tuple[str, ...]


@dataclass(frozen=True)
class McpProjection:
    provider_id: ProviderId
    target_scope: str
    target_path: str
    servers: tuple[tuple[str, dict], ...]
    secret_refs: tuple[str, ...]


def load_mcp_catalog(path: Path) -> tuple[McpServer, ...]:
    """Load the common, value-free MCP inventory in its declared order."""
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict) or set(value) != {"catalog_version", "servers"}:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    rows = value["servers"]
    if value["catalog_version"] != "1.0.0" or not isinstance(rows, list):
        raise ValueError("HARNESS_VERSION_UNSUPPORTED")
    result = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"id", "transport", "capability_id", "secret_refs"}:
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        if (not isinstance(row["id"], str) or not row["id"]
                or row["transport"] not in {"http", "stdio"}
                or not isinstance(row["capability_id"], str)
                or not isinstance(row["secret_refs"], list)
                or len(set(row["secret_refs"])) != len(row["secret_refs"])):
            raise ValueError("HARNESS_CATALOG_MISMATCH")
        result.append(McpServer(row["id"], row["transport"], row["capability_id"],
                                tuple(row["secret_refs"])))
    if not result or len({item.id for item in result}) != len(result):
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    return tuple(result)


def plan_mcp_projection(catalog: tuple[McpServer, ...], *, provider_id: ProviderId,
                        bindings_path: Path, selected: tuple[str, ...], trusted: bool) -> McpProjection:
    """Return one independent native projection, without writing a target or lock."""
    if not trusted:
        raise ValueError("HARNESS_TRUST_REQUIRED")
    ids = {server.id for server in catalog}
    if len(set(selected)) != len(selected) or set(selected) - ids:
        raise ValueError("HARNESS_CATALOG_MISMATCH")
    projection = json.loads(Path(bindings_path).read_text(encoding="utf-8"))
    if (not isinstance(projection, dict)
            or set(projection) != {"binding_version", "provider_id", "target_scope",
                                   "target_path", "servers"}
            or projection["binding_version"] != "1.0.0"
            or projection["provider_id"] != provider_id.value):
        raise ValueError("HARNESS_MAPPING_MISSING")
    if (not isinstance(projection["target_scope"], str)
            or not isinstance(projection["target_path"], str)
            or not isinstance(projection["servers"], dict)):
        raise ValueError("HARNESS_MAPPING_MISSING")
    rendered = []
    for server_id in selected:
        record = projection["servers"].get(server_id)
        if not isinstance(record, dict):
            raise ValueError("HARNESS_MAPPING_MISSING")
        server = next(server for server in catalog if server.id == server_id)
        _validate_secret_references(server, record)
        rendered.append((server_id, record))
    refs = tuple(sorted({ref for server_id in selected for server in catalog
                         if server.id == server_id for ref in server.secret_refs}))
    return McpProjection(provider_id, projection["target_scope"], projection["target_path"],
                         tuple(rendered), refs)


def _validate_secret_references(server, record):
    """Only declared placeholder references may cross the projection boundary."""
    if "secret_value" in record:
        raise ValueError("HARNESS_SECRET_VALUE_EXPOSED")
    env = record.get("env", {})
    if not isinstance(env, dict):
        raise ValueError("HARNESS_MAPPING_MISSING")
    expected = {"${" + ref.upper().replace("-", "_") + "}" for ref in server.secret_refs}
    observed = set()
    for value in env.values():
        if not isinstance(value, str) or not value.startswith("${") or not value.endswith("}"):
            raise ValueError("HARNESS_SECRET_VALUE_EXPOSED")
        observed.add(value)
    if observed != expected:
        raise ValueError("HARNESS_SECRET_REFERENCE_MISSING")


def plan_mcp_artifact(plan: McpProjection, *, catalog_path: Path, bindings_path: Path):
    """Codex/Cursor MCP is a P2 whole-file artifact; Claude keeps its merge-only writer."""
    if plan.provider_id not in (ProviderId.CODEX, ProviderId.CURSOR):
        raise ValueError("HARNESS_MAPPING_MISSING")
    binding_label = ("harness.codex.mcp-bindings" if plan.provider_id is ProviderId.CODEX
                     else "harness.cursor.mcp-bindings")
    binding_relpath = ("packages/harness/configs/codex/mcp/bindings.json"
                       if plan.provider_id is ProviderId.CODEX
                       else "packages/harness/configs/cursor/mcp/bindings.json")
    sources = (
        ArtifactSource("harness.mcp.catalog", "packages/harness/configs/common/mcp/catalog.json",
                       sha256_digest(Path(catalog_path).read_bytes())),
        ArtifactSource(binding_label, binding_relpath,
                       sha256_digest(Path(bindings_path).read_bytes())),
    )
    identity = ArtifactAdapterIdentity(f"harness.{plan.provider_id.value}.mcp", "1.0.0",
                                       plan.provider_id, "1.0.0", ())
    return plan_artifact_render(ArtifactRenderRequest(
        f"harness.{plan.provider_id.value}.mcp." + ".".join(server_id for server_id, _ in plan.servers),
        sources,
        ArtifactTarget(plan.target_path, ("whole-file", ())), identity, (),
        {"target_scope": plan.target_scope, "server_ids": [server_id for server_id, _ in plan.servers],
         "secret_refs": list(plan.secret_refs)},
        lambda _request: render_mcp_projection(plan)))


def render_mcp_projection(plan: McpProjection) -> bytes:
    """Serialize only the named projection.  Claude retains its merge-only writer."""
    if plan.provider_id in (ProviderId.CLAUDE_CODE, ProviderId.CURSOR):
        return (json.dumps({"mcpServers": dict(plan.servers)}, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    lines = []
    for server_id, binding in plan.servers:
        lines.append(f"[mcp_servers.{server_id}]")
        for field in ("url", "command"):
            if field in binding:
                lines.append(f'{field} = {json.dumps(binding[field], ensure_ascii=False)}')
        if "args" in binding:
            lines.append("args = " + json.dumps(binding["args"], ensure_ascii=False))
        if "env" in binding:
            env = binding["env"]
            lines.append("env = {" + ", ".join(
                f"{json.dumps(key, ensure_ascii=False)} = {json.dumps(value, ensure_ascii=False)}"
                for key, value in sorted(env.items())) + "}")
        lines.append("")
    return ("\n".join(lines)).encode("utf-8")
