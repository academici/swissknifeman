"""Native Codex install must not auto-migrate parameterized planner source commands."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[3]
CODEX = shutil.which("codex")


@unittest.skipUnless(CODEX, "native Codex discovery requires the installed CLI")
class NativeCommandDiscoveryTests(unittest.TestCase):
    def test_fresh_native_install_keeps_planner_out_of_idle_prompt(self):
        # An isolated home and local marketplace exercise the provider installer;
        # no credentials, user configuration, existing caches or network are needed.
        with tempfile.TemporaryDirectory(prefix="planner-native-discovery-") as folder:
            root = Path(folder)
            marketplace = root / "marketplace"
            plugin = marketplace / "planner"
            plugin.mkdir(parents=True)
            for directory in (".codex-plugin", ".claude-plugin", "commands", "adapters/codex/skills"):
                shutil.copytree(ROOT / "packages/planner" / directory, plugin / directory)
            manifest = marketplace / ".agents/plugins/marketplace.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"name": "planner-discovery-test", "plugins": [{
                "name": "planner", "source": "./planner", "description": "planner discovery test",
                "install_policy": "explicit", "auth": "none"}]}))
            home = root / "codex-home"
            home.mkdir()
            cwd = root / "project"
            cwd.mkdir()
            environment = {**os.environ, "CODEX_HOME": str(home)}

            def run(*arguments):
                result = subprocess.run([CODEX, *arguments], cwd=cwd, env=environment,
                                        capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)

            run("plugin", "marketplace", "add", str(marketplace), "--json")
            result = run("plugin", "add", "planner@planner-discovery-test", "--json")
            installed = Path(result["installedPath"])
            migrated = installed / ".codex-plugin/migrated-command-skills"
            self.assertEqual(list(migrated.glob("*/SKILL.md")), [])
            messages = run("debug", "prompt-input")
            text = "\n".join(block.get("text", "") for message in messages
                             for block in message.get("content", []))
            identities = re.findall(r"^- planner:([^:]+):", text, re.MULTILINE)
            expected = {"planner-" + path.stem for path in (plugin / "commands").glob("*.md")}
            self.assertEqual(identities, [])
            skills = installed / "adapters/codex/skills"
            self.assertEqual({path.parent.name for path in skills.glob("*/SKILL.md")}, expected)
            for policy in skills.glob("*/agents/openai.yaml"):
                self.assertIn("allow_implicit_invocation: false", policy.read_text())
