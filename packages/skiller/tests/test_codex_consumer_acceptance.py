"""P5.5: isolated Codex publication consumer-acceptance gate.

Azguard, 2026-07-21 — internal generator/unit checks were GREEN, but a fresh Codex
session could not install the sibling `task` plugin from native marketplace discovery.
Static schema conformance
(`test_codex_publication.py`) does not catch that class of failure — it never
asks the real `codex` binary anything. This module does: everything here drives
the external `codex` CLI itself, from an isolated `CODEX_HOME` and a consumer
directory OUTSIDE the repo — `test_repo_local_skills_would_mask_a_real_publication_failure`
proves why the consumer directory can never be the repo root (this repo's own
`.agents/skills` auto-loads regardless of marketplace install and would silently
hide exactly the failure this gate exists to catch).
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE_ROOT = REPO_ROOT / "packages" / "skiller"
CODEX_BIN = shutil.which("codex")


def _run_codex(args, *, codex_home, cwd, timeout=60):
    env = dict(os.environ)
    env["CODEX_HOME"] = str(codex_home)
    return subprocess.run([CODEX_BIN, *args], capture_output=True, text=True,
                          cwd=str(cwd), env=env, timeout=timeout)


def _expected_codex_plugin_names(repo_root, package_root):
    """Independent inventory: raw disk/config reads only — never
    `skiller.publication.render_codex_publication` or its input-gathering
    functions. A gate that sourced its own expectation from the code under test
    would be green on nothing (Scope Included item 1)."""
    buckets_meta = json.loads((package_root / "buckets.json").read_text(encoding="utf-8"))
    names = set()
    for bucket_dir in sorted(p for p in (package_root / "skills").iterdir() if p.is_dir()):
        if buckets_meta.get(bucket_dir.name, {}).get("private_source_only"):
            continue
        if any(bucket_dir.rglob("SKILL.md")):
            names.add(bucket_dir.name)
    names.add("generate-skill")
    core_policy = json.loads(
        (package_root / "configs" / "core-policy.json").read_text(encoding="utf-8"))
    if core_policy.get("skills"):
        names.add(core_policy["core_plugin"])
    if (package_root / "skm" / ".claude-plugin" / "plugin.json").is_file():
        names.add("skm")
    for pkg_dir in sorted((repo_root / "packages").iterdir()):
        if pkg_dir == package_root or not pkg_dir.is_dir():
            continue
        claude_manifest = pkg_dir / ".claude-plugin" / "plugin.json"
        codex_manifest = pkg_dir / ".codex-plugin" / "plugin.json"
        if claude_manifest.is_file() and codex_manifest.is_file():
            data = json.loads(codex_manifest.read_text(encoding="utf-8"))
            names.add(data.get("name", pkg_dir.name))
    return names


def assert_codex_inventory_matches(expected_names, actual_names):
    """The comparison the live gate runs — factored out so its RED path (Scope
    Included item 5: export-surface drift without a version bump) is unit-testable
    without needing a live `codex` binary at all."""
    missing = expected_names - actual_names
    extra = actual_names - expected_names
    if missing or extra:
        raise AssertionError(
            f"Codex publication export surface drifted from the independent "
            f"expected inventory — missing from native marketplace: {sorted(missing)}, "
            f"unexpected in native marketplace: {sorted(extra)}")


def resolve_skill_reference(instructions: str, value: str) -> str:
    """Resolve current Codex ``rN/path`` display aliases to their filesystem path."""
    roots = dict(re.findall(r"^- `(r\d+)` = `([^`]+)`$", instructions, re.MULTILINE))
    match = re.fullmatch(r"(r\d+)(/.*)?", value)
    if match is None:
        return value
    root = roots.get(match.group(1))
    if root is None:
        raise AssertionError(f"unknown Codex skill-root alias: {value}")
    return str(Path(root) / (match.group(2) or "").lstrip("/"))


def listed_skill_paths(instructions: str) -> set[str]:
    return {
        resolve_skill_reference(instructions, value)
        for value in re.findall(r"\(file: (\S+)\)", instructions)
    }


class InventoryDriftDetectionCase(unittest.TestCase):
    """Negative fixture (Validation item 3): a live plugin absent from the actual
    marketplace listing, or an actual plugin absent from the expected inventory,
    must red the gate. Runs without `codex` — it exercises the comparison
    function the live gate calls, not the CLI round-trip itself."""

    def test_plugin_missing_from_native_listing_is_red(self):
        expected = {"task", "ai", "generate-skill"}
        actual_missing_task = {"ai", "generate-skill"}
        with self.assertRaises(AssertionError):
            assert_codex_inventory_matches(expected, actual_missing_task)

    def test_unexpected_plugin_in_native_listing_is_red(self):
        expected = {"ai", "generate-skill"}
        actual_with_extra = {"ai", "generate-skill", "surprise-plugin"}
        with self.assertRaises(AssertionError):
            assert_codex_inventory_matches(expected, actual_with_extra)

    def test_matching_inventories_are_green(self):
        names = {"ai", "generate-skill", "task"}
        assert_codex_inventory_matches(names, set(names))


@unittest.skipUnless(CODEX_BIN, "codex CLI не найден в PATH — consumer-acceptance гейт пропущен "
                                "(SKIP, не GREEN: гейт не прогонялся)")
class TestCodexConsumerAcceptance(unittest.TestCase):
    """Isolated `CODEX_HOME` → real `codex` CLI → clean temp-consumer discovery.
    Package-level GREEN elsewhere in this suite is not release GREEN until this
    class also passes."""

    @classmethod
    def setUpClass(cls):
        # The operator's REAL ~/.codex may already carry an independently-installed
        # `swissknifeman`/`task` plugin (their own daily driver) — that pre-existing
        # state is none of this gate's business. What the gate must prove is narrower:
        # that ITS OWN round-trip below never writes there. Snapshot the one path our
        # own install below would collide with, before touching anything.
        real_task_cache = Path.home() / ".codex" / "plugins" / "cache" / "swissknifeman" / "task"
        cls._real_task_cache_mtime_before = (
            real_task_cache.stat().st_mtime_ns if real_task_cache.exists() else None)

        cls.tmp = tempfile.TemporaryDirectory(prefix="codex-consumer-acceptance-")
        tmp_path = Path(cls.tmp.name)
        cls.codex_home = (tmp_path / "codex_home").resolve()
        cls.codex_home.mkdir()
        cls.consumer_dir = (tmp_path / "consumer").resolve()
        cls.consumer_dir.mkdir()

        version_result = subprocess.run([CODEX_BIN, "--version"], capture_output=True,
                                        text=True, timeout=30)
        cls.codex_version = version_result.stdout.strip()

        add_result = _run_codex(["plugin", "marketplace", "add", str(REPO_ROOT), "--json"],
                                codex_home=cls.codex_home, cwd=cls.consumer_dir)
        if add_result.returncode != 0:
            raise unittest.SkipTest(
                f"codex plugin marketplace add провалился (живая версия {cls.codex_version} "
                f"могла сменить контракт): {add_result.stderr.strip()}")
        cls.marketplace_add = json.loads(add_result.stdout)

        list_result = _run_codex(
            ["plugin", "list", "--marketplace", "swissknifeman", "--available", "--json"],
            codex_home=cls.codex_home, cwd=cls.consumer_dir)
        assert list_result.returncode == 0, list_result.stderr
        cls.marketplace_listing = json.loads(list_result.stdout)

        install_result = _run_codex(["plugin", "add", "task@swissknifeman", "--json"],
                                    codex_home=cls.codex_home, cwd=cls.consumer_dir)
        assert install_result.returncode == 0, install_result.stderr
        cls.task_install = json.loads(install_result.stdout)

        blender_result = _run_codex(["plugin", "add", "blender@swissknifeman", "--json"],
                                    codex_home=cls.codex_home, cwd=cls.consumer_dir)
        assert blender_result.returncode == 0, blender_result.stderr
        cls.blender_install = json.loads(blender_result.stdout)

        installed_result = _run_codex(["plugin", "list", "--json"],
                                      codex_home=cls.codex_home, cwd=cls.consumer_dir)
        assert installed_result.returncode == 0, installed_result.stderr
        cls.installed_listing = json.loads(installed_result.stdout)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @staticmethod
    def _skills_instructions_text(prompt_input):
        for message in prompt_input:
            for block in message.get("content", []):
                text = block.get("text", "")
                if "<skills_instructions>" in text:
                    return text
        raise AssertionError("prompt-input carries no <skills_instructions> block")

    def test_expected_inventory_matches_native_marketplace_listing(self):
        expected = _expected_codex_plugin_names(REPO_ROOT, PACKAGE_ROOT)
        actual = {item["name"] for item in self.marketplace_listing["available"]}
        assert_codex_inventory_matches(expected, actual)

    def test_marketplace_source_and_plugin_paths_conform_to_native_schema(self):
        self.assertTrue(self.marketplace_listing["available"])
        for item in self.marketplace_listing["available"]:
            self.assertEqual(item["marketplaceName"], "swissknifeman")
            source = item["source"]
            self.assertEqual(source["source"], "local")
            self.assertTrue(Path(source["path"]).is_dir(), source["path"])

    def test_isolated_install_populates_cache_without_touching_user_codex_home(self):
        real_task_cache = Path.home() / ".codex" / "plugins" / "cache" / "swissknifeman" / "task"
        after = real_task_cache.stat().st_mtime_ns if real_task_cache.exists() else None
        self.assertEqual(after, self._real_task_cache_mtime_before,
                         "consumer-acceptance install touched the user's real ~/.codex "
                         "plugin cache — CODEX_HOME isolation failed")
        installed_path = Path(self.task_install["installedPath"])
        self.assertTrue(installed_path.is_relative_to(self.codex_home), installed_path)
        for skill_name in ("task-plan-run", "task-plan-exec"):
            cached = installed_path / "adapters" / "codex" / "skills" / skill_name / "SKILL.md"
            source = REPO_ROOT / "packages" / "task" / "adapters" / "codex" / "skills" / \
                skill_name / "SKILL.md"
            self.assertTrue(cached.is_file(), cached)
            self.assertEqual(cached.read_bytes(), source.read_bytes())

    def test_isolated_task_install_is_registered_with_its_exact_cache(self):
        entries = [entry for entry in self.installed_listing["installed"]
                   if entry.get("name") == "task" and entry.get("marketplaceName") == "swissknifeman"]
        self.assertEqual(len(entries), 1, entries)
        entry = entries[0]
        self.assertTrue(entry["installed"])
        self.assertTrue(entry["enabled"])
        self.assertEqual(entry["version"], self.task_install["version"])
        self.assertEqual(Path(entry["source"]["path"]), REPO_ROOT / "packages/task")
        self.assertEqual(Path(self.task_install["installedPath"]),
                         self.codex_home / "plugins/cache/swissknifeman/task" / entry["version"])

    def test_isolated_bucket_install_is_registered_with_its_exact_cache(self):
        entries = [entry for entry in self.installed_listing["installed"]
                   if entry.get("name") == "blender" and entry.get("marketplaceName") == "swissknifeman"]
        self.assertEqual(len(entries), 1, entries)
        entry = entries[0]
        self.assertTrue(entry["installed"])
        self.assertTrue(entry["enabled"])
        self.assertEqual(entry["version"], self.blender_install["version"])
        installed_path = Path(self.blender_install["installedPath"])
        self.assertTrue(installed_path.is_relative_to(self.codex_home), installed_path)
        for skill_name in ("mcp-blender", "version-gotchas"):
            cached = installed_path / skill_name / "SKILL.md"
            source = REPO_ROOT / "packages/skiller/skills/blender" / skill_name / "SKILL.md"
            self.assertTrue(cached.is_file(), cached)
            self.assertEqual(cached.read_bytes(), source.read_bytes())

    def test_repo_local_skills_would_mask_a_real_publication_failure(self):
        """Reproduces the Azguard failure mode directly: run the SAME isolated
        CODEX_HOME from the repo root instead of the temp consumer dir, and show
        this repo's own `.agents/skills` leaks into discovery regardless of what
        is or is not actually installed. This is exactly why every other test in
        this class uses `consumer_dir`, never `REPO_ROOT`, as `cwd`."""
        repo_local_marker = REPO_ROOT / ".agents" / "skills" / "package-architecture" / "SKILL.md"
        self.assertTrue(repo_local_marker.is_file())
        result = _run_codex(["debug", "prompt-input"], codex_home=self.codex_home,
                            cwd=REPO_ROOT)
        self.assertEqual(result.returncode, 0, result.stderr)
        text = self._skills_instructions_text(json.loads(result.stdout))
        self.assertIn(str(repo_local_marker), listed_skill_paths(text))


if __name__ == "__main__":
    unittest.main()
