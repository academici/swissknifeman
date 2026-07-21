import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness/lib"))

from core import ProviderId
from harness.mcp import load_mcp_catalog, plan_mcp_projection
from maind.provider_deploy import plan_provider_deploy, semantic_servers


class TestProviderDeploy(unittest.TestCase):
    def test_caller_owned_semantics_use_p5_targets_and_renderers(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        servers = semantic_servers(maind={"command": "maind"},
            codegraph={"command": "uvx", "args": ["serena"]},
            perplexity={"command": "pplx"})
        plan = plan_provider_deploy(bases, servers)
        self.assertTrue(plan.green)
        self.assertEqual([row.target_path for row in plan.results], [".mcp.json", ".codex/config.toml"])
        self.assertTrue(all(b"maind" in row.rendered and b"codegraph" in row.rendered
                            for row in plan.results))


if __name__ == "__main__":
    unittest.main()
