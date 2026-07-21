"""Conformance tests for the pure P2.1 artifact render seam."""
import unittest

from core import (ArtifactAdapterIdentity, ArtifactRenderRequest, ArtifactSource,
                  ArtifactTarget, CapabilityId, CapabilityRequirement, ProviderId,
                  SupportLevel, canonical_json_bytes, plan_artifact_render,
                  sha256_digest, validate_target_path)


SOURCE_HASH_A = "sha256:" + "a" * 64
SOURCE_HASH_B = "sha256:" + "b" * 64


def _adapter():
    return ArtifactAdapterIdentity(
        "task.codex-skill", "1.0.0", ProviderId.CODEX, "1.0.0",
        (CapabilityRequirement(CapabilityId("skills.repository"),
                               (SupportLevel.ADAPTED, SupportLevel.NATIVE)),),
    )


def _request(*, sources, target=None, override_layers=(), semantic_parameters=None, renderer=None):
    return ArtifactRenderRequest(
        "task.plan-exec.codex-skill", tuple(sources),
        target or ArtifactTarget(".agents/skills/task-plan-exec/SKILL.md", ("whole-file", ())),
        _adapter(), override_layers, semantic_parameters or {"title": "Plan exec"},
        renderer or (lambda _request: b"---\nname: task-plan-exec\n---\nbody\n"),
    )


