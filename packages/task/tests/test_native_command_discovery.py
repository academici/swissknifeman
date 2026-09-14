"""Native Codex install must not auto-migrate parameterized Task source commands."""
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
    def test_fresh_native_install_discovers_only_the_eleven_task_adapters(self):
        # An isolated home and local marketplace exercise the provider installer;
        # no credentials, user configuration, existing caches or network are needed.
        with tempfile.TemporaryDirectory(prefix="task-native-discovery-") as folder:
            root = Path(folder)
            marketplace = root / "marketplace"
            plugin = marketplace / "task"
            plugin.mkdir(parents=True)
            for directory in (".codex-plugin", ".claude-plugin", "commands", "adapters/codex/skills"):
                shutil.copytree(ROOT / "packages/task" / directory, plugin / directory)
            manifest = marketplace / ".agents/plugins/marketplace.json"
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps({"name": "task-discovery-test", "plugins": [{
                "name": "task", "source": "./task", "description": "Task discovery test",
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
            result = run("plugin", "add", "task@task-discovery-test", "--json")
            installed = Path(result["installedPath"])
            migrated = installed / ".codex-plugin/migrated-command-skills"
            self.assertEqual(list(migrated.glob("*/SKILL.md")), [])
            messages = run("debug", "prompt-input")
            text = "\n".join(block.get("text", "") for message in messages
                             for block in message.get("content", []))
            identities = re.findall(r"^- task:([^:]+):", text, re.MULTILINE)
            expected = {"task-" + path.stem for path in (plugin / "commands").glob("*.md")}
            self.assertEqual(set(identities), expected)
            self.assertEqual(len(identities), 11)
