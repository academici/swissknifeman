"""aicore.content.publication: manifests, whole-file artifacts, Codex plugin files, lock, runtime files."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from aicore.artifacts.artifact import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                                       ArtifactTarget, plan_artifact_render)
from aicore.content import publication
from aicore.provider.manifest import ProviderManifestError, default_manifest_path
from aicore.provider.values import CapabilityId, CapabilityRequirement, ProviderId, SupportLevel

HASH = "sha256:" + "ab" * 32
ADAPTER = ArtifactAdapterIdentity(
    "demo.publication", "1.0.0", ProviderId.CODEX, "1.0.0",
    (CapabilityRequirement(CapabilityId("skills.repository"),
                           (SupportLevel.NATIVE, SupportLevel.ADAPTED)),))


def write(path, text="x\n"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class PackageRelCase(unittest.TestCase):
    def test_nested_and_standalone(self):
        root = Path("/host")
        self.assertEqual(publication.package_rel(root, root / "vendor" / "skiller"), "vendor/skiller")
        self.assertEqual(publication.package_rel(root, root), "")


class ManifestBytesCase(unittest.TestCase):
    def test_insertion_order_is_kept_by_default(self):
        self.assertEqual(publication.manifest_bytes({"b": 1, "a": "ё"}),
                         '{\n  "b": 1,\n  "a": "ё"\n}\n'.encode("utf-8"))

    def test_sort_keys_is_explicit(self):
        self.assertEqual(publication.manifest_bytes({"b": 1, "a": 2}, sort_keys=True),
                         b'{\n  "a": 2,\n  "b": 1\n}\n')

    def test_non_ascii_is_not_escaped_and_newline_ends_the_file(self):
        out = publication.manifest_bytes({"k": "значение"})
        self.assertIn("значение".encode("utf-8"), out)
        self.assertTrue(out.endswith(b"\n"))
        self.assertFalse(out.endswith(b"\n\n"))


class RenderWholeFileCase(unittest.TestCase):
    def test_equals_the_direct_planning_call(self):
        sources = (ArtifactSource("demo.source0", "skills/a/SKILL.md", HASH),)
        params = {"publication_unit": "u", "plugin_version": "1.2.3"}
        direct = plan_artifact_render(ArtifactRenderRequest(
            "demo.artifact", sources, ArtifactTarget("out/plugin.json", ("whole-file", ())),
            ADAPTER, (), dict(params), lambda _request: b"payload"))
        built = publication.render_whole_file(
            artifact_id="demo.artifact", target="out/plugin.json", sources=sources,
            adapter=ADAPTER, parameters=params, rendered=b"payload")
        self.assertEqual(built.managed_bytes, direct.managed_bytes)
        self.assertEqual(built.provenance, direct.provenance)

    def test_boundary_is_whole_file(self):
        built = publication.render_whole_file(
            artifact_id="demo.artifact", target="a.json",
            sources=(ArtifactSource("demo.s", "a", HASH),), adapter=ADAPTER,
            parameters={}, rendered=b"{}\n")
        self.assertEqual(built.provenance.target_path, "a.json")
        self.assertIn(b"{}\n", built.managed_bytes)

    def test_target_must_be_relative(self):
        with self.assertRaises(ValueError):
            publication.render_whole_file(
                artifact_id="demo.artifact", target="/abs.json",
                sources=(ArtifactSource("demo.s", "a", HASH),), adapter=ADAPTER,
                parameters={}, rendered=b"")


class CapabilityRequirementsCase(unittest.TestCase):
    def test_sorted_distinct_with_adapted_and_native(self):
        found = publication.capability_requirements(("b.cap", "a.cap", "b.cap"))
        self.assertEqual([item.capability_id.value for item in found], ["a.cap", "b.cap"])
        for item in found:
            self.assertEqual(set(item.accepted_levels), {SupportLevel.ADAPTED, SupportLevel.NATIVE})

    def test_empty(self):
        self.assertEqual(publication.capability_requirements(()), ())


class CodexFilesCase(unittest.TestCase):
    def test_plugin_manifest_key_order(self):
        data = publication.codex_plugin_manifest("n", "1.0.0", "d", ["./x"])
        self.assertEqual(list(data), ["name", "version", "description", "skills"])
        self.assertEqual(data["skills"], ["./x"])

    def test_marketplace_entry(self):
        entry = publication.codex_marketplace_entry(
            "n", "./skills/n", "d", {"category": "meta", "tags": ("a", "b")})
        self.assertEqual(entry, {"name": "n", "source": "./skills/n", "description": "d",
                                 "category": "meta", "tags": ["a", "b"],
                                 "install_policy": "explicit", "auth": "none"})

    def test_marketplace_entry_defaults(self):
        entry = publication.codex_marketplace_entry("n", "./n", "d", {})
        self.assertEqual((entry["category"], entry["tags"]), ("", []))

    def test_marketplace_entry_refuses_unprefixed_and_escaping_paths(self):
        for path in ("skills/n", "/abs/n", "../n", "./a/../../n"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(
                        ValueError, "Codex marketplace source path must be contained and ./-prefixed"):
                    publication.codex_marketplace_entry("n", path, "d", {})


class PublicationLockCase(unittest.TestCase):
    def test_document_and_records_untouched(self):
        records = [{"path": "a", "source_hash": "s", "rendered_hash": "r"},
                   {"path": "b", "source_hash": "s", "rendered_hash": "r", "artifact_id": "x.y"}]
        lock = publication.publication_lock("unit", "2.0.0", tuple(records))
        self.assertEqual(list(lock), ["contract_version", "publication_unit", "version", "artifacts"])
        self.assertEqual(lock["contract_version"], "1.0.0")
        self.assertEqual((lock["publication_unit"], lock["version"]), ("unit", "2.0.0"))
        self.assertEqual(lock["artifacts"], records)
        self.assertIsInstance(lock["artifacts"], list)


class DistributionCatalogCase(unittest.TestCase):
    def test_cached(self):
        self.assertIs(publication.distribution_catalog(), publication.distribution_catalog())


class CapabilityGateCase(unittest.TestCase):
    def test_packaged_manifest_passes_for_the_publishing_providers(self):
        for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX, ProviderId.CURSOR):
            with self.subTest(provider=provider):
                manifest = publication.validate_publication_capabilities(provider)
                self.assertTrue(manifest.capabilities)

    def test_refuses_missing_unsupported_and_catalog_mismatch(self):
        source = json.loads(default_manifest_path().read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(ProviderManifestError):
                publication.validate_publication_capabilities(
                    ProviderId.CODEX, manifest_path=root / "missing.json")
            unsupported = json.loads(json.dumps(source))
            row = next(item for item in unsupported["capabilities"]
                       if item["id"] == "skills.repository")["support"]["codex"]
            row.pop("binding")
            row["level"] = "unsupported"
            row["limitations"] = ["fixture refusal"]
            row["diagnostic"] = "unsupported fixture; fail closed"
            path = root / "unsupported.json"
            path.write_text(json.dumps(unsupported), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "REGISTRY_CAPABILITY_UNSUPPORTED"):
                publication.validate_publication_capabilities(ProviderId.CODEX, manifest_path=path)
            mismatch = json.loads(json.dumps(source))
            mismatch["catalog_version"] = "1.1.0"
            path.write_text(json.dumps(mismatch), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "REGISTRY_CATALOG_VERSION_MISMATCH"):
                publication.validate_publication_capabilities(ProviderId.CODEX, manifest_path=path)


class SkillRuntimeFilesCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "bucket"
        self.skill = self.root / "demo"
        write(self.skill / "SKILL.md")
        write(self.skill / "snippets" / "a.md")
        write(self.skill / "snippets" / "deep" / "b.md")

    def files(self):
        return sorted(path.relative_to(self.skill).as_posix() for path in publication.skill_runtime_files(
            self.skill, source_root=self.root, plugin="demo"))

    def test_walks_the_tree(self):
        self.assertEqual(self.files(), ["SKILL.md", "snippets/a.md", "snippets/deep/b.md"])

    def test_vendor_exclusions_are_skipped(self):
        write(self.skill / "SKILL.ru.md")
        write(self.skill / "upstream.json", "{}")
        write(self.skill / "evals" / "case.json", "{}")
        write(self.skill / ".claude-plugin" / "plugin.json", "{}")
        write(self.skill / "__pycache__" / "m.pyc", "")
        write(self.skill / "snippets" / "check.pyc", "")
        self.assertEqual(self.files(), ["SKILL.md", "snippets/a.md", "snippets/deep/b.md"])

    def test_path_outside_the_root_is_refused(self):
        outside = Path(self._tmp.name) / "outside"
        write(outside / "secret.md")
        (self.skill / "link").symlink_to(outside, target_is_directory=True)
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            publication.skill_runtime_files(self.skill, source_root=self.root, plugin="demo")
        self.assertIn("SPUB_PATH_UNCONTAINED: provider codex, unit demo, runtime support file", err.getvalue())


class ContainedCase(unittest.TestCase):
    def test_inside_returns_the_resolved_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            write(root / "a" / "b.md")
            self.assertEqual(publication.contained(root, root / "a" / "b.md", plugin="p", label="file"),
                             root / "a" / "b.md")

    def test_outside_dies_with_the_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve() / "root"
            root.mkdir()
            err = io.StringIO()
            with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as raised:
                publication.contained(root, root / ".." / "x", plugin="p", label="declared skill root")
            self.assertEqual(raised.exception.code, 1)
            self.assertIn(f"ERROR: SPUB_PATH_UNCONTAINED: provider codex, unit p, declared skill root "
                          f"{root / '..' / 'x'} escapes {root}", err.getvalue())


if __name__ == "__main__":
    unittest.main()
