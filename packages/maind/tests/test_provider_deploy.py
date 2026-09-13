import json
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "harness/lib"))

from core import (ArtifactActionKind, ArtifactAdapterIdentity,
                  ArtifactRenderRequest, ArtifactSource, ArtifactTarget,
                  ConfigSource, ProviderConfigCatalog,
                  ProviderConfigLayer, ProviderId, apply_plan, canonical_json_bytes,
                  parse_lock, plan_artifact_lock, plan_artifact_render, sha256_digest)
from harness.mcp import load_mcp_catalog, plan_mcp_projection
from maind.provider_deploy import (ProviderDeployError, plan_provider_deploy,
                                   plan_provider_artifacts, apply_provider_artifacts,
                                   plan_provider_artifact_adoption,
                                   plan_exact_artifact_adoption,
                                   resolve_effective_providers, semantic_servers,
                                   SemanticServer, plan_d108_operation)
from maind.provider_deploy import (conformance_report, plan_d104_bootstrap_transfer,
                                   write_conformance_report, plan_project_carrier,
                                   apply_project_carrier, apply_d108_operation,
                                   rollback_d108_operation, _d108_planned_projections)
from maind.provision.deploy import deploy_project, mark_deployed, provider_semantic_inventory
try:
    from .fixtures import make_repo
except ImportError:  # unittest discover loads this module without a package.
    from tests.fixtures import make_repo
from maind.config import merge_defaults
import tempfile
import subprocess
from unittest.mock import patch


_D104_PREIMAGE = b'''{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "bash /home/vostrikov/projects/packages/swissknifeman/.claude/maind-memory.sh"
          }
        ]
      }
    ]
  }
}
'''

_D108_MCP_PREIMAGE = b'''{
  "mcpServers": {
    "maind": {
      "command": "${MAIND_BIN:-maind}",
      "args": [
        "mcp",
        "--scope",
        "project:swissknifeman"
      ]
    },
    "perplexity-web": {
      "command": "${PERPLEXITY_WEB_MCP_BIN:-/home/vostrikov/projects/packages/perplexity-web-mcp/start.sh}",
      "args": [
        "--pool=default"
      ]
    },
    "serena": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/oraios/serena",
        "serena",
        "start-mcp-server",
        "--context",
        "ide-assistant",
        "--project",
        "/home/vostrikov/projects/packages/swissknifeman",
        "--enable-web-dashboard",
        "false"
      ]
    }
  }
}
'''


