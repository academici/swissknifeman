"""The JSON commands other modules call (maind deploy, sync, workspace): output matches its contract."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))

import aicore
from aicore.artifacts.artifact import sha256_digest
from aicore.provider.mcp import parse_mcp_catalog, plan_mcp_projection
from aicore.provider.values import ProviderId
from aicore.util.schema import load_contract, validate
from harness import hooks, instructions, mcp, profiles
from harness.common import Env

ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = Path(aicore.__file__).resolve().parents[2] / "schemas"


def contract(name):
    return load_contract(ROOT / "schemas" / name / "v1", urn_prefix="urn:swissknifeman:harness:",
                         foundation=FOUNDATION)


def run(handler, *argv):
    """Run an in-process command and return its parsed JSON stdout."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        handler(Env(ROOT, "test"), list(argv))
    return json.loads(out.getvalue())


class McpCatalogCase(unittest.TestCase):
    def test_output_matches_contract_and_the_shipped_files(self):
        registry, kind = contract("mcp-catalog")
        document = run(mcp.cmd_mcp, "catalog", "--json")
        self.assertEqual(validate(document, kind, registry), [])
        catalog_path = ROOT / "configs/common/mcp/catalog.json"
        self.assertEqual(document["catalog"], json.loads(catalog_path.read_text(encoding="utf-8")))
        self.assertEqual(sorted(document["bindings"]), ["claude-code", "codex", "cursor", "grok"])
        self.assertEqual(document["sources"]["catalog"], {
            "id": "harness.mcp.catalog", "path": "packages/harness/configs/common/mcp/catalog.json",
            "sha256": sha256_digest(catalog_path.read_bytes())})
        codex = ROOT / "configs/codex/mcp/bindings.json"
        self.assertEqual(document["sources"]["bindings"]["codex"], {
            "id": "harness.codex.mcp-bindings",
            "path": "packages/harness/configs/codex/mcp/bindings.json",
            "sha256": sha256_digest(codex.read_bytes())})
        self.assertEqual(document["adapters"]["codex"], "harness.codex.mcp")

    def test_sources_equal_the_ones_the_artifact_plan_records(self):
        document = run(mcp.cmd_mcp, "catalog", "--json")
        catalog = mcp.load_mcp_catalog(ROOT / "configs/common/mcp/catalog.json")
        for provider in (ProviderId.CODEX, ProviderId.CURSOR, ProviderId.GROK):
            bindings = ROOT / "configs" / provider.value / "mcp" / "bindings.json"
            projection = mcp.plan_mcp_projection(catalog, provider_id=provider, bindings_path=bindings,
                                                 selected=(catalog[0].id,), trusted=True)
            artifact = mcp.plan_mcp_artifact(projection, catalog_path=ROOT / "configs/common/mcp/catalog.json",
                                             bindings_path=bindings)
            recorded = {item.source_id: [item.path, item.content_hash]
                        for item in artifact.provenance.canonical_sources}
            listed = {record["id"]: [record["path"], record["sha256"]]
                      for record in (document["sources"]["catalog"],
                                     document["sources"]["bindings"][provider.value])}
            self.assertEqual(recorded, listed)
            self.assertEqual(artifact.provenance.adapter_id, document["adapters"][provider.value])

    def test_document_feeds_the_aicore_projection(self):
        document = run(mcp.cmd_mcp, "catalog", "--json", "--provider", "codex")
        self.assertEqual(sorted(document["bindings"]), ["codex"])
        catalog = parse_mcp_catalog(document["catalog"])
        projection = plan_mcp_projection(catalog, provider_id=ProviderId.CODEX,
                                         bindings=document["bindings"]["codex"],
                                         selected=tuple(item.id for item in catalog), trusted=True)
        self.assertEqual(projection.target_path, ".codex/config.toml")

    def test_unknown_provider_is_refused(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(mcp.cmd_mcp, "catalog", "--json", "--provider", "nope")

    def test_json_is_required(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            run(mcp.cmd_mcp, "catalog")


class ProfileResolutionCase(unittest.TestCase):
    def resolve(self, *extra):
        return run(profiles.cmd_profiles, "resolve", "--json", *extra)

    def test_green_and_refused_resolutions_match_contract(self):
        registry, kind = contract("profile-resolution")
        green = self.resolve("--provider", "codex", "--profile", "workspace-contained",
                             "--target-scope", "project", "--trusted")
        self.assertEqual(validate(green, kind, registry), [])
        self.assertTrue(green["green"])
        self.assertEqual(green["profile"]["id"], "workspace-contained")
        untrusted = self.resolve("--provider", "codex", "--profile", "workspace-contained",
                                 "--target-scope", "project")
        self.assertEqual(validate(untrusted, kind, registry), [])
        self.assertFalse(untrusted["green"])
        self.assertIsNone(untrusted["profile"])
        self.assertEqual([item["code"] for item in untrusted["diagnostics"]], ["HARNESS_TRUST_REQUIRED"])

    def test_full_access_needs_explicit_operation_and_target(self):
        implicit = self.resolve("--provider", "claude-code", "--profile", "trusted-full-access",
                                "--target-scope", "project", "--trusted")
        self.assertEqual([item["code"] for item in implicit["diagnostics"]],
                         ["HARNESS_FULL_ACCESS_EXPLICIT_REQUIRED"])
        inherited = self.resolve("--provider", "claude-code", "--profile", "trusted-full-access",
                                 "--target-scope", "project", "--trusted", "--origin", "project")
        self.assertIn("HARNESS_FULL_ACCESS_INHERITANCE_FORBIDDEN",
                      [item["code"] for item in inherited["diagnostics"]])
        explicit = self.resolve("--provider", "claude-code", "--profile", "trusted-full-access",
                                "--target-scope", "project", "--trusted", "--operation-id", "self-host-apply",
                                "--target-identity", "repo:demo")
        self.assertTrue(explicit["green"])
        self.assertEqual((explicit["operation_id"], explicit["target_identity"]),
                         ("self-host-apply", "repo:demo"))

    def test_disabled_provider_is_refused(self):
        document = self.resolve("--provider", "grok", "--profile", "observe", "--target-scope", "project",
                                "--trusted", "--disabled")
        self.assertEqual([item["code"] for item in document["diagnostics"]], ["HARNESS_PROVIDER_DISABLED"])

    def test_fixed_resolution_oracle_and_read_only_filesystem_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            env = dict(os.environ, HOME=tmp, SKM_HOME=str(root / "skm"),
                       PYTHONPATH=os.pathsep.join([str(ROOT / "lib"), str(Path(aicore.__file__).resolve().parents[1])]))
            before = list(root.rglob("*"))
            done = subprocess.run([sys.executable, "-m", "harness", str(ROOT), "profiles", "resolve", "--json",
                                   "--provider", "codex", "--profile", "workspace-contained", "--target-scope", "project",
                                   "--trusted"], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(json.loads(done.stdout), {
                "$schema": "urn:swissknifeman:harness:profile-resolution:v1", "provider_id": "codex",
                "profile": {"id": "workspace-contained", "intent": "Operate autonomously only inside the explicit workspace and managed targets."},
                "target_scope": "project", "operation_id": None, "target_identity": None, "green": True, "diagnostics": []})
            self.assertEqual(list(root.rglob("*")), before)

    def test_matches_the_in_process_resolver(self):
        catalog = profiles.load_catalog(profiles.default_catalog_path(Env(ROOT, "test")))
        for profile_id in ("observe", "workspace-contained"):
            for provider in ProviderId:
                direct = profiles.resolve_profile(
                    catalog, provider_id=provider, profile_id=profile_id, target_scope="project",
                    trusted=True, origin="operation",
                    effective_provider=profiles.EffectiveProvider(provider, True))
                via = self.resolve("--provider", provider.value, "--profile", profile_id,
                                   "--target-scope", "project", "--trusted")
                self.assertEqual(via, profiles.resolution_document(direct))


class CodexLifecycleCase(unittest.TestCase):
    def fragment(self):
        return run(hooks.cmd_hooks, "codex-lifecycle", "fragment", "--json")

    def test_fragment_matches_contract_and_the_in_process_builder(self):
        registry, kind = contract("codex-lifecycle")
        document = self.fragment()
        self.assertEqual(validate(document, kind, registry), [])
        direct = hooks.d104_observer_fragment(ROOT / "configs")
        fragment = document["fragment"]
        self.assertEqual(fragment["handler"].encode("utf-8"), direct.handler_bytes)
        self.assertEqual(fragment["group"], direct.group)
        self.assertEqual((fragment["target_path"], fragment["event"]), (direct.target_path, direct.event))
        self.assertEqual(fragment["source"]["id"], "harness.d104.observer-fragment")
        self.assertEqual(fragment["source"]["path"], "packages/harness/lib/harness/hooks.py")
        self.assertEqual(fragment["handler_sha256"], sha256_digest(direct.handler_bytes))
        self.assertEqual((fragment["target_path"], fragment["event"]), (".codex/hooks.json", "SessionStart"))
        self.assertEqual(fragment["group"]["hooks"][0]["type"], "command")
        self.assertIn("context.observer", fragment["group"]["hooks"][0]["command"])

    def validate_document(self, document, memory_command):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "hooks.json"
            path.write_bytes(document)
            result = run(hooks.cmd_hooks, "codex-lifecycle", "validate", "--document", str(path),
                         "--memory-command", memory_command, "--json")
            self.assertEqual(path.read_bytes(), document)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["hooks.json"])
            return result

    def test_validate_accepts_the_composition_and_reports_refusals_as_data(self):
        registry, kind = contract("codex-lifecycle")
        observer = self.fragment()["fragment"]["group"]
        memory = {"hooks": [{"type": "command", "command": "bash memory.sh"}]}
        composed = (json.dumps({"hooks": {"SessionStart": [memory, observer]}}, indent=2) + "\n").encode()
        ok = self.validate_document(composed, "bash memory.sh")
        self.assertEqual(validate(ok, kind, registry), [])
        self.assertEqual((ok["ok"], ok["code"]), (True, None))
        wrong = self.validate_document(composed, "bash other.sh")
        self.assertEqual(validate(wrong, kind, registry), [])
        self.assertEqual((wrong["ok"], wrong["code"]), (False, "HARNESS_D104_LIFECYCLE_INVALID"))
        broken = self.validate_document(b"{", "bash memory.sh")
        self.assertEqual((broken["ok"], broken["code"]), (False, "HARNESS_D104_LIFECYCLE_INVALID"))


class InstructionScopesCase(unittest.TestCase):
    def test_scopes_match_contract_and_the_catalog(self):
        registry, kind = contract("instruction-scopes")
        document = run(instructions.cmd_instructions, "scopes", "--json")
        self.assertEqual(validate(document, kind, registry), [])
        self.assertEqual(document["scopes"], list(instructions.SCOPES))
        self.assertEqual(document["scopes"][0], "root")
        self.assertEqual(document["catalog_version"], instructions.CATALOG_VERSION)
        self.assertEqual(document["contract_version"], instructions.CONTRACT_VERSION)


class LauncherCase(unittest.TestCase):
    def test_commands_run_through_the_module_entry_point(self):
        with tempfile.TemporaryDirectory() as home:
            env = dict(os.environ, HOME=home, SKM_HOME=home,
                       PYTHONPATH=os.pathsep.join([str(ROOT / "lib"), str(Path(aicore.__file__).resolve().parents[1])]))
            for argv, key in ((["mcp", "catalog", "--json"], "catalog"),
                              (["instructions", "scopes", "--json"], "scopes"),
                              (["hooks", "codex-lifecycle", "fragment", "--json"], "fragment")):
                with self.subTest(argv=argv):
                    done = subprocess.run([sys.executable, "-m", "harness", str(ROOT)] + argv,
                                          capture_output=True, text=True, env=env, check=False)
                    self.assertEqual(done.returncode, 0, done.stderr)
                    self.assertIn(key, json.loads(done.stdout))


if __name__ == "__main__":
    unittest.main()
