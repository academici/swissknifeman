"""The memory hook finds the topology and the project registry in the owner's state file first, in the legacy file next."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

COMMON = Path(__file__).resolve().parents[1] / "configs" / "claude-code" / "hooks" / "memory" / "lib" / "common.sh"


def topology(home, env_extra=None):
    env = {key: value for key, value in os.environ.items() if key not in ("SKM_HOME", "XDG_STATE_HOME")}
    env.update(HOME=str(home), **(env_extra or {}))
    done = subprocess.run(["bash", "-c", f'source "{COMMON}" 2>/dev/null; printf "%s|" "$MEM_TOPO"; topo_node_path brain'],
                          env=env, capture_output=True, text=True)
    return done.stdout.strip()


class MemoryRegistryLadderTests(unittest.TestCase):
    def setUp(self):
        if subprocess.run(["bash", "-c", "command -v jq"], capture_output=True).returncode != 0:
            self.skipTest("jq is needed by the memory hook")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = Path(self._tmp.name)

    def write(self, path, node):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"nodes": {"brain": {"path": node}}}), encoding="utf-8")

    def test_the_owner_state_file_is_used_first(self):
        self.write(self.home / ".local/state/swissknifeman/maind/topology.json", "/owner/brain")
        self.write(self.home / ".swissknifeman/topology.json", "/legacy/brain")
        self.assertTrue(topology(self.home).endswith("|/owner/brain"), topology(self.home))

    def test_the_legacy_file_is_the_fallback_while_it_is_the_only_one(self):
        self.write(self.home / ".swissknifeman/topology.json", "/legacy/brain")
        self.assertTrue(topology(self.home).endswith("|/legacy/brain"))

    def test_skm_home_moves_the_lookup_and_switches_the_legacy_one_off(self):
        self.write(self.home / ".swissknifeman/topology.json", "/legacy/brain")
        out = topology(self.home, {"SKM_HOME": str(self.home / "skm")})
        self.assertTrue(out.startswith(str(self.home / "skm" / "state" / "maind" / "topology.json") + "|"), out)
        self.assertFalse(out.endswith("/legacy/brain"))


if __name__ == "__main__":
    unittest.main()
