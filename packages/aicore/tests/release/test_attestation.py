"""Version identity is tied to delivered bytes, including the historical incident."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from aicore.release.attestation import (Source, build, check, check_transition, surface,
                                        tree_digest, version_errors)
import subprocess
import tempfile


def _git(root, *args):
    subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid", *args],
                   cwd=root, check=True, capture_output=True)


def _write(root, relative, value):
    path = Path(root) / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")


PLUGIN_A = {"version_owner": "umbrella", "grok_native": True,
            "required_providers": ["claude-code", "codex", "grok"]}
PLUGIN_B = {"version_owner": "package", "package": "plugin-b", "path": "vendor/plugin-b",
            "required_providers": ["claude-code"]}


def _host_repo(root, policy):
    """Synthetic host: a commands plugin (plugin-a) and a package-owned plugin (plugin-b)."""
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    _write(root, "CHANGELOG.md", "# Changelog\n\n## [1.2.0] - 2026-01-02\n- entry\n")
    _write(root, ".agents/plugins/marketplace.json", {"plugins": [
        {"name": "plugin-a", "source": "./vendor/plugin-a"}]})
    _write(root, ".claude-plugin/marketplace.json", {"plugins": [
        {"name": "plugin-a", "source": "vendor/plugin-a"},
        {"name": "plugin-b", "source": "vendor/plugin-b"}]})
    _write(root, "vendor/plugin-a/.codex-plugin/plugin.json", {"version": "1.2.0", "skills": "./skills"})
    _write(root, "vendor/plugin-a/.claude-plugin/plugin.json", {"version": "1.2.0", "commands": "./commands"})
    _write(root, "vendor/plugin-a/skills/run/SKILL.md", "run\n")
    _write(root, "vendor/plugin-a/commands/run.md", "run\n")
    _write(root, "vendor/plugin-b/.claude-plugin/plugin.json", {"version": "0.3.0", "commands": "./commands"})
    _write(root, "vendor/plugin-b/commands/go.md", "go\n")
    _write(root, "vendor/plugin-b/package.json", {"version": "0.3.0"})
    _write(root, "vendor/plugin-b/lib/module.py", "pass\n")
    if policy is not None:
        _write(root, "configs/release-units.json", policy)


def _policy(**extra):
    value = {"schema_version": "release-unit-policy/v1",
             "plugins": {"plugin-a": dict(PLUGIN_A), "plugin-b": dict(PLUGIN_B)},
             "default_plugin_version_owner": "skiller-publication-map"}
    value.update(extra)
    return value


class HostPolicyBuildTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def units(self, value):
        return {unit["id"]: unit for unit in value["units"]}

    def test_grok_native_flag_adds_grok_surface_and_package_path_owns_version(self):
        _host_repo(self.root, _policy(package_units={"plugin-b": "vendor/plugin-b"}))
        units = self.units(build(self.root))
        self.assertEqual(set(units["plugin-a"]["providers"]),
                         {"codex", "codex-native", "grok", "claude-code"})
        self.assertEqual(set(units["plugin-a"]["providers"]["grok"]["files"]),
                         {"commands/run.md", ".claude-plugin/plugin.json"})
        self.assertNotIn("grok", units["plugin-b"]["providers"])
        self.assertEqual((units["plugin-b"]["expected_version"], units["plugin-b"]["version_source"]),
                         ("0.3.0", "vendor/plugin-b/package.json"))
        self.assertEqual(units["package.plugin-b"]["version_source"], "vendor/plugin-b/package.json")
        self.assertEqual(set(units["package.plugin-b"]["providers"]["runtime"]["files"]),
                         {"lib/module.py", "package.json"})

    def test_without_grok_native_there_is_no_grok_surface(self):
        policy = _policy()
        del policy["plugins"]["plugin-a"]["grok_native"]
        _host_repo(self.root, policy)
        self.assertNotIn("grok", self.units(build(self.root))["plugin-a"]["providers"])

    def test_package_owner_without_path_fails_closed(self):
        policy = _policy()
        del policy["plugins"]["plugin-b"]["path"]
        _host_repo(self.root, policy)
        with self.assertRaisesRegex(ValueError, "RELEASE_UNIT_POLICY_INVALID: plugin-b: path missing"):
            build(self.root)

    def test_historical_ref_without_policy_uses_worktree_legacy_policy(self):
        _host_repo(self.root, None)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "historical")
        legacy = _policy()
        _write(self.root, "configs/release-units.json",
               _policy(legacy_policy=legacy, package_units={"plugin-b": "vendor/plugin-b"}))
        value = build(self.root, ref="HEAD")
        self.assertIn("grok", self.units(value)["plugin-a"]["providers"])
        self.assertIn("package.plugin-b", self.units(value))
        self.assertEqual(value["version_policy"]["digest"], build(self.root, ref="HEAD")["version_policy"]["digest"])
        _write(self.root, "configs/release-units.json", _policy())
        with self.assertRaisesRegex(ValueError, "RELEASE_UNIT_POLICY_MISSING"):
            build(self.root, ref="HEAD")

    def test_historical_policy_without_layout_fields_takes_them_from_worktree(self):
        old = _policy()
        del old["plugins"]["plugin-a"]["grok_native"]
        del old["plugins"]["plugin-b"]["path"]
        _host_repo(self.root, old)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "policy before layout fields")
        _write(self.root, "configs/release-units.json", _policy())
        units = self.units(build(self.root, ref="HEAD"))
        self.assertIn("grok", units["plugin-a"]["providers"])
        self.assertEqual(units["plugin-b"]["version_source"], "vendor/plugin-b/package.json")

    def test_a_package_unit_added_after_a_historical_ref_is_left_out_of_it(self):
        _host_repo(self.root, _policy())
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "before the new package")
        _write(self.root, "configs/release-units.json",
               _policy(package_units={"plugin-b": "vendor/plugin-b", "later": "vendor/later"}))
        units = self.units(build(self.root, ref="HEAD"))
        self.assertIn("package.plugin-b", units)
        self.assertNotIn("package.later", units)  # it was a crash: git show HEAD:vendor/later/package.json
        _write(self.root, "vendor/later/package.json", {"version": "0.1.0"})
        _write(self.root, "vendor/later/lib/x.py", "pass\n")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "the new package")
        self.assertIn("package.later", self.units(build(self.root)))  # the worktree names its own units

    def test_invalid_schema_version_is_rejected(self):
        _host_repo(self.root, _policy(schema_version="release-unit-policy/v0"))
        with self.assertRaisesRegex(ValueError, "RELEASE_UNIT_POLICY_INVALID"):
            build(self.root)


class PackageRootTests(unittest.TestCase):
    """`package_root` names where the publication-version map and the package's own skills live in the host."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        policy = _policy()
        policy["plugins"]["plugin-a"] = {"version_owner": "skiller-publication-map"}
        _host_repo(self.root, policy)
        versions = {"default_unit_version": "9.9.9", "units": {"plugin-a": "1.2.0"}}
        _write(self.root, "packages/pub/configs/publication-versions.json", versions)
        _write(self.root, "configs/publication-versions.json",
               {"default_unit_version": "7.7.7", "units": {}})

    def version_source(self, **kwargs):
        unit = {u["id"]: u for u in build(self.root, **kwargs)["units"]}["plugin-a"]
        return unit["expected_version"], unit["version_source"]

    def test_publication_map_is_read_below_the_package_prefix(self):
        self.assertEqual(self.version_source(package_root=self.root / "packages/pub"),
                         ("1.2.0", "packages/pub/configs/publication-versions.json"))

    def test_without_package_root_the_prefix_is_empty(self):
        self.assertEqual(self.version_source(), ("7.7.7", "configs/publication-versions.json"))

    def test_package_outside_the_host_root_has_an_empty_prefix(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(self.version_source(package_root=Path(folder)),
                             ("7.7.7", "configs/publication-versions.json"))

    def test_package_that_is_the_host_root_has_an_empty_prefix(self):
        self.assertEqual(self.version_source(package_root=self.root),
                         ("7.7.7", "configs/publication-versions.json"))

    def test_package_skills_are_released_as_a_whole_tree(self):
        _write(self.root, ".claude-plugin/marketplace.json", {"plugins": [
            {"name": "plugin-a", "source": "vendor/plugin-a"},
            {"name": "plugin-b", "source": "vendor/plugin-b"},
            {"name": "skill-pack", "source": "packages/pub/skills/pack"}]})
        _write(self.root, "packages/pub/skills/pack/.claude-plugin/plugin.json", {"version": "1.2.0"})
        _write(self.root, "packages/pub/skills/pack/skill/SKILL.md", "skill\n")
        inside = {u["id"]: u for u in build(self.root, package_root=self.root / "packages/pub")["units"]}
        outside = {u["id"]: u for u in build(self.root)["units"]}
        self.assertEqual(set(inside["skill-pack"]["providers"]["claude-code"]["files"]),
                         {"skill/SKILL.md", ".claude-plugin/plugin.json"})
        self.assertNotIn("skill/SKILL.md", outside["skill-pack"]["providers"]["claude-code"]["files"])

    def test_check_passes_package_root_to_the_rebuild(self):
        package_root = self.root / "packages/pub"
        value = build(self.root, "v1.2.0", package_root=package_root)
        self.assertEqual(check(self.root, value, package_root=package_root), [])
        self.assertIn("RELEASE_SNAPSHOT_STALE", check(self.root, value))


class ReleaseAttestationTests(unittest.TestCase):
    def test_byte_consistent_snapshot_still_rejects_stale_expected_plugin_version(self):
        value = {"units": [{
            "id": "plugin-a", "version": "0.21.0", "expected_version": "0.24.0",
            "version_source": "umbrella", "required_providers": ["claude-code", "codex"],
            "provider_versions": {"claude-code": "0.21.0", "codex": "0.21.0"},
            "providers": {"claude-code": {}, "codex": {}},
        }]}
        errors = version_errors(value)
        self.assertIn(
            "RELEASE_EXPECTED_VERSION_MISMATCH: plugin-a expected 0.24.0 from umbrella, got 0.21.0",
            errors)
        self.assertIn(
            "RELEASE_VERSION_SURFACE_MISMATCH: plugin-a codex=0.21.0, expected 0.24.0",
            errors)

    def test_version_surfaces_and_required_providers_are_independent_gates(self):
        value = {"units": [{
            "id": "plugin-a", "version": "0.24.0", "expected_version": "0.24.0",
            "version_source": "umbrella", "required_providers": ["claude-code", "codex"],
            "provider_versions": {"claude-code": "0.23.0"},
            "providers": {"claude-code": {}},
        }]}
        self.assertEqual(version_errors(value), [
            "RELEASE_VERSION_SURFACE_MISMATCH: plugin-a claude-code=0.23.0, expected 0.24.0",
            "RELEASE_PROVIDER_MISSING: plugin-a codex",
        ])

    def test_live_source_ignores_ambient_ignored_telemetry(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", folder], check=True)
            (root / ".gitignore").write_text("telemetry/\n")
            (root / "lib").mkdir()
            (root / "lib/source.py").write_text("source\n")
            (root / "lib/telemetry").mkdir()
            (root / "lib/telemetry/session.json").write_text("ambient\n")
            self.assertEqual(Source(root).files("lib"), ["lib/source.py"])

    def test_deleted_tracked_files_change_live_surface_without_breaking_historical_ref(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", folder], check=True)
            (root / "skills").mkdir()
            (root / "skills/keep.md").write_text("retained capability\n")
            removed = root / "skills/removed.md"
            removed.write_text("removed CORE member\n")
            subprocess.run(["git", "add", "skills"], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                            "commit", "-qm", "fixture"], cwd=root, check=True)
            previous = surface(Source(root, "HEAD"), "skills", ["."])
            removed.unlink()  # Deliberately leave the deleted path in the git index.
            current = surface(Source(root), "skills", ["."])
            self.assertEqual(set(current["files"]), {"keep.md"})
            self.assertEqual(set(previous["files"]), {"keep.md", "removed.md"})
            self.assertEqual(surface(Source(root, "HEAD"), "skills", ["."]), previous)
            def release(value, version="1.0.0"):
                return {"units": [{"id": "core", "version": version,
                                   "providers": {"codex": value},
                                   "tree_digest": value["tree_digest"]}]}
            self.assertEqual(check_transition(release(previous), release(current)),
                             ["RELEASE_IMMUTABLE_TUPLE: core@1.0.0"])
            self.assertEqual(check_transition(release(previous), release(current, "1.0.1")), [])

    def test_missing_and_external_symlink_targets_are_not_treated_as_deletions(self):
        for outside in (False, True):
            with self.subTest(outside=outside), tempfile.TemporaryDirectory() as folder:
                root = Path(folder) / "repo"
                root.mkdir()
                subprocess.run(["git", "init", "-q", str(root)], check=True)
                (root / "skills").mkdir()
                link = root / "skills/broken.md"
                target = Path(folder) / "outside.md" if outside else root / "missing.md"
                link.symlink_to(target)
                source = Source(root)
                self.assertIn("skills/broken.md", source.files("skills"))
                with self.assertRaises(ValueError if outside else FileNotFoundError):
                    surface(source, "skills", ["."])

    def test_deleted_path_below_replaced_symlink_parent_still_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder) / "repo"
            root.mkdir()
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            parent = root / "skills"
            parent.mkdir()
            (parent / "tracked.md").write_text("tracked\n")
            subprocess.run(["git", "add", "skills/tracked.md"], cwd=root, check=True)
            (parent / "tracked.md").unlink()
            parent.rmdir()
            parent.symlink_to(Path(folder) / "missing-outside")
            source = Source(root)
            self.assertIn("skills/tracked.md", source.files("skills"))
            with self.assertRaisesRegex(ValueError, "RELEASE_PATH_UNCONTAINED"):
                source.read("skills/tracked.md")

    def test_added_native_proof_does_not_change_old_bytes(self):
        old = {"units": [{"id": "plugin-a", "version": "1.0.0", "providers": {"codex": {"tree_digest": "same"}}, "tree_digest": "old-proof"}]}
        new = deepcopy(old)
        new["units"][0]["providers"]["codex-native"] = {"tree_digest": "additional-proof"}
        new["units"][0]["tree_digest"] = "expanded-proof"
        self.assertEqual(check_transition(old, new), [])
        new["units"][0]["providers"]["codex"]["tree_digest"] = "changed-bytes"
        self.assertEqual(check_transition(old, new), ["RELEASE_IMMUTABLE_TUPLE: plugin-a@1.0.0"])

    def test_tree_digest_is_order_independent_and_path_sensitive(self):
        self.assertEqual(tree_digest({"a": "one", "b": "two"}),
                         tree_digest({"b": "two", "a": "one"}))
        self.assertNotEqual(tree_digest({"a": "one"}), tree_digest({"b": "one"}))

    def test_unchanged_unit_needs_no_bump_but_changed_bytes_do(self):
        previous = {"units": [{"id": "plugin-a", "version": "1.0.0", "tree_digest": "old"}]}
        current = deepcopy(previous)
        self.assertEqual(check_transition(previous, current), [])
        current["units"][0]["tree_digest"] = "new"
        self.assertEqual(check_transition(previous, current),
                         ["RELEASE_IMMUTABLE_TUPLE: plugin-a@1.0.0"])
        current["units"][0]["version"] = "1.0.1"
        self.assertEqual(check_transition(previous, current), [])

    def test_recorded_v014_to_v015_incident_rejects_core_and_command_plugin(self):
        fixture = json.loads((Path(__file__).parent / "fixtures_data/release-immutable-incident.json").read_text())
        errors = check_transition(fixture["v0.14.0"], fixture["v0.15.0"])
        self.assertIn("RELEASE_IMMUTABLE_TUPLE: core@0.13.1", errors)
        self.assertIn("RELEASE_IMMUTABLE_TUPLE: plugin-a@0.13.3", errors)
