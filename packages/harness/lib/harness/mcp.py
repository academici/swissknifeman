"""Internal documentation."""
import json
from pathlib import Path

from aicore.artifacts.artifact import ArtifactSource, sha256_digest
from aicore.provider import mcp as projection
from aicore.provider.mcp import (McpProjection, McpServer, parse_mcp_catalog,
                                 render_mcp_projection)
from aicore.provider.values import ProviderId

from aicore.util.cli import parse_flags
from aicore.util.term import die, warn
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
    if argv and argv[0] == "catalog":
        return cmd_mcp_catalog(env, argv[1:])
    opts = parse_flags(argv, {
        "--target": "str", "--mcp": "str", "--list": "bool", "--dry-run": "bool",
    })
    if opts["help"]:
        print("harness mcp [--target P] [--mcp name1,name2] [--list] [--dry-run]\n"
              "harness mcp catalog --json [--provider ID]")
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


# The projection itself is pure and lives in aicore.provider.mcp; this module keeps the Claude
# merge/write CLI above and the harness-owned catalog locations below (they are lock data).
_CATALOG_LABEL = "harness.mcp.catalog"
_CATALOG_RELPATH = "packages/harness/configs/common/mcp/catalog.json"


def load_mcp_catalog(path: Path) -> tuple[McpServer, ...]:
    """Load the common, value-free MCP inventory in its declared order."""
    return parse_mcp_catalog(json.loads(Path(path).read_text(encoding="utf-8")))


def plan_mcp_projection(catalog: tuple[McpServer, ...], *, provider_id: ProviderId,
                        bindings_path: Path, selected: tuple[str, ...], trusted: bool) -> McpProjection:
    """Return one independent native projection, without writing a target or lock."""
    if not trusted:
        raise ValueError("HARNESS_TRUST_REQUIRED")
    return projection.plan_mcp_projection(
        catalog, provider_id=provider_id,
        bindings=json.loads(Path(bindings_path).read_text(encoding="utf-8")),
        selected=selected, trusted=trusted)


def mcp_sources(provider_id: ProviderId, *, catalog_path: Path, bindings_path: Path):
    """The catalog and bindings records a Codex/Cursor/Grok MCP artifact is locked against."""
    name = provider_id.value
    return (
        ArtifactSource(_CATALOG_LABEL, _CATALOG_RELPATH,
                       sha256_digest(Path(catalog_path).read_bytes())),
        ArtifactSource(f"harness.{name}.mcp-bindings",
                       f"packages/harness/configs/{name}/mcp/bindings.json",
                       sha256_digest(Path(bindings_path).read_bytes())),
    )


def plan_mcp_artifact(plan: McpProjection, *, catalog_path: Path, bindings_path: Path):
    """Codex/Cursor/Grok MCP is a whole-file artifact; Claude keeps its merge-only writer."""
    return projection.plan_mcp_artifact(
        plan, sources=mcp_sources(plan.provider_id, catalog_path=catalog_path,
                                  bindings_path=bindings_path),
        adapter_id=f"harness.{plan.provider_id.value}.mcp")


MCP_CATALOG_SCHEMA = "urn:swissknifeman:harness:mcp-catalog:v1"


def _source_record(source: ArtifactSource) -> dict:
    return {"id": source.source_id, "path": source.path, "sha256": source.content_hash}


def mcp_catalog_document(configs: Path, provider_ids=None) -> dict:
    """The catalog, per-provider bindings and lock source records, as one JSON document."""
    configs = Path(configs)
    catalog_path = configs / "common" / "mcp" / "catalog.json"
    parse_mcp_catalog(json.loads(catalog_path.read_text(encoding="utf-8")))
    available = sorted(path.parent.parent.name for path in configs.glob("*/mcp/bindings.json"))
    wanted = available if provider_ids is None else list(provider_ids)
    unknown = sorted(set(wanted) - set(available))
    if unknown:
        raise ValueError(f"HARNESS_MAPPING_MISSING: no MCP bindings for {', '.join(unknown)}")
    document = {"$schema": MCP_CATALOG_SCHEMA,
                "catalog": json.loads(catalog_path.read_text(encoding="utf-8")),
                "bindings": {}, "sources": {"bindings": {}}, "adapters": {}}
    for name in wanted:
        bindings_path = configs / name / "mcp" / "bindings.json"
        catalog_source, bindings_source = mcp_sources(
            ProviderId(name), catalog_path=catalog_path, bindings_path=bindings_path)
        document["bindings"][name] = json.loads(bindings_path.read_text(encoding="utf-8"))
        document["sources"]["catalog"] = _source_record(catalog_source)
        document["sources"]["bindings"][name] = _source_record(bindings_source)
        document["adapters"][name] = f"harness.{name}.mcp"
    return document


def cmd_mcp_catalog(env, argv):
    """`harness mcp catalog --json [--provider ID]` — data for a consumer that renders MCP itself."""
    opts = parse_flags(argv, {"--json": "bool", "--provider": "str"})
    if opts["help"]:
        print("harness mcp catalog --json [--provider ID]")
        return
    if not opts["json"]:
        die("harness mcp catalog needs --json")
    try:
        document = mcp_catalog_document(Path(env.root) / "configs",
                                        [opts["provider"]] if opts["provider"] else None)
    except (ValueError, OSError) as error:
        die(str(error))
    print(json.dumps(document, ensure_ascii=False))
