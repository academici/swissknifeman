"""aicore.delivery.distribution: vendor and connect plans, the Codex bundle, the native install."""
import contextlib
import hashlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aicore.artifacts.artifact import ArtifactAdapterIdentity
from aicore.delivery import distribution
from aicore.delivery.distribution import (DistributionIdentity, ProviderDistributionPlan,
                                          connect_distribution_plan, distribution_artifact,
                                          run_codex_native_install, vendor_distribution_plan)
from aicore.provider.values import CapabilityId, CapabilityRequirement, ProviderId, SupportLevel

ADAPTER = ArtifactAdapterIdentity(
    "demo.codex-publication", "1.0.0", ProviderId.CODEX, "1.0.0",
    (CapabilityRequirement(CapabilityId("skills.repository"),
                           (SupportLevel.NATIVE, SupportLevel.ADAPTED)),))
IDENTITY = DistributionIdentity(ADAPTER, "demo.codex.connect", "demo.connect.source")


def refused(call, *args, **kwargs):
    """Run ``call`` and return the text that ``die`` wrote before exiting."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        with unittest.TestCase().assertRaises(SystemExit):
            call(*args, **kwargs)
    return err.getvalue()


def write(path, text="x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.source = self.root / "source"
        self.target = self.root / "consumer"
        self.target.mkdir()

    def make_marketplace(self, names=("php", "quality")):
        plugins = []
        for name in names:
            plugin = self.source / "skills" / name
            write(plugin / ".codex-plugin" / "plugin.json", json.dumps({
                "name": name, "version": "0.1.0", "description": name, "skills": ["./skills"]}) + "\n")
            write(plugin / "skills" / "rule" / "SKILL.md", f"---\nname: rule\n---\n{name}\n")
            write(plugin / "skills" / "rule" / "refs" / "a.md", "ref\n")
            plugins.append({"name": name, "source": f"./skills/{name}",
                            "description": name, "category": "engineering"})
        marketplace = self.source / ".agents" / "plugins" / "marketplace.json"
        write(marketplace, json.dumps({"name": "swissknifeman", "plugins": plugins}) + "\n")
        return marketplace


class VendorPlanCase(Base):
    def test_two_providers_get_their_own_paths(self):
        plans = vendor_distribution_plan(["claude-code", "codex"], self.target,
                                         claude_path=".claude/skills", codex_path=".agents/skills")
        self.assertEqual([(p.provider_id, p.channel) for p in plans],
                         [("claude-code", "vendor"), ("codex", "vendor")])
        self.assertEqual([p.target for p in plans],
                         [self.target / ".claude/skills", self.target / ".agents/skills"])
        self.assertEqual(plans[0].target_identity, (self.target / ".claude/skills").as_posix())
        self.assertEqual((plans[0].source_hash, plans[0].rendered_hash, plans[0].artifacts), ("", "", ()))

    def test_one_shared_path_is_an_ownership_conflict(self):
        message = refused(vendor_distribution_plan, ["claude-code", "codex"], self.target,
                          claude_path=".ai/skills", codex_path=".ai/skills")
        self.assertIn("SPUB_OWNERSHIP_CONFLICT", message)

    def test_providers_without_a_vendor_channel_are_skipped(self):
        plans = vendor_distribution_plan(["cursor", "grok", "codex"], self.target,
                                         claude_path="c", codex_path="x")
        self.assertEqual([p.provider_id for p in plans], ["codex"])

    def test_no_providers_no_plans(self):
        self.assertEqual(vendor_distribution_plan([], self.target, claude_path="c", codex_path="x"), ())


class ConnectPlanCase(Base):
    def test_claude_marketplace_points_at_the_claude_directory(self):
        plans = connect_distribution_plan(["claude-code"], self.target, repo_root=self.source,
                                          identity=IDENTITY)
        self.assertEqual(len(plans), 1)
        self.assertEqual((plans[0].provider_id, plans[0].channel, plans[0].target,
                          plans[0].target_identity),
                         ("claude-code", "marketplace", self.target / ".claude", ".claude"))

    def test_codex_in_the_source_repository_uses_its_own_marketplace(self):
        marketplace = self.make_marketplace()
        plans = connect_distribution_plan(["codex"], self.source, repo_root=self.source,
                                          identity=IDENTITY)
        self.assertEqual((plans[0].channel, plans[0].target, plans[0].artifacts),
                         ("marketplace", marketplace, ()))

    def test_codex_without_a_generated_marketplace_is_incomplete(self):
        message = refused(connect_distribution_plan, ["codex"], self.target,
                          repo_root=self.source, identity=IDENTITY, plugins=["php"])
        self.assertIn("SPUB_BUNDLE_INCOMPLETE", message)
        self.assertIn("generated marketplace is missing", message)

    def test_codex_bundle_needs_a_plugin_selection(self):
        self.make_marketplace()
        message = refused(connect_distribution_plan, ["codex"], self.target,
                          repo_root=self.source, identity=IDENTITY)
        self.assertIn("SPUB_BUNDLE_INCOMPLETE", message)
        self.assertIn("selected plugin set is required", message)

    def test_codex_bundle_is_self_contained_and_stamped_with_the_caller_identity(self):
        marketplace = self.make_marketplace()
        plans = connect_distribution_plan(["claude-code", "codex"], self.target,
                                          repo_root=self.source, identity=IDENTITY,
                                          plugins=["quality", "php"])
        codex = plans[1]
        self.assertEqual((codex.channel, codex.target_identity),
                         ("marketplace-bundle", ".agents/plugins/marketplace.json"))
        paths = [item.target.path for item in codex.artifacts]
        self.assertEqual(paths, sorted(paths))
        self.assertIn(".agents/plugins/bundles/php/.codex-plugin/plugin.json", paths)
        self.assertIn(".agents/plugins/bundles/quality/skills/rule/refs/a.md", paths)
        self.assertEqual(paths[0], ".agents/plugins/bundles/php/.codex-plugin/plugin.json")
        for item in codex.artifacts:
            digest = hashlib.sha256(item.target.path.encode("utf-8")).hexdigest()[:16]
            self.assertEqual(item.provenance.artifact_id, f"demo.codex.connect.a{digest}")
            self.assertEqual(item.provenance.adapter_id, "demo.codex-publication")
            self.assertEqual(item.provenance.canonical_sources[0].source_id, "demo.connect.source")
        consumer = json.loads(next(i for i in codex.artifacts
                                   if i.target.path == ".agents/plugins/marketplace.json").managed_bytes)
        self.assertEqual(consumer["name"], "swissknifeman")
        self.assertEqual([e["name"] for e in consumer["plugins"]], ["php", "quality"])
        self.assertEqual(consumer["plugins"][0]["source"],
                         {"source": "local", "path": "./.agents/plugins/bundles/php"})
        self.assertNotIn(str(self.source), json.dumps(consumer))
        marketplace_item = next(i for i in codex.artifacts if i.target.path.endswith("marketplace.json"))
        self.assertEqual(marketplace_item.provenance.canonical_sources[0].path, marketplace.relative_to(self.source).as_posix())
        self.assertEqual(codex.source_hash, marketplace_item.provenance.source_hash)
        self.assertEqual(codex.rendered_hash, marketplace_item.provenance.rendered_hash)
        self.assertTrue(codex.artifact_plan is not None)

    def test_undeclared_and_duplicate_plugins_are_refused(self):
        self.make_marketplace()
        message = refused(connect_distribution_plan, ["codex"], self.target, repo_root=self.source,
                          identity=IDENTITY, plugins=["missing"])
        self.assertIn("selected plugin is not declared", message)
        message = refused(connect_distribution_plan, ["codex"], self.target, repo_root=self.source,
                          identity=IDENTITY, plugins=["php", "php"])
        self.assertIn("duplicate selected plugin", message)

    def test_a_plugin_source_outside_the_repository_is_refused(self):
        marketplace = self.make_marketplace()
        data = json.loads(marketplace.read_text(encoding="utf-8"))
        data["plugins"][0]["source"] = "../elsewhere"
        marketplace.write_text(json.dumps(data), encoding="utf-8")
        message = refused(connect_distribution_plan, ["codex"], self.target, repo_root=self.source,
                          identity=IDENTITY, plugins=["php"])
        self.assertIn("SPUB_PATH_UNCONTAINED", message)

    def test_an_unowned_file_in_a_managed_bundle_is_a_conflict(self):
        self.make_marketplace()
        write(self.target / ".agents/plugins/bundles/php/stray.txt")
        message = refused(connect_distribution_plan, ["codex"], self.target, repo_root=self.source,
                          identity=IDENTITY, plugins=["php"])
        self.assertIn("SPUB_OWNERSHIP_CONFLICT", message)
        self.assertIn("unowned file in managed bundle", message)

    def test_a_bundle_plan_is_deterministic(self):
        self.make_marketplace()
        first = connect_distribution_plan(["codex"], self.target, repo_root=self.source,
                                          identity=IDENTITY, plugins=["php"])
        second = connect_distribution_plan(["codex"], self.target, repo_root=self.source,
                                           identity=IDENTITY, plugins=["php"])
        self.assertEqual([a.managed_bytes for a in first[0].artifacts],
                         [a.managed_bytes for a in second[0].artifacts])
        self.assertEqual([a.provenance.artifact_id for a in first[0].artifacts],
                         [a.provenance.artifact_id for a in second[0].artifacts])


class DistributionArtifactCase(Base):
    def test_artifact_is_a_whole_file_stamped_with_the_identity(self):
        target = self.target / "a" / "b.txt"
        item = distribution_artifact(self.target, target, b"managed", "src/b.txt", b"source",
                                     identity=IDENTITY)
        digest = hashlib.sha256(b"a/b.txt").hexdigest()[:16]
        self.assertEqual(item.provenance.artifact_id, f"demo.codex.connect.a{digest}")
        self.assertEqual(item.target.path, "a/b.txt")
        self.assertEqual(item.managed_bytes, b"managed")
        self.assertEqual(item.provenance.canonical_sources[0].path, "src/b.txt")
        self.assertEqual(item.provenance.canonical_sources[0].content_hash, "sha256:" + hashlib.sha256(b"source").hexdigest())

    def test_two_namespaces_give_two_ids(self):
        other = DistributionIdentity(ADAPTER, "demo.other", "demo.other.source")
        a = distribution_artifact(self.target, self.target / "f", b"", "s", b"", identity=IDENTITY)
        b = distribution_artifact(self.target, self.target / "f", b"", "s", b"", identity=other)
        self.assertNotEqual(a.provenance.artifact_id, b.provenance.artifact_id)
        self.assertTrue(b.provenance.artifact_id.startswith("demo.other.a"))

    def test_the_plan_type_is_a_frozen_dataclass(self):
        plan = ProviderDistributionPlan("codex", "vendor", self.target, "t", "", "")
        with self.assertRaises(Exception):
            plan.channel = "x"


class NativeInstallCase(Base):
    def test_dry_run_never_probes_or_runs(self):
        runner = mock.Mock()
        with mock.patch.object(distribution.shutil, "which") as which:
            ok, message = run_codex_native_install(repo_root=self.source, plugin="php",
                                                   dry_run=True, runner=runner)
        self.assertTrue(ok)
        self.assertIn("SPUB_INSTALL_EXPLICIT_REQUIRED", message)
        runner.assert_not_called()
        which.assert_not_called()

    def test_missing_executable_is_unavailable(self):
        runner = mock.Mock()
        with mock.patch.object(distribution.shutil, "which", return_value=None) as which:
            ok, message = run_codex_native_install(repo_root=self.source, plugin="php",
                                                   dry_run=False, runner=runner)
        which.assert_called_once_with("codex")
        self.assertFalse(ok)
        self.assertIn("SPUB_INSTALL_UNAVAILABLE", message)
        runner.assert_not_called()

    def test_adds_the_marketplace_then_the_plugin(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
        with mock.patch.object(distribution.shutil, "which", return_value="/bin/codex"):
            ok, message = run_codex_native_install(repo_root=self.source, plugin="php",
                                                   dry_run=False, runner=runner)
        self.assertTrue(ok)
        self.assertEqual([c.args[0] for c in runner.call_args_list], [
            ["codex", "plugin", "marketplace", "add", str(self.source)],
            ["codex", "plugin", "add", "php@swissknifeman"]])
        self.assertEqual(message, f"codex/native-install: marketplace={self.source}, plugin=php@swissknifeman")

    def test_a_failing_command_names_itself(self):
        runner = mock.Mock(return_value=subprocess.CompletedProcess([], 2, "", "denied"))
        with mock.patch.object(distribution.shutil, "which", return_value="/bin/codex"):
            ok, message = run_codex_native_install(repo_root=self.source, plugin="php",
                                                   dry_run=False, runner=runner)
        self.assertFalse(ok)
        self.assertEqual(message, "SPUB_INSTALL_UNAVAILABLE: codex plugin marketplace failed: denied")
