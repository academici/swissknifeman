"""Unit tests for ``skm.modules.extensions.domain.digest_rules`` (extensions §4.14)."""

import hashlib

from skm.modules.extensions.domain.digest_rules import (
    file_digest,
    is_excluded,
    pack_digest,
    resource_digest,
)


def test_file_digest_matches_sha256() -> None:
    data = b"hello world\n"
    assert file_digest(data) == f"sha256:{hashlib.sha256(data).hexdigest()}"


def test_is_excluded_rules() -> None:
    assert is_excluded("__pycache__/mod.cpython-312.pyc")
    assert is_excluded("references/__pycache__/helper.py")
    assert is_excluded("helper.pyc")
    assert is_excluded(".DS_Store")
    assert is_excluded("references/.DS_Store")
    assert is_excluded("SKILL.ru.md")
    assert is_excluded("SKILL.backup.md")
    assert not is_excluded("SKILL.md")
    assert not is_excluded("manifest.toml")
    assert not is_excluded("references/guide.md")


def test_resource_digest_order_independent_and_ignores_excluded_files() -> None:
    files_a = {
        "SKILL.md": b"# Review Skill\n",
        "manifest.toml": b'key = "review"\n',
    }
    files_b = {
        "manifest.toml": b'key = "review"\n',
        "SKILL.md": b"# Review Skill\n",
        "__pycache__/foo.pyc": b"\x00\x01\x02",
        "SKILL.draft.md": b"draft",
        ".DS_Store": b"junk",
    }
    digest_a = resource_digest(files_a)
    digest_b = resource_digest(files_b)
    assert digest_a == digest_b

    expected = hashlib.sha256()
    expected.update(b"SKILL.md\0# Review Skill\n")
    expected.update(b'manifest.toml\0key = "review"\n')
    assert digest_a == f"sha256:{expected.hexdigest()}"


def test_pack_digest_canonical_and_resource_order_independent() -> None:
    manifest_1 = {"slug": "demo", "version": "1.0.0", "config": {"threshold": 0.5}}
    manifest_2 = {"config": {"threshold": 0.5}, "version": "1.0.0", "slug": "demo"}
    r1 = ("skill", "alpha", "1.0.0", "sha256:" + "1" * 64)
    r2 = ("steering", "beta", "1.0.0", "sha256:" + "2" * 64)

    d1 = pack_digest(manifest_1, [r2, r1])
    d2 = pack_digest(manifest_2, [r1, r2])
    assert d1 == d2
    assert d1.startswith("sha256:")


def test_resource_digest_sensitive_to_file_rename_and_matches_legacy_vector() -> None:
    assert resource_digest({"a.md": b"x"}) != resource_digest({"b.md": b"x"})

    # Legacy skill_content_hash compatibility vector (sorted POSIX path + NUL + content)
    legacy_skill_files = {
        "SKILL.md": b"---\nname: sample\ndescription: Sample skill\n---\n# Sample\n",
        "references/checklist.md": b"- item 1\n- item 2\n",
    }
    assert (
        resource_digest(legacy_skill_files)
        == "sha256:d84372bd71aab3970122cad2b8511907924928c0dbf2f878dfcfbae9bacbd1e0"
    )
