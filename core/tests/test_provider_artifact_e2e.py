"""Synthetic P2 conformance for render, lock, preview, doctor, apply, and repair.

Every root passed to the artifact engine is a ``TemporaryDirectory``.  The
protected-path test deliberately keeps repository, FOREMAN, and fleet sentinels
outside that root, proving this harness cannot write them by accident.
"""
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from core import (AdapterCatalog, AdapterDescriptor, ArtifactAdapterIdentity,
                  ArtifactActionKind, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, CapabilityId, CapabilityRequirement,
                  CapabilitySupport, DriftObservation, EffectiveProvider,
                  ProviderConfigCatalog, ProviderId, SupportLevel, apply_plan,
                  plan_artifact_lock, plan_artifact_render, serialize_lock)
import core.provider_lock as provider_lock
from core.provider_lock import (artifact_doctor, artifact_dry_run,
                                render_artifact_projection)


HASH = "sha256:" + "a" * 64
_BLOCK_MARKER = re.compile(rb"(?m)^<<(\/)?([a-z0-9-]+)>>\n")


def _fixture_blocks(file_bytes, ordered_block_ids):
    blocks = []
    opened = None
    start = None
    for match in _BLOCK_MARKER.finditer(file_bytes):
        closing, block_id = match.group(1), match.group(2).decode()
        if closing is None:
            if opened is not None:
                raise ValueError("nested fixture block")
            opened, start = block_id, match.start()
        elif opened != block_id:
            raise ValueError("missing or reordered fixture block")
        else:
            blocks.append((opened, start, match.end(), file_bytes[start:match.end()]))
            opened, start = None, None
    if opened is not None or tuple(block[0] for block in blocks) != ordered_block_ids:
        raise ValueError("duplicate, missing, or reordered fixture block")
    return blocks


def _fixture_extract(file_bytes, ordered_block_ids):
    return b"".join(block[3] for block in _fixture_blocks(file_bytes, ordered_block_ids))


def _fixture_replace(file_bytes, managed_bytes, ordered_block_ids):
    if not file_bytes:
        _fixture_blocks(managed_bytes, ordered_block_ids)
        return managed_bytes
    original = _fixture_blocks(file_bytes, ordered_block_ids)
    replacement = _fixture_blocks(managed_bytes, ordered_block_ids)
    cursor = 0
    parts = []
    for old, new in zip(original, replacement):
        parts.extend((file_bytes[cursor:old[1]], new[3]))
        cursor = old[2]
    return b"".join(parts) + file_bytes[cursor:]


FIXTURE_CODEC = (_fixture_extract, _fixture_replace)


def _catalog():
    skills = CapabilityId("skills.repository")
    hooks = CapabilityId("hooks.lifecycle")
    return ProviderConfigCatalog(
        "1.0.0", (ProviderId.CLAUDE_CODE, ProviderId.CODEX),
        (CapabilitySupport(skills, ProviderId.CLAUDE_CODE, SupportLevel.NATIVE),
         CapabilitySupport(skills, ProviderId.CODEX, SupportLevel.ADAPTED),
         CapabilitySupport(hooks, ProviderId.CODEX, SupportLevel.UNSUPPORTED)), ())


def _descriptor(provider: ProviderId, *, requirement=None):
    requirement = requirement or CapabilityRequirement(
        CapabilityId("skills.repository"), (SupportLevel.NATIVE, SupportLevel.ADAPTED))
    identity = ArtifactAdapterIdentity(
        f"fixture.{provider.value}", "1.0.0", provider, "1.0.0", (requirement,))
    return AdapterDescriptor("fixture.artifact", identity,
                             lambda request: f"{request.adapter.provider_id.value} fixture\n".encode())


def _request(identity: ArtifactAdapterIdentity, *, artifact_id="fixture.codex",
             target="generated/codex.txt", version="1.0.0", source_hash=HASH):
    adapter = ArtifactAdapterIdentity(identity.adapter_id, version, identity.provider_id,
                                      identity.capability_catalog_version,
                                      identity.capability_requirements)
    return ArtifactRenderRequest(
        artifact_id, (ArtifactSource("fixture.source", "fixtures/source.md", source_hash),),
        ArtifactTarget(target, ("whole-file", ())), adapter, (),
        {"fixture": artifact_id}, lambda request: f"{request.adapter.provider_id.value}:{version}\n".encode())


class ProviderArtifactEndToEndTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "managed"
        self.root.mkdir()
        self.catalog = _catalog()
        self.codex = _descriptor(ProviderId.CODEX)
        self.claude = _descriptor(ProviderId.CLAUDE_CODE)
        self.registry = AdapterCatalog((self.codex, self.claude))

    def tearDown(self):
        self.temp.cleanup()

    def render(self, provider=ProviderId.CODEX, *, artifact_id="fixture.codex",
               target="generated/codex.txt", version="1.0.0", source_hash=HASH):
        selected = self.registry.select(
            provider_id=provider, artifact_kind="fixture.artifact",
            capability_catalog=self.catalog, effective_provider=EffectiveProvider(provider, True))
        self.assertIsNotNone(selected.selection)
        return self.registry.plan_render(selected, _request(
            selected.selection.descriptor.identity, artifact_id=artifact_id,
            target=target, version=version, source_hash=source_hash))

    def plan(self, expected, lock_bytes=None, **kwargs):
        return plan_artifact_lock(self.root, (expected,), lock_bytes=lock_bytes, **kwargs)

    def render_blocks(self, *, project_override=False):
        selected = self.registry.select(
            provider_id=ProviderId.CODEX, artifact_kind="fixture.artifact",
            capability_catalog=self.catalog, effective_provider=EffectiveProvider(ProviderId.CODEX, True))
        self.assertIsNotNone(selected.selection)
        identity = selected.selection.descriptor.identity
        overrides = ()
        label = b"default"
        if project_override:
            overrides = ({"id": "project", "owner": "project", "order": 0,
                          "provenance": {"path": ".swissknife.json", "hash": HASH}},)
            label = b"project"
        return plan_artifact_render(ArtifactRenderRequest(
            "fixture.codex.blocks",
            (ArtifactSource("fixture.source", "fixtures/source.md", HASH),),
            ArtifactTarget("generated/managed.txt", ("managed-blocks", ("common", "codex"))),
            identity, overrides, {"fixture": "blocks"},
            lambda _request: (b"<<common>>\ncommon=" + label + b"\n<</common>>\n"
                              b"<<codex>>\ncodex=" + label + b"\n<</codex>>\n"),
        ))

    def test_two_provider_adapters_render_in_one_canonical_order(self):
        codex = self.render()
        claude = self.render(ProviderId.CLAUDE_CODE, artifact_id="fixture.claude",
                             target="generated/claude.txt")
        plan = plan_artifact_lock(self.root, (codex, claude), lock_bytes=None)
        self.assertEqual([action.artifact_id for action in plan.actions],
                         ["fixture.claude", "fixture.codex"])
        self.assertEqual([action.action for action in plan.actions],
                         [ArtifactActionKind.CREATE, ArtifactActionKind.CREATE])

    def test_preview_and_apply_share_one_plan_and_preview_is_no_write(self):
        expected = self.render()
        plan = self.plan(expected)
        before = self._tree_snapshot(self.root)
        first = artifact_dry_run(plan)
        second = artifact_dry_run(plan)
        self.assertEqual(first, second)
        self.assertEqual(before, self._tree_snapshot(self.root))
        self.assertEqual(first["exit_severity"], "warning")
        self.assertIn("fixture.codex: missing → create", render_artifact_projection(first))

        applied = apply_plan(self.root, plan)
        self.assertEqual(artifact_doctor(applied)["plan_id"], artifact_dry_run(applied)["plan_id"])
        self.assertEqual(artifact_doctor(applied)["exit_severity"], "green")
        self.assertEqual(applied.actions[0].action, ArtifactActionKind.NOOP)

    def test_all_frozen_drift_and_capability_cases_have_stable_projection(self):
        expected = self.render()
        initial = self.plan(expected)
        apply_plan(self.root, initial)
        lock = serialize_lock(initial.next_lock)
        target = self.root / expected.target.path
        stale = self.render(source_hash="sha256:" + "b" * 64)
        stale_source = self.plan(stale, lock)
        target.write_bytes(b"manual local edit\n")
        managed_drift = self.plan(expected, lock)
        repair = self.plan(expected, lock,
                           repair_artifact_ids=(expected.provenance.artifact_id,))
        target.write_bytes(expected.managed_bytes)
        clean = self.plan(expected, lock)
        target.unlink()
        missing = self.plan(expected, lock)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"unmanaged\n")
        unmanaged = self.plan(expected, None)
        corrupt = self.plan(expected, b"{")
        unsupported_requirement = CapabilityRequirement(
            CapabilityId("hooks.lifecycle"), (SupportLevel.NATIVE,))
        unsupported_descriptor = _descriptor(ProviderId.CODEX, requirement=unsupported_requirement)
        refusal = AdapterCatalog((unsupported_descriptor,)).select(
            provider_id=ProviderId.CODEX, artifact_kind="fixture.artifact",
            capability_catalog=self.catalog, effective_provider=EffectiveProvider(ProviderId.CODEX, True))
        self.assertEqual(refusal.diagnostics[0].code, "REGISTRY_CAPABILITY_UNSUPPORTED")
        unsupported = self.plan(expected, lock,
                                unsupported_artifact_ids=(expected.provenance.artifact_id,))

        cases = (
            ("clean", clean, DriftObservation.CLEAN, ArtifactActionKind.NOOP, "green"),
            ("source-change", stale_source, DriftObservation.STALE_SOURCE, ArtifactActionKind.UPDATE, "warning"),
            ("local-drift", managed_drift, DriftObservation.MANAGED_DRIFT, ArtifactActionKind.REFUSE, "error"),
            ("missing", missing, DriftObservation.MISSING, ArtifactActionKind.CREATE, "warning"),
            ("unmanaged", unmanaged, DriftObservation.OWNERSHIP_CONFLICT, ArtifactActionKind.REFUSE, "error"),
            ("corrupt-lock", corrupt, DriftObservation.PROVENANCE_INVALID, ArtifactActionKind.REFUSE, "error"),
            ("unsupported-capability", unsupported, DriftObservation.UNSUPPORTED, ArtifactActionKind.REFUSE, "error"),
            ("repair", repair, DriftObservation.MANAGED_DRIFT, ArtifactActionKind.REPAIR, "warning"),
        )
        for name, plan, observation, action, severity in cases:
            with self.subTest(case=name):
                preview = artifact_dry_run(plan)
                self.assertEqual((plan.actions[0].observation, plan.actions[0].action),
                                 (observation, action))
                self.assertEqual(preview["exit_severity"], severity)
                self.assertIn(observation.value, render_artifact_projection(preview))

    def test_repair_returns_clean_doctor_and_second_apply_is_noop(self):
        expected = self.render()
        initial = self.plan(expected)
        apply_plan(self.root, initial)
        lock = serialize_lock(initial.next_lock)
        target = self.root / expected.target.path
        target.write_bytes(b"local edit\n")
        repair = self.plan(expected, lock,
                           repair_artifact_ids=(expected.provenance.artifact_id,))
        applied = apply_plan(self.root, repair)
        self.assertEqual(artifact_doctor(applied)["exit_severity"], "green")
        self.assertEqual(applied.actions[0].action, ArtifactActionKind.NOOP)
        self.assertEqual(target.with_name(target.name + ".provider-artifact.bak").read_bytes(),
                         b"local edit\n")

    def test_managed_blocks_preserve_outside_bytes_and_project_override_is_stale_source(self):
        initial = self.render_blocks()
        created = self.plan(initial, managed_block_codecs={initial.provenance.artifact_id: FIXTURE_CODEC})
        applied = apply_plan(self.root, created)
        target = self.root / initial.target.path
        target.write_bytes(target.read_bytes().replace(
            b"<</common>>\n", b"<</common>>\nproject-between\n", 1).replace(
                b"<<common>>\n", b"project-prefix\n<<common>>\n", 1) + b"project-suffix\n")
        override = self.render_blocks(project_override=True)
        update = self.plan(override, serialize_lock(applied.next_lock),
                           managed_block_codecs={override.provenance.artifact_id: FIXTURE_CODEC})
        self.assertEqual((update.actions[0].observation, update.actions[0].action),
                         (DriftObservation.STALE_SOURCE, ArtifactActionKind.UPDATE))
        apply_plan(self.root, update)
        self.assertEqual(target.read_bytes(),
                         b"project-prefix\n<<common>>\ncommon=project\n<</common>>\n"
                         b"project-between\n<<codex>>\ncodex=project\n<</codex>>\nproject-suffix\n")

    def test_invalid_managed_boundaries_refuse_without_writer(self):
        expected = self.render_blocks()
        initial = self.plan(expected, managed_block_codecs={expected.provenance.artifact_id: FIXTURE_CODEC})
        applied = apply_plan(self.root, initial)
        target = self.root / expected.target.path
        valid = target.read_bytes()
        invalid = {
            "duplicate": valid + b"<<common>>\nagain\n<</common>>\n",
            "nested": valid.replace(b"common=default\n", b"common=default\n<<codex>>\n", 1),
            "missing": valid.replace(b"<</codex>>\n", b"", 1),
            "reordered": (b"<<codex>>\ncodex=default\n<</codex>>\n"
                          b"<<common>>\ncommon=default\n<</common>>\n"),
        }
        for name, value in invalid.items():
            with self.subTest(case=name):
                target.write_bytes(value)
                plan = self.plan(expected, serialize_lock(applied.next_lock),
                                 managed_block_codecs={expected.provenance.artifact_id: FIXTURE_CODEC})
                self.assertEqual((plan.actions[0].observation, plan.actions[0].action),
                                 (DriftObservation.BOUNDARY_INVALID, ArtifactActionKind.REFUSE))
                before = target.read_bytes()
                with patch.object(provider_lock, "_atomic_write_bytes", wraps=provider_lock._atomic_write_bytes) as writer:
                    with self.assertRaises(ValueError):
                        apply_plan(self.root, plan)
                self.assertEqual(writer.call_count, 0)
                self.assertEqual(target.read_bytes(), before)

    def test_protected_repo_foreman_and_fleet_sentinels_remain_unchanged(self):
        protected = Path(self.temp.name) / "protected"
        sentinels = {
            protected / "repository" / "config.json": b'{"owner":true}\n',
            protected / "FOREMAN" / "plan.md": b"FOREMAN protected\n",
            protected / "external-fleet" / "config.json": b"fleet protected\n",
        }
        for path, content in sentinels.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        before = {path: path.read_bytes() for path in sentinels}
        plan = self.plan(self.render())
        artifact_dry_run(plan)
        artifact_doctor(plan)
        apply_plan(self.root, plan)
        self.assertEqual({path: path.read_bytes() for path in sentinels}, before)

    @staticmethod
    def _tree_snapshot(root):
        if not root.exists():
            return ()
        return tuple(sorted((path.relative_to(root).as_posix(), path.read_bytes())
                            for path in root.rglob("*") if path.is_file()))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
