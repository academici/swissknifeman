from unittest import TestCase

from aicore.provider.skill_adapter import SkillAdapterDescriptor, SkillAdapterRegistry, SkillCoreRef


def descriptor(provider_id="codex"):
    return SkillAdapterDescriptor(
        "1.0.0", f"fixture.{provider_id}", "1.0.0", provider_id,
        SkillCoreRef("quality/code-review", ("skills.review", "skills.measure")),
        ("skills.review",), ("skills.measure",), (f"{provider_id}.native-ui",),
        {"unit": "skill", "budget_unit": "tokens", "degradation": "on-demand"},
        {"id": f"{provider_id}.renderer", "version": "1", "target_roots": (".agents/skills",)},
        {"mode": "explicit", "unsupported": False},
        {"unit": "tokens", "method": "probe", "bounds": {"max": 10}, "version": "1"},
        {"fixture_set": "fixture", "unavailable": False}, f"{provider_id}.status")


class SkillAdapterTests(TestCase):
    def test_third_provider_registers_without_existing_adapter_edits(self):
        registry = SkillAdapterRegistry((descriptor("claude-code"), descriptor("codex"), descriptor("third-provider")))
        self.assertEqual(registry.select(provider_id="third-provider", skill_id="quality/code-review").provider_id,
                         "third-provider")

    def test_adapter_cannot_replace_semantic_core(self):
        values = list(descriptor().__dict__.values())
        values[9] = {"id": "codex.renderer", "version": "1", "target_roots": (".agents/skills",),
                      "semantic_copy": "forbidden"}
        with self.assertRaisesRegex(ValueError, "ADAPTER_SEMANTIC_REPLACEMENT"):
            SkillAdapterDescriptor(*values)

    def test_provider_scoped_status_and_extension_are_required(self):
        values = list(descriptor().__dict__.values())
        values[-1] = "shared.status"
        with self.assertRaisesRegex(ValueError, "provider-scoped"):
            SkillAdapterDescriptor(*values)
