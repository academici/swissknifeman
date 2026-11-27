"""check_skills fails closed on empty roles, a bad SKILL.md, a bad scan root, and incompatible requires."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from skm.adapters.resources.pack_compiler import compile_packs

check_skills = importlib.import_module("tools.check_skills")

_SKILL = """---
name: {key}
description: "A fixture skill."
---

Body.
"""


def _pack(root: Path, key: str, manifest: str, *, skill: bool = True) -> None:
    skill_dir = root / "demo" / "skills" / key
    skill_dir.mkdir(parents=True)
    (skill_dir / "manifest.toml").write_text(manifest, encoding="utf-8")
    if skill:
        (skill_dir / "SKILL.md").write_text(_SKILL.format(key=key), encoding="utf-8")


def test_repository_packs_are_clean() -> None:
    errors, warnings = check_skills.check_skills()
    assert errors == []
    # Reviewer audits name authoring skills they must not expand into.
    assert any("requirement-critic" in warning and "brd" in warning for warning in warnings)
    assert check_skills.main([]) == 0


def test_compiled_skill_manifest_and_body_are_checked(tmp_path: Path) -> None:
    _pack(tmp_path, "alpha", 'key = "alpha"\nroles = ["executor"]\n')
    pack = tmp_path / "demo"
    (pack / "pack.toml").write_text('slug = "demo"\n', encoding="utf-8")
    skill = pack / "skills/alpha"
    for name in ("manifest.toml", "SKILL.md"):
        (skill / f"copy-{name}").write_bytes((skill / name).read_bytes())
    compile_packs(tmp_path)
    assert not (skill / "manifest.toml").exists()
    assert not (skill / "SKILL.md").exists()
    assert check_skills.check_skills(tmp_path) == ([], [])


def test_empty_roles_and_unknown_role_fail(tmp_path: Path) -> None:
    _pack(
        tmp_path,
        "alpha",
        'key = "alpha"\nversion = "1.0.0"\nroles = []\n',
    )
    _pack(
        tmp_path,
        "beta",
        'key = "beta"\nversion = "1.0.0"\nroles = ["security"]\n',
    )
    errors, _warnings = check_skills.check_skills(tmp_path)
    assert any("roles must be a non-empty list" in error for error in errors)
    assert any("outside the 7-role enum" in error for error in errors)
    assert check_skills.main(["--root", str(tmp_path)]) == 1


def test_malformed_skill_frontmatter_is_a_diagnostic(tmp_path: Path) -> None:
    _pack(
        tmp_path,
        "alpha",
        'key = "alpha"\nversion = "1.0.0"\nroles = ["executor"]\n',
        skill=False,
    )
    skill_md = tmp_path / "demo" / "skills" / "alpha" / "SKILL.md"
    skill_md.write_text("---\nname: alpha\ndescription: broken\n", encoding="utf-8")
    errors, warnings = check_skills.check_skills(tmp_path)
    assert warnings == []
    assert errors == [
        "demo/skills/alpha/manifest.toml: SKILL.md is invalid: "
        "SCHEMA_INVALID: pack is invalid: front_matter_unterminated"
    ]
    assert check_skills.main(["--root", str(tmp_path)]) == 1


@pytest.mark.parametrize("kind", ["missing", "file"])
def test_scan_root_must_be_a_directory(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "scan-root"
    if kind == "file":
        root.write_text("not a directory", encoding="utf-8")
    errors, warnings = check_skills.check_skills(root)
    reason = "does not exist" if kind == "missing" else "is not a directory"
    assert warnings == []
    assert errors == [f"scan root {reason}: {root}"]
    assert check_skills.main(["--root", str(root)]) == 1


def test_missing_skill_markdown_fails(tmp_path: Path) -> None:
    _pack(
        tmp_path,
        "alpha",
        'key = "alpha"\nversion = "1.0.0"\nroles = ["executor"]\n',
        skill=False,
    )
    errors, warnings = check_skills.check_skills(tmp_path)
    assert warnings == []
    assert errors == ["demo/skills/alpha/manifest.toml: SKILL.md is missing"]


def test_requires_must_share_a_parent_role(tmp_path: Path) -> None:
    _pack(tmp_path, "parent", 'key = "parent"\nroles = ["reviewer"]\nrequires = ["child"]\n')
    _pack(tmp_path, "child", 'key = "child"\nroles = ["executor"]\n')
    _pack(tmp_path, "other", 'key = "other"\nroles = ["advisor"]\nrequires = ["missing"]\n')
    errors, warnings = check_skills.check_skills(tmp_path)
    assert any("share none of" in warning and "parent" in warning for warning in warnings)
    assert any("requires unknown skill missing" in error for error in errors)


def test_shared_role_requires_pass(tmp_path: Path) -> None:
    _pack(
        tmp_path,
        "parent",
        'key = "parent"\nroles = ["executor", "reviewer"]\nrequires = ["child"]\n',
    )
    _pack(tmp_path, "child", 'key = "child"\nroles = ["reviewer"]\n')
    assert check_skills.check_skills(tmp_path) == ([], [])


@pytest.mark.parametrize("role", sorted(check_skills.ROLE_NAMES))
def test_each_enum_role_is_accepted(tmp_path: Path, role: str) -> None:
    _pack(tmp_path, "alpha", f'key = "alpha"\nroles = ["{role}"]\n')
    assert check_skills.check_skills(tmp_path) == ([], [])
