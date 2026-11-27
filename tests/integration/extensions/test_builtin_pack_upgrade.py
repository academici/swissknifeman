"""The P03 built-in pack upgrade preserves access to old pinned skill revisions."""

from pathlib import Path
from typing import Final

import pytest

import skm
from contracts.extensions.harness import build_world, pack_payload
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.kernel.ids import ResourceVersionId
from skm.modules.extensions import public
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.domain.payload import PackPayload
from skm.modules.extensions.generated.commands import SyncBuiltinPacks
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef

_PACKS_ROOT = Path(__file__).resolve().parents[3] / "resources" / "packs"
_GENERAL = "migrated-upstream-general"
_QUALITY = "migrated-upstream-quality-security"
_LEGACY: Final = {
    "core": ("2.0.8", "code-review", "2.0.0", "reviewer"),
    _GENERAL: ("1.0.1", "implement", "0.1.0", "executor"),
    _QUALITY: ("1.0.1", "diagnosing-bugs", "0.2.0", "scout"),
}


def _legacy_payloads() -> tuple[PackPayload, ...]:
    """Recreate the 0.1.0 ownership and versions for the three skills changed by P03."""
    return tuple(
        pack_payload(
            slug,
            pack_version,
            trust="builtin" if slug == "core" else "third_party",
            priority=0 if slug == "core" else -100,
            files={
                f"skills/{key}/manifest.toml": (
                    'schema = "urn:skm:extensions:skill-manifest:v1"\n'
                    f'key = "{key}"\nversion = "{version}"\nroles = ["{role}"]\n'
                ),
                f"skills/{key}/SKILL.md": (
                    f"---\nname: {key}\ndescription: Legacy {key} skill\n---\n# Legacy {key}\n"
                ),
            },
        )
        for slug, (pack_version, key, version, role) in _LEGACY.items()
    )


@pytest.mark.integration
def test_builtin_pack_upgrade_reopens_pinned_skill_revisions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(skm, "__version__", "0.1.0")
    world = build_world(*_legacy_payloads())
    initial = world.run(SyncBuiltinPacks())
    assert {(item.slug, item.version) for item in initial.installed} == {
        (slug, entry[0]) for slug, entry in _LEGACY.items()
    }
    world.run(
        SetValue(
            scope=SetValueDefsScopeRef(level="workspace", scope_id=world.workspace_id),
            key="extensions.packs.enabled",
            value=[_GENERAL, _QUALITY],
        )
    )
    with world.uow() as uow:
        config = world.config(uow)
        pins = public.pinned_pack_versions(uow, config=config)
        old_skills = {}
        for slug, (_, key, version, _) in _LEGACY.items():
            skill = public.resolve_resource(uow, ResourceKind.SKILL, key, config=config)
            assert (skill.pack_version_id, skill.version) == (pins[slug], version)
            old_skills[key] = public.get_resource_version(
                uow, ResourceVersionId(skill.resource_version_id), include_bodies=True
            )

    monkeypatch.setattr(skm, "__version__", "0.2.0")
    world.builtin.current = PackagedBuiltinPacks(_PACKS_ROOT).payloads()
    upgraded = world.run(SyncBuiltinPacks())
    installed = {(item.slug, item.version) for item in upgraded.installed}
    assert {("core", "2.1.0"), (_GENERAL, "1.1.0"), (_QUALITY, "1.1.0")} <= installed

    replay = world.run(SyncBuiltinPacks())
    assert replay.installed == ()
    assert {(item.slug, item.version) for item in replay.already_installed} == installed

    with world.uow() as uow:
        config = world.config(uow)
        current_pins = public.pinned_pack_versions(uow, config=config)
        assert {slug for slug in pins if pins[slug] != current_pins[slug]} == _LEGACY.keys()
        for key in ("implement", "diagnosing-bugs", "spec-review"):
            current = public.resolve_resource(uow, ResourceKind.SKILL, key, config=config)
            assert (current.pack_version_id, current.version) == (current_pins["core"], "2.1.0")
        assert "code-review" not in public.known_keys(uow, ResourceKind.SKILL, config=config)

        for key, before in old_skills.items():
            pinned = public.resolve_resource(uow, ResourceKind.SKILL, key, config=config, pins=pins)
            assert pinned.resource_version_id == before.resource_version_id
            reopened = public.get_resource_version(
                uow, ResourceVersionId(pinned.resource_version_id), include_bodies=True
            )
            assert reopened == before
            assert reopened.bodies is not None
            assert f"# Legacy {key}" in reopened.bodies["SKILL.md"]
