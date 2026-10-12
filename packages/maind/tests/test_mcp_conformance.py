"""Conformance of the stdlib MCP server against the official Python SDK client.

Skipped when the SDK is not installed (optional dev dependency, see requirements-dev.txt).
The server runs by the command a project `.mcp.json` carries (`bin/maind mcp`), with a temporary
HOME and no memory daemon."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError:
    raise unittest.SkipTest("official MCP SDK not installed")

from maind import mcp as server

REPO = Path(__file__).resolve().parents[1]


def _params(tmp):
    root = Path(tmp) / "node"
    (root / "config" / "memory").mkdir(parents=True)
    (root / "config.json").write_text(
        json.dumps({"_version": "1", "projects": [{"id": "x", "name": "X"}]}), encoding="utf-8")
    home = Path(tmp) / "home"
    home.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SKM_", "MAIND_"))}
    env.update({"HOME": str(home), "SKM_HOME": str(home / "skm"), "MAIND_ROOT": str(root)})
    return StdioServerParameters(command=str(REPO / "bin" / "maind"),
                                 args=["mcp"], env=env, cwd=str(root))


async def _session(tmp, scenario):
    async with stdio_client(_params(tmp)) as (read, write):
        async with ClientSession(read, write) as session:
            return await scenario(session)


class TestConformance(unittest.TestCase):
    def run_scenario(self, scenario):
        with tempfile.TemporaryDirectory() as tmp:
            return asyncio.run(asyncio.wait_for(_session(tmp, scenario), timeout=60))

    def test_initialize_negotiates_a_supported_version(self):
        async def scenario(session):
            return await session.initialize()
        result = self.run_scenario(scenario)
        self.assertIn(result.protocolVersion, server.SUPPORTED_PROTOCOL_VERSIONS)
        self.assertEqual(result.serverInfo.name, "maind")

    def test_list_tools_matches_server_list(self):
        async def scenario(session):
            await session.initialize()
            return await session.list_tools()
        listed = self.run_scenario(scenario)
        self.assertEqual([t.name for t in listed.tools], [t["name"] for t in server.TOOLS])

    def test_safe_tool_call_returns_a_result(self):
        async def scenario(session):
            await session.initialize()
            return await session.call_tool("maind_projects_list", {})
        result = self.run_scenario(scenario)
        self.assertTrue(result.content)
        self.assertIsInstance(json.loads(result.content[0].text), list)


if __name__ == "__main__":
    unittest.main()
