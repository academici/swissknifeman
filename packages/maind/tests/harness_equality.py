"""Scenarios whose provider-file bytes and lock records must not change when the harness link moves.

Each scenario builds a temporary project, runs the public maind deploy path and returns every file
it wrote (bytes as text) plus the lock. ``fixtures/harness-link-before-v1.json`` holds the capture
taken from the in-process harness link; ``test_harness_link_equality.py`` compares the current
behaviour against it. The scenarios take the entry points that changed signature as arguments, so
the same code ran before and after the change."""
import json
import tempfile
from pathlib import Path

from maind.config import merge_defaults
from maind.provider_deploy import SemanticServer, apply_d108_operation
from maind.provision import deploy
from tests.fixtures import make_repo

D104_PREIMAGE = b'''{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash /srv/project/.claude/maind-memory.sh"
          }
        ]
      }
    ]
  }
}
'''

# The D108 preimage is sealed by hash, so its machine-specific paths cannot change; this file is listed in
# ``CONTENT_EXEMPT`` of scripts/public-hygiene.py for that reason, and the fixture holds the token below instead.
PINNED_PACKAGES = "/home/vostrikov/projects/packages"
PINNED_TOKEN = "@PINNED_PACKAGES@"

_D108_MCP_PREIMAGE_TEMPLATE = b'''{
  "mcpServers": {
    "maind": {
      "command": "${MAIND_BIN:-maind}",
      "args": [
        "mcp",
        "--scope",
        "project:swissknifeman"
      ]
    },
    "perplexity-web": {
      "command": "${PERPLEXITY_WEB_MCP_BIN:-@PINNED_PACKAGES@/perplexity-web-mcp/start.sh}",
      "args": [
        "--pool=default"
      ]
    },
    "serena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server",
        "--context",
        "ide-assistant",
        "--project",
        "@PINNED_PACKAGES@/swissknifeman",
        "--enable-web-dashboard",
        "false"
      ]
    }
  }
}
'''

D108_MCP_PREIMAGE = _D108_MCP_PREIMAGE_TEMPLATE.replace(PINNED_TOKEN.encode(), PINNED_PACKAGES.encode())

PROVIDER_SETS = {
    "claude-codex": ("claude-code", "codex"),
    "cursor": ("claude-code", "cursor"),
    "grok": ("claude-code", "grok"),
    "all": ("claude-code", "codex", "cursor", "grok"),
}


def tree(root):
    """Every file under ``root`` except backups, as ``{relative path: text}``."""
    root = Path(root)
    return {str(path.relative_to(root)): path.read_bytes().decode("utf-8", "surrogateescape")
            for path in sorted(root.rglob("*"))
            if path.is_file() and ".bak" not in path.name and "backups" not in path.parts}


def _project(tmp, pid, providers):
    path = Path(tmp) / "proj" / pid
    path.mkdir(parents=True)
    selection = {name: {"enabled": True} for name in providers}
    (path / ".swissknife.json").write_text(json.dumps(
        {"providers": {"contract_version": "1.0.0", "selection": selection}}), encoding="utf-8")
    config = merge_defaults({"projects": [{
        "id": pid, "name": pid.title(), "local_path": str(path),
        "memory_scope": f"project:{pid}"}]})
    return path, config


def deploy_scenario(label):
    """Deploy twice into a project that selects the named provider set; return both trees."""
    with tempfile.TemporaryDirectory() as tmp:
        _, env = make_repo(tmp)
        path, config = _project(tmp, "flexcrm", PROVIDER_SETS[label])
        project = config["projects"][0]
        context = deploy.provider_projection_context(env, config, project)
        first = deploy.deploy_project(env, config, project, with_code=False,
                                      provider_projections=context.projections)
        after_first = tree(path)
        second = deploy.deploy_project(env, config, project, with_code=False,
                                       provider_projections=context.projections)
        return {"providers": [item.value for item in context.providers],
                "first_targets": first["targets"], "first_changed": first["provider_changed"],
                "second_changed": second["provider_changed"],
                "files": after_first, "files_after_second": tree(path)}


def d104_scenario(plan_transfer):
    """Plan, apply and describe the D104 bootstrap transfer of a Codex hooks document."""
    from aicore.artifacts.lock import apply_plan
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".codex/hooks").mkdir(parents=True)
        (root / ".codex/hooks.json").write_bytes(D104_PREIMAGE)
        transfer = plan_transfer(root)
        planned = [[action.action.value, action.target_path] for action in transfer.plan.actions]
        sources = [[source.source_id, source.path, source.content_hash]
                   for source in transfer.artifacts[0].provenance.canonical_sources]
        apply_plan(root, transfer.plan)
        return {"actions": planned, "sources": sources,
                "managed_post_apply": transfer.managed_post_apply, "files": tree(root)}


def d108_scenario(plan_operation):
    """Plan and apply the sealed D108 operation on a project with the frozen preimages."""
    servers = (SemanticServer("maind", {"command": "maind"}),
               SemanticServer("perplexity-web", {"command": "pplx"}),
               SemanticServer("serena", {"command": "serena"}))
    config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".codex").mkdir()
        (root / ".codex/hooks.json").write_bytes(D104_PREIMAGE.replace(
            b"/srv/project/.claude/maind-memory.sh",
            PINNED_PACKAGES.encode() + b"/swissknifeman/.claude/maind-memory.sh"))
        (root / ".mcp.json").write_bytes(D108_MCP_PREIMAGE)
        operation = plan_operation(root, config, "swissknifeman", servers)
        planned = [[action.action.value, action.target_path] for action in operation.chained_plan.actions]
        apply_d108_operation(root, operation)
        return {"actions": planned, "carrier": operation.carrier.path.name,
                "files": tree(root)}


def conformance_scenario(generate):
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "report.md"
        generate(output)
        return {"report": output.read_text(encoding="utf-8")}
