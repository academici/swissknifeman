"""Contracts of the source skills shipped with the core pack."""

import tomllib
from pathlib import Path

from skm.modules.extensions.domain.kinds import KIND_SPECS, ResourceKind, validate_layout

PACKS_ROOT = Path(__file__).resolve().parents[3] / "resources" / "packs"
CORE_ROOT = PACKS_ROOT / "core"
USER_ONLY = {"grill-me", "handoff", "implement", "to-spec", "to-tickets"}
OPTIONALLY_INVOKED = {"diagnosing-bugs", "tdd"}
EXPECTED_SKILLS = (
    USER_ONLY
    | OPTIONALLY_INVOKED
    | {
        "research-method",
        "review-checklist",
        "security-review",
        "spec-review",
    }
)


def test_core_skill_pack_layout_and_invocation() -> None:
    pack = tomllib.loads((CORE_ROOT / "pack.toml").read_text(encoding="utf-8"))
    assert (pack["slug"], pack["version"]) == ("core", "2.1.0")
    assert {(item["kind"], item["key"]) for item in pack["overrides"]} == {
        ("skill", "diagnosing-bugs"),
        ("skill", "implement"),
    }

    skill_dirs = {path.name: path for path in (CORE_ROOT / "skills").iterdir() if path.is_dir()}
    assert skill_dirs.keys() == EXPECTED_SKILLS
    assert len(skill_dirs) == 11
    for key, directory in skill_dirs.items():
        files = {
            path.relative_to(directory).as_posix(): path.read_bytes()
            for path in directory.rglob("*")
            if path.is_file()
        }
        assert validate_layout(KIND_SPECS[ResourceKind.SKILL], files) == (), key
        manifest = tomllib.loads(files["manifest.toml"].decode("utf-8"))
        assert manifest["key"] == key
        markdown = files["SKILL.md"].decode("utf-8")
        assert len(markdown.splitlines()) < 500, key
        if key in USER_ONLY | OPTIONALLY_INVOKED:
            assert manifest["invocation"]["user_only"] is (key in USER_ONLY), key
            assert manifest["version"] == "2.1.0"
        if key == "spec-review":
            assert manifest["version"] == "2.1.0"
            assert manifest["exclusive_group"] == "review-method"
            assert len(markdown.splitlines()) < 120
            assert {"## Standards", "## Spec"} <= set(markdown.splitlines())


def test_builtin_skill_edges_resolve() -> None:
    manifests = [
        tomllib.loads(path.read_text(encoding="utf-8"))
        for path in PACKS_ROOT.glob("**/skills/*/manifest.toml")
    ]
    keys = {manifest["key"] for manifest in manifests}
    assert "code-review" not in keys
    for manifest in manifests:
        for field in ("requires", "conflicts_with"):
            missing = set(manifest.get(field, ())) - keys
            assert not missing, (manifest["key"], field, missing)