class TestProviderDeploy(unittest.TestCase):
    @staticmethod
    def skiller_artifact(body=b"managed skill\n"):
        return plan_artifact_render(ArtifactRenderRequest(
            "skiller.codex.connect.a123", (ArtifactSource(
                "skiller.test", "packages/skiller/test", sha256_digest(body)),),
            ArtifactTarget(".agents/skills/test/SKILL.md", ("whole-file", ())),
            ArtifactAdapterIdentity("skiller.test", "1.0.0", ProviderId.CODEX,
                                    "1.0.0", ()), (), {}, lambda _request: body))

    def test_ordinary_deploy_and_skiller_alternating_writers_preserve_ownership(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(
            catalog, provider_id=provider,
            bindings_path=harness / provider.value / "mcp/bindings.json",
            selected=(), trusted=True) for provider in ProviderId)
        deploy = plan_provider_deploy(bases, semantic_servers(maind={"command": "maind"}))
        for order in (("skiller", "maind"), ("maind", "skiller")):
            with self.subTest(order=order), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                lock_path = root / ".swissknifeman/provider-artifacts.lock.json"

                def skiller_write(body):
                    artifact = self.skiller_artifact(body)
                    apply_plan(root, plan_artifact_lock(
                        root, (artifact,), lock_bytes=lock_path.read_bytes()
                        if lock_path.exists() else None,
                        owner_namespace="skiller.codex.connect"))

                for writer in order:
                    if writer == "skiller":
                        skiller_write(b"old skill\n")
                    else:
                        apply_provider_artifacts(root, deploy)
                updated = plan_provider_deploy(
                    bases, semantic_servers(maind={"command": "updated-maind"}))
                apply_provider_artifacts(root, updated)
                skiller_write(b"updated skill\n")
                self.assertEqual(plan_provider_artifacts(root, updated)["severity"], "green")
                records = parse_lock(lock_path.read_bytes()).records
                self.assertEqual({record.artifact_id for record in records},
                                 {"skiller.codex.connect.a123"} |
                                 {row.artifact.provenance.artifact_id for row in deploy.results})

    def test_exact_provider_artifact_adoption_updates_and_locks_targets(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(
            catalog, provider_id=provider,
            bindings_path=harness / provider.value / "mcp/bindings.json",
            selected=(), trusted=True) for provider in ProviderId)
        deploy = plan_provider_deploy(
            bases, semantic_servers(maind={"command": "maind"}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            preimages = {}
            for row in deploy.results:
                target = root / row.target_path
                target.parent.mkdir(parents=True, exist_ok=True)
                content = (b'approval_policy = "never"\n\n'
                           if row.provider_id is ProviderId.CODEX else
                           f"foreign {row.provider_id.value}\n".encode())
                target.write_bytes(content)
                preimages[row.target_path] = sha256_digest(target.read_bytes())

            adoption = plan_provider_artifact_adoption(
                root, deploy, preimage_hashes=preimages)
            self.assertEqual(
                [action.diagnostic for action in adoption.actions],
                ["explicit-adoption", "explicit-adoption"])
            apply_plan(root, adoption)

            for row in deploy.results:
                current = (root / row.target_path).read_bytes()
                if row.provider_id is ProviderId.CODEX:
                    self.assertTrue(current.startswith(
                        b'approval_policy = "never"\n\n'))
                    self.assertTrue(current.endswith(row.rendered))
                else:
                    self.assertEqual(current, row.rendered)
            self.assertTrue(
                (root / ".swissknifeman/provider-artifacts.lock.json").is_file())
            self.assertEqual(plan_provider_artifacts(root, deploy)["severity"], "green")

    def test_exact_adoption_already_desired_target_still_transfers_ownership(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        base = plan_mcp_projection(
            catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=harness / "claude-code/mcp/bindings.json",
            selected=(), trusted=True)
        deploy = plan_provider_deploy(
            (base,), semantic_servers(maind={"command": "maind"}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            row = deploy.results[0]
            target = root / row.target_path
            target.write_bytes(row.rendered)
            before = target.read_bytes()

            adoption = plan_provider_artifact_adoption(
                root, deploy, preimage_hashes={
                    row.target_path: sha256_digest(before)})
            self.assertEqual(
                [action.action for action in adoption.actions],
                [ArtifactActionKind.UPDATE])
            apply_plan(root, adoption)

            self.assertEqual(target.read_bytes(), before)
            self.assertTrue(
                (root / ".swissknifeman/provider-artifacts.lock.json").is_file())
            ordinary = plan_provider_artifacts(root, deploy)
            self.assertEqual(ordinary["severity"], "green")
            self.assertTrue(all(
                action.action is ArtifactActionKind.NOOP
                for action in ordinary["plan"].actions))

    def test_exact_provider_artifact_adoption_refuses_changed_preimage(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        base = plan_mcp_projection(
            catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=harness / "claude-code/mcp/bindings.json",
            selected=(), trusted=True)
        deploy = plan_provider_deploy(
            (base,), semantic_servers(maind={"command": "maind"}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / deploy.results[0].target_path
            target.write_text("foreign\n", encoding="utf-8")
            before = target.read_bytes()

            with self.assertRaisesRegex(
                    ProviderDeployError,
                    "MAIND_PROVIDER_ADOPTION_PREIMAGE_MISMATCH"):
                plan_provider_artifact_adoption(
                    root, deploy,
                    preimage_hashes={deploy.results[0].target_path:
                                     "sha256:" + "0" * 64})

            self.assertEqual(target.read_bytes(), before)
            self.assertFalse(
                (root / ".swissknifeman/provider-artifacts.lock.json").exists())

    def test_exact_adoption_preserves_owner_bytes_and_unrelated_lock_records(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        base = plan_mcp_projection(
            catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=harness / "claude-code/mcp/bindings.json",
            selected=(), trusted=True)
        deploy = plan_provider_deploy(
            (base,), semantic_servers(maind={"command": "maind"}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            mcp = root / ".mcp.json"
            mcp.write_text("foreign\n", encoding="utf-8")
            apply_plan(root, plan_provider_artifact_adoption(
                root, deploy, preimage_hashes={
                    ".mcp.json": sha256_digest(mcp.read_bytes())}))
            owner = root / "CLAUDE.md"
            owner.write_bytes(b"# Owner\n")
            source = ArtifactSource(
                "test.instructions", "test", sha256_digest(b"managed\n"))
            artifact = plan_artifact_render(ArtifactRenderRequest(
                "test.instructions.root", (source,),
                ArtifactTarget("CLAUDE.md", ("managed-blocks", ("instructions",))),
                ArtifactAdapterIdentity(
                    "test.instructions", "1.0.0", ProviderId.CLAUDE_CODE,
                    "1.0.0", ()), (), {}, lambda _request: b"managed\n"))

            def extract(raw, _ids):
                return b"managed\n" if raw.endswith(b"managed\n") else b""

            def replace_blocks(raw, managed, _ids):
                existing = b"managed\n" if raw.endswith(b"managed\n") else b""
                if existing:
                    return raw[:-len(existing)] + managed
                return raw + managed

            plan = plan_exact_artifact_adoption(
                root, (artifact,),
                preimage_hashes={"CLAUDE.md": sha256_digest(owner.read_bytes())},
                managed_block_codecs={
                    artifact.provenance.artifact_id: (extract, replace_blocks)})
            apply_plan(root, plan)

            self.assertEqual(owner.read_bytes(), b"# Owner\nmanaged\n")
            lock = parse_lock(
                (root / ".swissknifeman/provider-artifacts.lock.json").read_bytes())
            self.assertEqual(
                {record.artifact_id for record in lock.records},
                {"maind.provider-deploy.claude-code",
                 "test.instructions.root"})

    def test_d108_project_carrier_preserves_siblings_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".swissknife.json"
            path.write_text(json.dumps({"custom": {"keep": True}, "providers": {
                "contract_version": "1.0.0", "selection": {
                    "claude-code": {"enabled": False,
                                     "capabilities": {"mcp.catalog": True}}}}}),
                            encoding="utf-8")
            config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
            first = plan_project_carrier(root, config, "swissknifeman")
            self.assertTrue(first.changed)
            self.assertEqual(first.providers["selection"]["claude-code"]["enabled"], True)
            self.assertEqual(first.providers["selection"]["codex"]["enabled"], True)
            apply_project_carrier(first)
            value = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(value["custom"], {"keep": True})
            self.assertEqual(plan_project_carrier(root, config, "swissknifeman").changed, False)

    def test_d108_project_carrier_refuses_foreign_or_invalid_without_write(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / ".swissknife.json"
            path.write_text("[]", encoding="utf-8")
            config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
            before = path.read_bytes()
            with self.assertRaisesRegex(ProviderDeployError, "MAIND_D108_CARRIER_INVALID"):
                plan_project_carrier(root, config, "swissknifeman")
            with self.assertRaisesRegex(ProviderDeployError, "MAIND_D108_FOREIGN_PROJECT"):
                plan_project_carrier(root, config, "other")
            self.assertEqual(path.read_bytes(), before)

    def test_d108_plans_exact_dual_p5_bases_after_claude_only_current_selection(self):
        """D112: the carrier, not the caller's current P1 selection, owns D108 bases."""
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
            self.assertEqual(resolve_effective_providers(config, None, "swissknifeman"),
                             (ProviderId.CLAUDE_CODE,))
            carrier = plan_project_carrier(root, config, "swissknifeman")
            bases = _d108_planned_projections(config, "swissknifeman", carrier, harness)
            self.assertEqual(tuple(base.provider_id for base in bases),
                             (ProviderId.CLAUDE_CODE, ProviderId.CODEX))

    def test_d115_d108_adopts_only_the_sealed_unchanged_mcp_preimage(self):
        repo = Path(__file__).resolve().parents[3]
        harness = repo / "packages/harness/configs"
        sealed = _D108_MCP_PREIMAGE
        servers = (
            SemanticServer("maind", {"command": "maind"}),
            SemanticServer("perplexity-web", {"command": "pplx"}),
            SemanticServer("serena", {"command": "serena"}),
        )
        config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex").mkdir()
            (root / ".codex/hooks.json").write_bytes(_D104_PREIMAGE)
            (root / ".mcp.json").write_bytes(sealed)

            operation = plan_d108_operation(
                root, config, "swissknifeman", servers,
                harness_configs=harness, expected_root=root)
            mcp = next(action for action in operation.chained_plan.actions
                       if action.target_path == ".mcp.json")
            self.assertEqual(mcp.action.value, "noop")
            self.assertEqual(mcp.expected.managed_bytes, sealed)
            self.assertEqual(mcp.expected.provenance.rendered_hash,
                             sha256_digest(sealed))

            (root / ".mcp.json").write_bytes(sealed + b"\n")
            with self.assertRaisesRegex(ProviderDeployError, "MAIND_D108_CHAIN_REFUSED"):
                plan_d108_operation(root, config, "swissknifeman", servers,
                                    harness_configs=harness, expected_root=root)

    def test_d122_d108_second_identical_plan_and_apply_are_noops(self):
        repo = Path(__file__).resolve().parents[3]
        harness = repo / "packages/harness/configs"
        sealed = _D108_MCP_PREIMAGE
        servers = (SemanticServer("maind", {"command": "maind"}),
                   SemanticServer("perplexity-web", {"command": "pplx"}),
                   SemanticServer("serena", {"command": "serena"}))
        config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex").mkdir()
            (root / ".codex/hooks.json").write_bytes(_D104_PREIMAGE)
            (root / ".mcp.json").write_bytes(sealed)
            first = plan_d108_operation(root, config, "swissknifeman", servers,
                                        harness_configs=harness, expected_root=root)
            apply_d108_operation(root, first)
            lock_path = root / ".swissknifeman/provider-artifacts.lock.json"
            foreign = self.skiller_artifact()
            apply_plan(root, plan_artifact_lock(
                root, (foreign,), lock_bytes=lock_path.read_bytes(),
                owner_namespace="skiller.codex.connect"))
            before = {path.relative_to(root): path.read_bytes()
                      for path in root.rglob("*") if path.is_file()}

            second = plan_d108_operation(root, config, "swissknifeman", servers,
                                         harness_configs=harness, expected_root=root)
            self.assertFalse(second.carrier.changed)
            self.assertIn(foreign.provenance, second.chained_plan.next_lock.records)
            self.assertTrue(all(action.action.value == "noop"
                                for action in second.chained_plan.actions))
            with patch("maind.provider_deploy.apply_plan") as writer:
                apply_d108_operation(root, second)
            self.assertEqual(writer.call_count, 0)
            after = {path.relative_to(root): path.read_bytes()
                     for path in root.rglob("*") if path.is_file()}
            self.assertEqual(after, before)

    def test_d122_d108_rejects_malformed_or_changed_managed_observer_before_writer(self):
        repo = Path(__file__).resolve().parents[3]
        harness = repo / "packages/harness/configs"
        sealed = _D108_MCP_PREIMAGE
        servers = (SemanticServer("maind", {"command": "maind"}),
                   SemanticServer("perplexity-web", {"command": "pplx"}),
                   SemanticServer("serena", {"command": "serena"}))
        config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
        for name, mutate in (
                ("malformed", lambda group: group.clear()),
                ("changed", lambda group: group["hooks"][0].__setitem__("command", "python3 foreign.py"))):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".codex").mkdir()
                (root / ".codex/hooks.json").write_bytes(_D104_PREIMAGE)
                (root / ".mcp.json").write_bytes(sealed)
                first = plan_d108_operation(root, config, "swissknifeman", servers,
                                            harness_configs=harness, expected_root=root)
                apply_d108_operation(root, first)
                hooks_path = root / ".codex/hooks.json"
                hooks = json.loads(hooks_path.read_text(encoding="utf-8"))
                mutate(hooks["hooks"]["SessionStart"][1])
                hooks_path.write_text(json.dumps(hooks, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
                before = {path.relative_to(root): path.read_bytes()
                          for path in root.rglob("*") if path.is_file()}
                with patch("maind.provider_deploy.apply_plan") as writer:
                    with self.assertRaisesRegex(ProviderDeployError,
                                                "MAIND_PROVIDER_DEPLOY_REFUSED"):
                        plan_d108_operation(root, config, "swissknifeman", servers,
                                            harness_configs=harness, expected_root=root)
                self.assertEqual(writer.call_count, 0)
                after = {path.relative_to(root): path.read_bytes()
                         for path in root.rglob("*") if path.is_file()}
                self.assertEqual(after, before)

    def test_d123_rolls_back_the_recorded_d108_operation_and_carrier(self):
        repo = Path(__file__).resolve().parents[3]
        harness = repo / "packages/harness/configs"
        sealed = _D108_MCP_PREIMAGE
        servers = (SemanticServer("maind", {"command": "maind"}),
                   SemanticServer("perplexity-web", {"command": "pplx"}),
                   SemanticServer("serena", {"command": "serena"}))
        config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex").mkdir()
            (root / ".codex/hooks.json").write_bytes(_D104_PREIMAGE)
            (root / ".mcp.json").write_bytes(sealed)
            carrier_before = b'{"custom":{"preserve":true}}\n'
            (root / ".swissknife.json").write_bytes(carrier_before)
            before = {path.relative_to(root): path.read_bytes()
                      for path in root.rglob("*") if path.is_file()}
            operation = plan_d108_operation(root, config, "swissknifeman", servers,
                                            harness_configs=harness, expected_root=root)
            apply_d108_operation(root, operation)
            self.assertIs(rollback_d108_operation(root, operation), operation)
            after = {path.relative_to(root): path.read_bytes()
                     for path in root.rglob("*") if path.is_file()}
            self.assertEqual(after, before)

    def test_d123_refuses_changed_carrier_before_core_rollback(self):
        repo = Path(__file__).resolve().parents[3]
        harness = repo / "packages/harness/configs"
        sealed = _D108_MCP_PREIMAGE
        servers = (SemanticServer("maind", {"command": "maind"}),
                   SemanticServer("perplexity-web", {"command": "pplx"}),
                   SemanticServer("serena", {"command": "serena"}))
        config = merge_defaults({"projects": [{"id": "swissknifeman", "name": "SKM"}]})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex").mkdir()
            (root / ".codex/hooks.json").write_bytes(_D104_PREIMAGE)
            (root / ".mcp.json").write_bytes(sealed)
            operation = plan_d108_operation(root, config, "swissknifeman", servers,
                                            harness_configs=harness, expected_root=root)
            apply_d108_operation(root, operation)
            (root / ".swissknife.json").write_text('{"foreign":true}\n', encoding="utf-8")
            before = {path.relative_to(root): path.read_bytes()
                      for path in root.rglob("*") if path.is_file()}
            with patch("maind.provider_deploy.rollback_chained_bootstrap_transfer") as rollback:
                with self.assertRaisesRegex(ProviderDeployError,
                                            "MAIND_D108_ROLLBACK_CARRIER_CHANGED"):
                    rollback_d108_operation(root, operation)
            self.assertEqual(rollback.call_count, 0)
            after = {path.relative_to(root): path.read_bytes()
                     for path in root.rglob("*") if path.is_file()}
            self.assertEqual(after, before)

    def test_d104_transfer_composes_then_returns_to_normal_p2_repair(self):
        repo = Path(__file__).resolve().parents[3]
        harness = repo / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(
            catalog, provider_id=provider,
            bindings_path=harness / provider.value / "mcp/bindings.json",
            selected=(), trusted=True) for provider in ProviderId)
        deploy = plan_provider_deploy(bases, semantic_servers(maind={"command": "maind"}))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex/hooks").mkdir(parents=True)
            (root / ".codex/hooks.json").write_bytes(_D104_PREIMAGE)
            foreign = root / "foreign.txt"
            foreign.write_text("preserve", encoding="utf-8")

            transfer = plan_d104_bootstrap_transfer(root, harness_configs=harness)
            self.assertEqual([action.action.value for action in transfer.plan.actions],
                             ["update", "create"])
            apply_plan(root, transfer.plan)
            hooks = json.loads((root / ".codex/hooks.json").read_text(encoding="utf-8"))
            commands = [group["hooks"][0]["command"]
                        for group in hooks["hooks"]["SessionStart"]]
            self.assertEqual(commands[0],
                             "bash /home/vostrikov/projects/packages/swissknifeman/.claude/maind-memory.sh")
            self.assertEqual(len(commands), 2)
            self.assertTrue((root / ".codex/hooks/lifecycle.py").is_file())
            self.assertTrue((root / ".codex/hooks.json.provider-artifact.bootstrap-transfer.bak").is_file())

            checked = plan_provider_artifacts(root, deploy, extra_artifacts=transfer.artifacts)
            self.assertNotEqual(checked["severity"], "error")
            apply_provider_artifacts(root, deploy, extra_artifacts=transfer.artifacts)
            clean = plan_provider_artifacts(root, deploy, extra_artifacts=transfer.artifacts)
            self.assertEqual(clean["severity"], "green")
            self.assertTrue(all(action.action.value == "noop" for action in clean["plan"].actions))
            self.assertEqual(foreign.read_text(encoding="utf-8"), "preserve")

            (root / ".codex/hooks.json").write_bytes(
                (root / ".codex/hooks.json").read_bytes() + b"\n")
            self.assertEqual(plan_provider_artifacts(
                root, deploy, extra_artifacts=transfer.artifacts)["severity"], "error")
            apply_provider_artifacts(root, deploy, repair=True,
                                     extra_artifacts=transfer.artifacts)
            self.assertEqual(plan_provider_artifacts(
                root, deploy, extra_artifacts=transfer.artifacts)["severity"], "green")

    def test_d104_transfer_refuses_changed_preimage_or_existing_handler_without_writes(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        for changed, handler in ((True, False), (False, True)):
            with self.subTest(changed=changed, handler=handler), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                (root / ".codex/hooks").mkdir(parents=True)
                preimage = (_D104_PREIMAGE.replace(b"maind-memory.sh", b"other-memory.sh")
                            if changed else _D104_PREIMAGE)
                (root / ".codex/hooks.json").write_bytes(preimage)
                if handler:
                    (root / ".codex/hooks/lifecycle.py").write_text("foreign", encoding="utf-8")
                before = {path.relative_to(root): path.read_bytes()
                          for path in root.rglob("*") if path.is_file()}
                transfer = plan_d104_bootstrap_transfer(root, harness_configs=harness)
                self.assertTrue(all(action.action.value == "refuse" for action in transfer.plan.actions))
                after = {path.relative_to(root): path.read_bytes()
                         for path in root.rglob("*") if path.is_file()}
                self.assertEqual(after, before)

    def test_d104_transfer_rolls_back_a_temporary_interrupted_transaction(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".codex/hooks").mkdir(parents=True)
            hooks_path = root / ".codex/hooks.json"
            hooks_path.write_bytes(_D104_PREIMAGE)
            transfer = plan_d104_bootstrap_transfer(root, harness_configs=harness)

            def interrupted(_root, _admission, _results, state):
                if state == "created":
                    raise OSError("simulated interruption")

            with patch("core.provider.lock._bootstrap_write_state", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "simulated interruption"):
                    apply_plan(root, transfer.plan)
            self.assertEqual(hooks_path.read_bytes(), _D104_PREIMAGE)
            self.assertFalse((root / ".codex/hooks/lifecycle.py").exists())
            self.assertFalse((root / ".swissknifeman/provider-artifacts.lock.json").exists())

    def test_deploy_facade_requests_d104_transfer_only_for_the_absent_lock_candidate(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(
            catalog, provider_id=provider,
            bindings_path=harness / provider.value / "mcp/bindings.json",
            selected=(), trusted=True) for provider in ProviderId)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            target = Path(tmp) / "project"
            (target / ".codex/hooks").mkdir(parents=True)
            (target / ".codex/hooks.json").write_bytes(_D104_PREIMAGE)
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            first = deploy_project(env, config, config["projects"][0], with_code=False,
                                   provider_projections=bases)
            self.assertTrue(first["provider_changed"])
            self.assertTrue((target / ".codex/hooks/lifecycle.py").is_file())
            second = deploy_project(env, config, config["projects"][0], with_code=False,
                                    provider_projections=bases)
            self.assertFalse(second["provider_changed"])

    def test_deploy_facade_projects_d104_refusal_before_mcp_write(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(
            catalog, provider_id=provider,
            bindings_path=harness / provider.value / "mcp/bindings.json",
            selected=(), trusted=True) for provider in ProviderId)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            target = Path(tmp) / "project"
            (target / ".codex/hooks").mkdir(parents=True)
            hooks_path = target / ".codex/hooks.json"
            hooks_path.write_bytes(_D104_PREIMAGE.replace(
                b"maind-memory.sh", b"other-memory.sh"))
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            result = deploy_project(env, config, config["projects"][0], with_code=False,
                                    provider_projections=bases)
            self.assertEqual(result["bootstrap_transfer"]["status"], "refused")
            self.assertEqual(result["bootstrap_transfer"]["diagnostic"],
                             "MAIND_PROVIDER_DEPLOY_REFUSED")
            self.assertEqual(hooks_path.read_bytes(), _D104_PREIMAGE.replace(
                b"maind-memory.sh", b"other-memory.sh"))
            self.assertFalse((target / ".mcp.json").exists())

    def test_selected_transfer_and_unmanaged_mcp_refuse_before_every_write(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(
            catalog, provider_id=provider,
            bindings_path=harness / provider.value / "mcp/bindings.json",
            selected=(), trusted=True) for provider in ProviderId)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            target = Path(tmp) / "project"
            (target / ".codex/hooks").mkdir(parents=True)
            (target / ".codex/hooks.json").write_bytes(_D104_PREIMAGE)
            (target / ".mcp.json").write_text('{"mcpServers":{"foreign":{"command":"x"}}}',
                                                encoding="utf-8")
            before = {path.relative_to(target): path.read_bytes()
                      for path in target.rglob("*") if path.is_file()}
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            with patch("maind.provision.deploy.apply_plan") as writer:
                result = deploy_project(env, config, config["projects"][0], with_code=False,
                                        provider_projections=bases)
            self.assertEqual(result["bootstrap_transfer"]["status"], "admitted")
            self.assertEqual(result["provider_plan"].results[0].status, "failed")
            self.assertEqual(result["provider_plan"].results[0].diagnostic,
                             "unmanaged-target")
            self.assertEqual(writer.call_count, 0)
            after = {path.relative_to(target): path.read_bytes()
                     for path in target.rglob("*") if path.is_file()}
            self.assertEqual(after, before)

    def test_incomplete_existing_lock_or_handler_refuses_before_every_write(self):
        harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(
            catalog, provider_id=provider,
            bindings_path=harness / provider.value / "mcp/bindings.json",
            selected=(), trusted=True) for provider in ProviderId)
        for name, target_path, expected in (
                ("existing-lock", ".swissknifeman/provider-artifacts.lock.json",
                 "bootstrap-lock-present"),
                ("existing-handler", ".codex/hooks/lifecycle.py",
                 "bootstrap-created-target-present")):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                _, env = make_repo(tmp)
                target = Path(tmp) / "project"
                (target / ".codex/hooks").mkdir(parents=True)
                (target / ".codex/hooks.json").write_bytes(_D104_PREIMAGE)
                path = target / target_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("foreign", encoding="utf-8")
                before = {item.relative_to(target): item.read_bytes()
                          for item in target.rglob("*") if item.is_file()}
                config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                    "local_path": str(target), "memory_scope": "project:demo"}]})
                with patch("maind.provision.deploy.apply_plan") as writer:
                    result = deploy_project(env, config, config["projects"][0], with_code=False,
                                            provider_projections=bases)
                bootstrap = result["bootstrap_transfer"]
                self.assertEqual(bootstrap["status"], "refused")
                self.assertEqual(bootstrap["actions"][0]["diagnostic"], expected)
                self.assertEqual(writer.call_count, 0)
                after = {item.relative_to(target): item.read_bytes()
                         for item in target.rglob("*") if item.is_file()}
                self.assertEqual(after, before)

    def test_manifest_gate_refuses_missing_and_unsupported_before_render(self):
        repo = Path(__file__).resolve().parents[3]
        harness = repo / "packages/harness/configs"
        catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(
            catalog, provider_id=provider,
            bindings_path=harness / provider.value / "mcp/bindings.json",
            selected=(), trusted=True) for provider in ProviderId)
        servers = semantic_servers(maind={"command": "maind"})
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ProviderDeployError,
                                        "MAIND_CAPABILITY_MANIFEST_INVALID"):
                plan_provider_deploy(bases, servers, manifest_path=root / "missing.json")
            value = json.loads((repo / "configs/provider-capabilities.json").read_text())
            row = next(item for item in value["capabilities"]
                       if item["id"] == "mcp.catalog")["support"]["codex"]
            row.pop("adapter_id")
            row["level"] = "unsupported"
            row["diagnostic"] = "unsupported fixture; fail closed"
            path = root / "manifest.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            plan = plan_provider_deploy(bases, servers, manifest_path=path)
            self.assertFalse(plan.green)
            self.assertEqual(plan.results[1].diagnostic,
                             "MAIND_CAPABILITY_UNSUPPORTED:codex:mcp.catalog")

    def test_effective_provider_resolution_honors_operation_override_and_refuses_invalid(self):
        catalog = ProviderConfigCatalog("1.0.0", (ProviderId.CLAUDE_CODE, ProviderId.CODEX), (), ())
        config = merge_defaults({"projects": [{"id": "demo", "name": "Demo"}]})
        self.assertEqual(resolve_effective_providers(config, catalog, "demo"),
                         (ProviderId.CLAUDE_CODE,))
        operation = ProviderConfigLayer(ConfigSource("operation", "test", "operation", "/"), {
            "contract_version": "1.0.0", "selection": {"codex": {"enabled": True},
            "claude-code": {"enabled": False}}})
        self.assertEqual(resolve_effective_providers(config, catalog, "demo", operation=operation),
                         (ProviderId.CODEX,))
        unknown = ProviderConfigLayer(ConfigSource("operation", "test", "operation", "/"), {
            "contract_version": "1.0.0", "selection": {"unknown": {"enabled": True}}})
        with self.assertRaisesRegex(ProviderDeployError, "PCFG_UNKNOWN_PROVIDER"):
            resolve_effective_providers(config, catalog, "demo", operation=unknown)
        disabled = ProviderConfigLayer(ConfigSource("operation", "test", "operation", "/"), {
            "contract_version": "1.0.0", "selection": {"claude-code": {"enabled": False}}})
        with self.assertRaisesRegex(ProviderDeployError, "MAIND_PROVIDER_DISABLED"):
            resolve_effective_providers(config, catalog, "demo", operation=disabled)
    def test_caller_owned_semantics_use_p5_targets_and_renderers(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        servers = semantic_servers(maind={"command": "maind"},
            codegraph={"command": "uvx", "args": ["serena"]},
            perplexity={"command": "pplx"})
        plan = plan_provider_deploy(bases, servers)
        self.assertTrue(plan.green)
        self.assertEqual([row.target_path for row in plan.results], [".mcp.json", ".codex/config.toml"])
        self.assertTrue(all(b"maind" in row.rendered and b"codegraph" in row.rendered
                            for row in plan.results))
        self.assertTrue(all(row.artifact.provenance.target_path == row.target_path
                            for row in plan.results))
        self.assertTrue(all(row.artifact.provenance.canonical_sources[0].path ==
                            "packages/maind/lib/maind/provider_deploy.py" for row in plan.results))
        expected_hash = sha256_digest(canonical_json_bytes({"servers": [
            {"id": row.id, "binding": dict(row.binding)} for row in servers]}))
        self.assertTrue(all(row.artifact.provenance.canonical_sources[0].content_hash == expected_hash
                            for row in plan.results))

    def test_missing_disabled_and_selected_provider_are_tagged(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        claude = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        servers = semantic_servers(maind={"command": "maind"})
        plan = plan_provider_deploy((claude,), servers,
            selected=(ProviderId.CLAUDE_CODE, ProviderId.CODEX),
            required_providers=(ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        self.assertEqual([row.status for row in plan.results], ["planned", "failed"])
        self.assertEqual(plan.results[1].diagnostic, "MAIND_PROJECTION_MISSING")
        disabled = plan_provider_deploy((claude,), servers, selected=(ProviderId.CLAUDE_CODE,),
            disabled=(ProviderId.CLAUDE_CODE,))
        self.assertEqual(disabled.results[0].diagnostic, "MAIND_PROVIDER_DISABLED")

    def test_deploy_facade_preserves_semantic_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = Path(tmp) / "project"
            project_path.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(project_path), "memory_scope": "project:demo"}]})
            rows = provider_semantic_inventory(env, config, config["projects"][0],
                                               with_code=False, maind_server=True,
                                               with_agentmemory=False)
            self.assertEqual([row.id for row in rows], ["maind"])

    def test_project_extra_servers_join_provider_neutral_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = Path(tmp) / "project"
            project_path.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(project_path), "memory_scope": "project:demo",
                "mcp": {"extra_servers": {
                    "laravel-boost": {"command": "php", "args": ["artisan", "boost:mcp"]}}}}]})
            rows = provider_semantic_inventory(env, config, config["projects"][0],
                                               with_code=False, maind_server=True,
                                               with_agentmemory=False)
            self.assertEqual([row.id for row in rows], ["maind", "laravel-boost"])

    def test_provider_deploy_does_not_run_legacy_mcp_writer_twice(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            target = Path(tmp) / "project"
            target.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            result = deploy_project(env, config, config["projects"][0], with_code=False,
                                    provider_projections=bases)
            self.assertEqual(result["targets"], [".mcp.json", ".codex/config.toml"])
            self.assertEqual(json.loads((target / ".mcp.json").read_text())["mcpServers"],
                             {"maind": {"command": "maind",
                                        "args": ["mcp", "--scope", "project:demo"]}})

    def test_full_semantic_inventory_and_duplicate_server_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = Path(tmp) / "project"; project_path.mkdir()
            config = merge_defaults({"mcp": {"perplexity_web": {"enabled": True}},
                "projects": [{"id": "demo", "name": "Demo", "local_path": str(project_path),
                              "memory_scope": "project:demo", "code_graph": {"enabled": True}}]})
            rows = provider_semantic_inventory(env, config, config["projects"][0], with_code=True,
                                               maind_server=True, with_agentmemory=True)
            self.assertEqual([row.id for row in rows], ["maind", "agentmemory", "codegraph", "perplexity"])
        with self.assertRaisesRegex(ProviderDeployError, "MAIND_SEMANTIC_SERVER_DUPLICATE"):
            plan_provider_deploy((), (semantic_servers(maind={"command": "maind"})[0],) * 2)

    def test_d108_inventory_uses_configured_server_names_without_changing_bindings(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            project_path = Path("/tmp/d108-canonical")
            config = merge_defaults({"mcp": {"perplexity_web": {"enabled": True}},
                "projects": [{"id": "swissknifeman", "name": "SKM",
                              "local_path": str(project_path), "memory_scope": "project:skm",
                              "code_graph": {"enabled": True}}]})
            project = config["projects"][0]
            ordinary = provider_semantic_inventory(env, config, project, with_code=True,
                                                   maind_server=True, with_agentmemory=False)
            d108 = provider_semantic_inventory(env, config, project, with_code=True,
                                               maind_server=True, with_agentmemory=False, d108=True)
            self.assertEqual([row.id for row in ordinary], ["maind", "codegraph", "perplexity"])
            self.assertEqual([row.id for row in d108], ["maind", "serena", "perplexity-web"])
            self.assertEqual([dict(row.binding) for row in d108],
                             [dict(row.binding) for row in ordinary])
            harness = Path(__file__).resolve().parents[3] / "packages/harness/configs"
            catalog = load_mcp_catalog(harness / "common/mcp/catalog.json")
            bases = tuple(plan_mcp_projection(
                catalog, provider_id=provider,
                bindings_path=harness / provider.value / "mcp/bindings.json",
                selected=(), trusted=True) for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
            plan = plan_provider_deploy(bases, d108)
            claude = next(row for row in plan.results if row.provider_id is ProviderId.CLAUDE_CODE)
            self.assertEqual(sha256_digest(claude.rendered),
                             "sha256:1d6d757436dc238647a841e6bb7c9efdfa137d5f82c680b7a88d28f1c325fd9d")

    def test_facade_executes_provider_plan_and_dry_is_no_write(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp); target = Path(tmp) / "project"; target.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            project = config["projects"][0]
            deploy_project(env, config, project, with_code=False, provider_projections=bases, dry=True)
            self.assertFalse((target / ".codex/config.toml").exists())
            deploy_project(env, config, project, with_code=False, provider_projections=bases)
            self.assertTrue((target / ".mcp.json").exists())
            self.assertTrue((target / ".codex/config.toml").exists())
            (target / ".mcp.json").write_bytes((target / ".mcp.json").read_bytes() + b"\n")
            refused = deploy_project(env, config, project, with_code=False,
                                     provider_projections=bases)
            self.assertEqual(refused["provider_plan"].results[0].status, "failed")
            deploy_project(env, config, project, with_code=False, provider_projections=bases,
                           provider_repair=True)
            self.assertNotEqual(plan_provider_artifacts(target, plan_provider_deploy(
                bases, semantic_servers(maind={"command": "maind"}))) ["severity"], "error")

    def test_secret_reference_is_preserved_without_resolved_value(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        base = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        codex = plan_mcp_projection(catalog, provider_id=ProviderId.CODEX,
            bindings_path=root / "codex/mcp/bindings.json", selected=(), trusted=True)
        plan = plan_provider_deploy((base, codex), semantic_servers(maind={"command": "maind",
            "env": {"TOKEN": "${MAIND_TOKEN}", "UNRELATED": "resolved-secret-value"}}),
            secret_values=("resolved-secret-value",))
        rendered = plan.results[0].rendered.decode("utf-8")
        self.assertIn("${MAIND_TOKEN}", rendered)
        self.assertNotIn("resolved-secret-value", rendered)
        self.assertNotIn("resolved-secret-value", conformance_report(plan))
        self.assertTrue(all(b"${SECRET_REF}" in row.rendered for row in plan.results))

    def test_duplicate_provider_projections_are_refused(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        claude = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        with self.assertRaisesRegex(ProviderDeployError, "MAIND_PROVIDER_DUPLICATE"):
            plan_provider_deploy((claude, claude), semantic_servers(maind={"command": "maind"}))

    def test_consumer_inventory_projects_claude_and_codex_outputs(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp); target = Path(tmp) / "project"; target.mkdir()
            config = merge_defaults({"mcp": {"perplexity_web": {"enabled": True}}, "projects": [{
                "id": "demo", "name": "Demo", "local_path": str(target), "memory_scope": "project:demo",
                "code_graph": {"enabled": True}}]})
            rows = provider_semantic_inventory(env, config, config["projects"][0], with_code=True,
                                               maind_server=True, with_agentmemory=False)
            plan = plan_provider_deploy(bases, rows)
            apply_provider_artifacts(target, plan)
            claude, codex = (target / ".mcp.json").read_bytes(), (target / ".codex/config.toml").read_bytes()
            self.assertIn(b'"codegraph"', claude); self.assertIn(b'"perplexity"', claude)
            self.assertIn(b"[mcp_servers.codegraph]", codex); self.assertIn(b"[mcp_servers.perplexity]", codex)

    def test_temp_conformance_is_no_write_deterministic_and_preserves_foreign(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        servers = semantic_servers(maind={"command": "maind"}, codegraph={"command": "uvx"})
        first, second = plan_provider_deploy(bases, servers), plan_provider_deploy(bases, servers)
        self.assertEqual([row.rendered for row in first.results], [row.rendered for row in second.results])
        with tempfile.TemporaryDirectory() as tmp:
            foreign = Path(tmp) / "foreign.json"
            foreign.write_text('{"foreign":true}', encoding="utf-8")
            evidence = Path(tmp) / "evidence.md"
            write_conformance_report(evidence, first)
            self.assertEqual(foreign.read_text(encoding="utf-8"), '{"foreign":true}')
            self.assertIn("Aggregate:** GREEN", evidence.read_text(encoding="utf-8"))

    def test_mark_deployed_keeps_legacy_fields_and_provider_tagged_state(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        plan = plan_provider_deploy(bases, semantic_servers(maind={"command": "maind"}))
        config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
            "local_path": "/tmp/demo", "memory_scope": "project:demo"}]})
        result = {"servers": ["maind"], "code": "disabled", "code_server": "serena",
                  "targets": [".mcp.json"], "scope": "project:demo", "provider_plan": plan}
        saved = mark_deployed(config, "demo", result)
        project = saved["projects"][0]
        self.assertEqual(project["mcp"]["targets"], [".mcp.json"])
        self.assertEqual(project["provider_deploy"]["claude-code"]["status"], "planned")
        self.assertEqual(project["provider_deploy"]["codex"]["target_path"], ".codex/config.toml")

    def test_worktree_local_cli_generates_conformance_report(self):
        launcher = Path(__file__).resolve().parents[1] / "bin/maind"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "P6-provider-deploy-conformance.md"
            result = subprocess.run([str(launcher), "deploy", "--conformance", str(output)],
                                    text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("| codex | .codex/config.toml | planned |", output.read_text(encoding="utf-8"))

    def test_provider_artifact_check_apply_repair_is_no_write_and_deterministic(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        bases = tuple(plan_mcp_projection(catalog, provider_id=provider,
            bindings_path=root / provider.value / "mcp/bindings.json", selected=(), trusted=True)
            for provider in (ProviderId.CLAUDE_CODE, ProviderId.CODEX))
        deploy = plan_provider_deploy(bases, semantic_servers(maind={"command": "maind"}))
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            checked = plan_provider_artifacts(target, deploy)
            self.assertFalse((target / ".mcp.json").exists())
            self.assertEqual(checked["mode"], "check")
            apply_provider_artifacts(target, deploy)
            self.assertTrue((target / ".mcp.json").exists())
            self.assertEqual(plan_provider_artifacts(target, deploy)["severity"], "green")
            (target / ".mcp.json").write_bytes((target / ".mcp.json").read_bytes() + b"\n")
            self.assertEqual(plan_provider_artifacts(target, deploy)["severity"], "error")
            repaired = plan_provider_artifacts(target, deploy, repair=True)
            self.assertEqual(repaired["mode"], "repair")
            apply_provider_artifacts(target, deploy, repair=True)
            self.assertEqual(plan_provider_artifacts(target, deploy)["severity"], "green")
            (target / ".mcp.json").write_text('{"foreign": true}', encoding="utf-8")
            self.assertEqual(plan_provider_artifacts(target, deploy)["severity"], "error")

    def test_provider_managed_emit_example_writes_portable_template_and_gitignore(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        claude = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            target = Path(tmp) / "project"
            target.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            deploy_project(env, config, config["projects"][0], with_code=False,
                           provider_projections=(claude,))
            self.assertTrue((target / ".mcp.json.example").is_file())
            example = json.loads((target / ".mcp.json.example").read_text())
            real = json.loads((target / ".mcp.json").read_text())
            self.assertEqual(example, real)  # только серверы maind — плейсхолдеров нет
            gitignore = (target / ".gitignore").read_text().splitlines()
            self.assertIn(".mcp.json", gitignore)
            self.assertNotIn(".mcp.json.example", gitignore)

    def test_provider_managed_emit_example_opt_out(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        claude = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            target = Path(tmp) / "project"
            target.mkdir()
            config = merge_defaults({"mcp": {"emit_example": False},
                "projects": [{"id": "demo", "name": "Demo", "local_path": str(target),
                              "memory_scope": "project:demo"}]})
            deploy_project(env, config, config["projects"][0], with_code=False,
                           provider_projections=(claude,))
            self.assertTrue((target / ".mcp.json").is_file())
            self.assertFalse((target / ".mcp.json.example").exists())
            self.assertFalse((target / ".gitignore").exists())

    def test_provider_managed_emit_example_skips_refused_row(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        claude = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            target = Path(tmp) / "project"
            target.mkdir()
            (target / ".mcp.json").write_text('{"mcpServers":{"foreign":{"command":"x"}}}',
                                                encoding="utf-8")
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            result = deploy_project(env, config, config["projects"][0], with_code=False,
                                    provider_projections=(claude,))
            self.assertEqual(result["provider_plan"].results[0].status, "failed")
            self.assertEqual(result["provider_plan"].results[0].diagnostic, "unmanaged-target")
            self.assertFalse((target / ".mcp.json.example").exists())
            self.assertFalse((target / ".gitignore").exists())

    def test_provider_managed_emit_example_dry_run_is_no_write(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        claude = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            target = Path(tmp) / "project"
            target.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            deploy_project(env, config, config["projects"][0], with_code=False,
                           provider_projections=(claude,), dry=True)
            self.assertFalse((target / ".mcp.json").exists())
            self.assertFalse((target / ".mcp.json.example").exists())
            self.assertFalse((target / ".gitignore").exists())

    def test_provider_managed_emit_example_repeat_is_idempotent(self):
        root = Path(__file__).resolve().parents[3] / "packages/harness/configs"
        catalog = load_mcp_catalog(root / "common/mcp/catalog.json")
        claude = plan_mcp_projection(catalog, provider_id=ProviderId.CLAUDE_CODE,
            bindings_path=root / "claude-code/mcp/bindings.json", selected=(), trusted=True)
        with tempfile.TemporaryDirectory() as tmp:
            _, env = make_repo(tmp)
            target = Path(tmp) / "project"
            target.mkdir()
            config = merge_defaults({"projects": [{"id": "demo", "name": "Demo",
                "local_path": str(target), "memory_scope": "project:demo"}]})
            deploy_project(env, config, config["projects"][0], with_code=False,
                           provider_projections=(claude,))
            example_path = target / ".mcp.json.example"
            self.assertTrue(example_path.is_file())
            example_path.chmod(0o444)          # переписать нельзя — второй прогон обязан не писать
            try:
                deploy_project(env, config, config["projects"][0], with_code=False,
                               provider_projections=(claude,))
            finally:
                example_path.chmod(0o644)


if __name__ == "__main__":
    unittest.main()
