"""Host-driven sibling publication and package provenance in arbitrary layouts."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from skiller.common import Env
from skiller.doctor import declared_fixture_unit_set
from skiller.host import Host, load_host
from skiller.publication import (_generator, package_rel,
                                 render_repository_bootstrap_projections)
from skiller.registry import (_legacy_build_plugin_manifests, _sibling_plugins,
                              build_catalog, build_claude_publication,
                              build_codex_publication, build_registry)
from tests.fixtures import make_registry


class HostPublicationCase(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        (self.repo / ".git").mkdir()
        root, _ = make_registry(self.repo)
        self.root = self.repo / "vendor" / "skiller"
        self.root.parent.mkdir()
        root.rename(self.root)
        self.env = Env(self.root)
        self.registry, self.metadata, self.buckets = build_registry(self.env)
        patch = mock.patch.dict(os.environ, {}, clear=False)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("SKILLER_HOST_CONFIG", None)
        self.alpha = self._plugin("plugins/alpha", "alpha", codex=True)
        self._plugin("plugins/omega", "omega", codex=False)
        # Host discovery must never infer sibling directories without configuration.
        self._plugin("other/hidden", "hidden", codex=True)

    def _plugin(self, path, name, *, codex):
        root = self.repo / path
        for provider in ("claude", "codex") if codex else ("claude",):
            target = root / f".{provider}-plugin" / "plugin.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"name": name, "description": name}), encoding="utf-8")
        return root

    def _host(self, patterns):
        target = self.repo / "configs" / "skiller-host.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps({"schema_version": 1, "plugin_dirs": patterns}),
                          encoding="utf-8")
        return load_host(self.root)

    def _marketplace(self, builder):
        artifacts = builder(self.env, self.metadata, self.buckets, self.registry)
        return json.loads(next(a.managed_bytes for a in artifacts
                               if a.target.name == "marketplace.json"))

    def test_siblings_use_host_globs_and_provider_support(self):
        self._host(["plugins/*"])
        for builder in (build_claude_publication, build_codex_publication):
            plugins = {p["name"]: p for p in self._marketplace(builder)["plugins"]}
            self.assertEqual(plugins["alpha"]["source"], "./plugins/alpha")
            self.assertNotIn("hidden", plugins)
            self.assertEqual("omega" in plugins, builder is build_claude_publication)
        legacy = _legacy_build_plugin_manifests(self.env, self.metadata, self.buckets)
        plugins = {p["name"]: p for p in legacy[-1][1]["plugins"]}
        self.assertEqual(plugins["alpha"]["source"], "./plugins/alpha")

    def test_siblings_are_empty_without_host(self):
        self.assertEqual(_sibling_plugins(self.repo, self.root, Host.empty()), ())
        for builder in (build_claude_publication, build_codex_publication):
            names = {p["name"] for p in self._marketplace(builder)["plugins"]}
            self.assertFalse(names & {"alpha", "omega", "hidden"})
        legacy = _legacy_build_plugin_manifests(self.env, self.metadata, self.buckets)
        self.assertFalse({p["name"] for p in legacy[-1][1]["plugins"]} & {"alpha", "omega"})

    def test_overlapping_patterns_are_deduplicated_sorted_and_exclude_self(self):
        self._plugin("vendor/skiller", "self", codex=True)
        host = self._host(["plugins/omega", "vendor/*", "plugins/*", "other/*"])
        siblings = _sibling_plugins(self.repo, self.root, host)
        self.assertEqual([p.source_path for p in siblings],
                         ["other/hidden", "plugins/alpha", "plugins/omega"])

    def test_empty_source_provenance_uses_actual_package_prefix(self):
        from aicore.content import publication
        real_render = publication.plan_artifact_render
        with mock.patch.object(publication, "plan_artifact_render", wraps=real_render) as render:
            self._marketplace(build_claude_publication)
            self._marketplace(build_codex_publication)
        meta_sources = [source.path for call in render.call_args_list
                        for source in call.args[0].canonical_sources
                        if source.source_id == "skiller.publication.meta"]
        self.assertTrue(meta_sources)
        self.assertEqual(set(meta_sources), {"vendor/skiller/package.json"})

    def test_doctor_identity_and_generator_use_actual_prefix(self):
        catalog = build_catalog(self.env, self.metadata, self.buckets, self.registry)
        document = declared_fixture_unit_set(catalog, repo_root=self.repo, package_root=self.root)
        for provider in document["providers"].values():
            self.assertEqual(provider["identity_source"],
                             "vendor/skiller/lib/skiller/registry.py::build_catalog")
        self.assertEqual(package_rel(self.repo, self.root), "vendor/skiller")
        self.assertEqual(package_rel(self.root, self.root), "")
        self.assertEqual(_generator(""),
                         "generator: lib/skiller/registry.py→lib/skiller/publication.py")

    def test_bootstrap_generator_in_relocated_package(self):
        from tests.fixtures import write_skill
        write_skill(self.repo / "bootstrap/skills/alpha", "alpha")
        config_dir = self.repo / "configs"
        config_dir.mkdir()
        config_dir.joinpath("skiller-host.json").write_text(json.dumps({
            "schema_version": 1, "bootstrap": "configs/repository-bootstrap-skills.json",
        }))
        config_dir.joinpath("repository-bootstrap-skills.json").write_text(json.dumps({
            "schema_version": 2, "identities": [
                {"identity": "alpha", "canonical": "bootstrap/skills/alpha/SKILL.md"}],
            "providers": ["claude", "codex"], "class_a_content_version": "0.1.0",
            "publication_unit": "repository-bootstrap", "class_b": [],
            "bucket": "repository-bootstrap", "unit_version": "0.1.0",
            "lock_path": "bootstrap/publication-lock.json",
        }), encoding="utf-8")
        config_dir.joinpath("publication-versions.json").write_text(json.dumps({
            "units": {"repository-bootstrap": "0.1.0"}, "default_unit_version": "0.1.0",
        }), encoding="utf-8")
        artifacts = render_repository_bootstrap_projections(repo_root=self.repo,
                                                            package_root=self.root)
        for artifact in artifacts:
            if artifact.provider != "lock":
                self.assertIn(_generator("vendor/skiller"), artifact.managed_bytes.decode())