class ProviderArtifactTests(unittest.TestCase):
    def test_canonical_json_is_sorted_compact_utf8(self):
        self.assertEqual(canonical_json_bytes({"z": "ёж", "a": [True, None]}),
                         b'{"a":[true,null],"z":"\xd1\x91\xd0\xb6"}')
        self.assertEqual(sha256_digest(b"artifact\n"),
                         "sha256:5b3513f580c8397212ff2c8f459c199efc0c90e4354a5f3533adf0a3fff3a530")

    def test_same_semantics_have_same_bytes_and_hashes_despite_mapping_order(self):
        sources = (
            ArtifactSource("task.command.plan-exec", "packages/task/commands/plan-exec.md", SOURCE_HASH_A),
            ArtifactSource("task.shared.policy", "packages/task/policy.md", SOURCE_HASH_B),
        )
        first = _request(
            sources=sources,
            semantic_parameters={"z": {"second": 2, "first": 1}, "a": ["one", "two"]},
        )
        second = _request(
            sources=tuple(reversed(sources)),
            semantic_parameters={"a": ["one", "two"], "z": {"first": 1, "second": 2}},
        )
        one = plan_artifact_render(first)
        two = plan_artifact_render(second)
        self.assertEqual(one.managed_bytes, two.managed_bytes)
        self.assertEqual(one.provenance.source_hash, two.provenance.source_hash)
        self.assertEqual(one.provenance.rendered_hash, two.provenance.rendered_hash)
        self.assertEqual(one.provenance.canonical_sources, two.provenance.canonical_sources)

    def test_renderer_runs_once_and_preserves_shebang_then_frontmatter(self):
        calls = []

        def renderer(request):
            calls.append(request.artifact_id)
            return (b"#!/usr/bin/env python3\n---\nname: task-plan-exec\n"
                    b"artifact-id: task.plan-exec.codex-skill\n---\nprint('ok')\n")

        result = plan_artifact_render(_request(
            sources=(ArtifactSource("task.command.plan-exec", "packages/task/commands/plan-exec.md", SOURCE_HASH_A),),
            renderer=renderer,
        ))
        self.assertEqual(calls, ["task.plan-exec.codex-skill"])
        self.assertTrue(result.managed_bytes.startswith(b"#!/usr/bin/env python3\n---\n"))
        self.assertNotIn(b"rendered_hash", result.managed_bytes)
        self.assertEqual(result.provenance.target_path, ".agents/skills/task-plan-exec/SKILL.md")
        self.assertEqual(result.provenance.rendered_hash, sha256_digest(result.managed_bytes))
        self.assertEqual(result.provenance.managed_boundary, ("whole-file", ()))

    def test_managed_block_boundary_and_ordered_overrides_are_sidecar_provenance(self):
        target = ArtifactTarget(".claude/CLAUDE.md", ("managed-blocks", ("common", "codex")))
        request = ArtifactRenderRequest(
            "root.instructions.codex", (ArtifactSource("root.common", "instructions/common.md", SOURCE_HASH_A),),
            target, _adapter(),
            ({"id": "operation", "owner": "operation", "order": 0,
              "provenance": {"source": "request"}},
             {"id": "project", "owner": "project", "order": 1,
              "provenance": {"path": ".swissknife.json"}}),
            {"language": "ru"}, lambda _request: b"<!-- common -->\n<!-- codex -->\n",
        )
        result = plan_artifact_render(request)
        self.assertEqual(result.provenance.override_layers,
                         ((("id", "operation"), ("order", 0), ("owner", "operation"),
                           ("provenance", {"source": "request"})),
                          (("id", "project"), ("order", 1), ("owner", "project"),
                           ("provenance", {"path": ".swissknife.json"}))))
        self.assertEqual(result.provenance.managed_boundary, ("managed-blocks", ("common", "codex")))

    def test_rejects_malformed_or_ambiguous_override_layers(self):
        source = ArtifactSource("task.command.plan-exec", "packages/task/commands/plan-exec.md", SOURCE_HASH_A)
        invalid_layers = (
            ({"id": "project", "order": 0, "provenance": {"path": "x"}},),
            ({"id": "project", "owner": "project", "order": True,
              "provenance": {"path": "x"}},),
            ({"id": "project", "owner": "project", "order": 0, "provenance": {}},),
            ({"id": "project", "owner": "project", "order": 0, "provenance": {"path": "x"}},
             {"id": "fleet", "owner": "fleet", "order": 0, "provenance": {"path": "y"}}),
            ({"id": "project", "owner": "project", "order": 0, "provenance": {"path": "x"}},
             {"id": "project-extra", "owner": "project", "order": 1, "provenance": {"path": "y"}}),
        )
        for layers in invalid_layers:
            with self.subTest(layers=layers):
                with self.assertRaises((TypeError, ValueError)):
                    _request(sources=(source,), override_layers=layers)

    def test_capability_requirements_contribute_to_the_source_envelope(self):
        source = ArtifactSource("task.command.plan-exec", "packages/task/commands/plan-exec.md", SOURCE_HASH_A)
        native = _request(sources=(source,))
        adapted_adapter = ArtifactAdapterIdentity(
            "task.codex-skill", "1.0.0", ProviderId.CODEX, "1.0.0",
            (CapabilityRequirement(CapabilityId("skills.repository"), (SupportLevel.ADAPTED,)),),
        )
        adapted = ArtifactRenderRequest(
            native.artifact_id, native.canonical_sources, native.target, adapted_adapter,
            native.override_layers, {"title": "Plan exec"}, native.renderer,
        )
        self.assertNotEqual(plan_artifact_render(native).provenance.source_hash,
                            plan_artifact_render(adapted).provenance.source_hash)

    def test_rejects_unsafe_or_noncanonical_target_paths(self):
        unsafe = ("", ".", "..", "/etc/passwd", "../outside", "a/../outside", "a//b", "a\\b")
        for path in unsafe:
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    validate_target_path(path)
        self.assertEqual(validate_target_path(".agents/skills/task/SKILL.md"),
                         ".agents/skills/task/SKILL.md")

    def test_rejects_invalid_boundary_and_renderer_output(self):
        with self.assertRaises(ValueError):
            ArtifactTarget("x", ("whole-file", ("unexpected",)))
        with self.assertRaises(ValueError):
            ArtifactTarget("x", ("managed-blocks", ()))
        request = _request(
            sources=(ArtifactSource("task.command.plan-exec", "packages/task/commands/plan-exec.md", SOURCE_HASH_A),),
            renderer=lambda _request: "text",  # type: ignore[return-value]
        )
        with self.assertRaises(TypeError):
            plan_artifact_render(request)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
