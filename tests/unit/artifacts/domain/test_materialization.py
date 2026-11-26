"""safe_material_name and plan_materialization (artifacts §4.4; vectors of materialization-security.json)."""

import unicodedata
from dataclasses import dataclass, replace
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.materialization import plan_materialization, safe_material_name

ID1 = UUID("0192f5ca-5001-7a01-8000-f8091a2b3c4e")
ID2 = UUID("0192f5ca-5002-7a01-8000-f8091a2b3c4e")
ID3 = UUID("0192f5ca-5003-7a01-8000-f8091a2b3c4e")
ID4 = UUID("0192f5ca-5004-7a01-8000-f8091a2b3c4e")
DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64


@dataclass(frozen=True, slots=True)
class View:
    file_version_id: UUID
    original_filename: str
    size_bytes: int
    digest: str | ContentDigest


def view(version_id: UUID = ID1, name: str = "a.txt", size: int = 3, digest: str = DIGEST_A) -> View:
    return View(version_id, name, size, digest)


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("CON.txt", "_CON.txt"),
        ("con", "_con"),
        ("Nul.tar.gz", "_Nul.tar.gz"),
        ("COM1.log", "_COM1.log"),
        ("lpt9", "_lpt9"),
        ("COM0.txt", "COM0.txt"),
        ("CONSOLE.txt", "CONSOLE.txt"),
        ("a.", "a"),
        ("a. . .", "a._._"),
        ("report...", "report"),
        ("", "content"),
        (".", "content"),
        ("..", "content"),
        ("...", "content"),
        ("../x", ".._x"),
        ("a/b", "a_b"),
        ("a\\b", "a_b"),
        ("nul\x00byte.txt", "nul_byte.txt"),
        ("my report (1).pdf", "my_report__1_.pdf"),
        ("résumé.pdf", "r_sum_.pdf"),
        ("A.txt", "A.txt"),
        (".bashrc", ".bashrc"),
        ("bundle.tar", "bundle.tar"),
        ("C:evil.txt", "C_evil.txt"),
    ],
)
def test_safe_material_name(original: str, expected: str) -> None:
    assert safe_material_name(original) == expected


def test_safe_material_name_is_the_same_for_nfc_and_nfd() -> None:
    nfc = unicodedata.normalize("NFC", "é.txt")
    nfd = unicodedata.normalize("NFD", "é.txt")
    assert nfc != nfd
    assert safe_material_name(nfc) == safe_material_name(nfd) == "_.txt"


def test_long_names_keep_a_short_extension() -> None:
    name = safe_material_name("x" * 300 + ".tar.gz")
    assert len(name.encode()) == 120
    assert name.endswith(".gz")
    assert safe_material_name("ж" * 200 + ".md") == "_" * 117 + ".md"


def test_a_long_extension_is_cut_to_16_bytes() -> None:
    name = safe_material_name("a." + "e" * 40)
    assert name == "a." + "e" * 15
    long_both = safe_material_name("s" * 200 + "." + "e" * 40)
    assert len(long_both) == 120
    assert long_both.endswith("." + "e" * 15)


def test_an_extensionless_long_name_is_cut_to_120_bytes() -> None:
    assert safe_material_name("y" * 500) == "y" * 120


@pytest.mark.parametrize("reserved", ["CON", "nul", "COM1", "lpt9"])
def test_a_long_reserved_name_keeps_its_prefix_within_120_bytes(reserved: str) -> None:
    name = safe_material_name(f"{reserved}.{'x' * 300}.txt")
    assert len(name.encode()) == 120
    assert name.startswith(f"_{reserved}.x")
    assert name.endswith("x.txt")
    assert safe_material_name(f"{reserved}.{'e' * 40}") == f"_{reserved}." + "e" * 15


@pytest.mark.parametrize(
    "original",
    [
        "CON.txt",
        "a.",
        "../../etc/passwd",
        "x\N{RIGHT-TO-LEFT OVERRIDE}gpj.exe",
        "\x00",
        "ab" * 200 + ".exe",
        "αβγ",
    ],
)
def test_safe_material_names_are_portable(original: str) -> None:
    name = safe_material_name(original)
    assert 1 <= len(name.encode()) <= 120
    assert name.isascii()
    assert all(c.isalnum() or c in "._-" for c in name)
    assert name not in {".", ".."}
    assert not name.endswith((".", " "))


def test_plan_uses_canonical_lowercase_version_directories() -> None:
    (entry,) = plan_materialization([view(name="CON.txt", size=7)])
    assert entry.relative_path == "0192f5ca-5001-7a01-8000-f8091a2b3c4e/_CON.txt"
    assert (entry.file_version_id, entry.size_bytes, entry.digest) == (ID1, 7, ContentDigest(DIGEST_A))


def test_a_string_id_is_canonicalized() -> None:
    upper = View(str(ID1).upper(), "a.txt", 3, DIGEST_A)  # type: ignore[arg-type]
    (entry,) = plan_materialization([upper])
    assert entry.relative_path.startswith(str(ID1) + "/")


def test_same_version_retry_is_one_entry() -> None:
    plan = plan_materialization([view(), view(), replace(view(), digest=ContentDigest(DIGEST_A))])
    assert len(plan) == 1


@pytest.mark.parametrize(
    "other", [view(digest=DIGEST_B), view(size=4), view(name="b.txt"), view(name="A.txt")]
)
def test_same_version_with_other_metadata_is_refused(other: View) -> None:
    with pytest.raises(ValidationFailed) as error:
        plan_materialization([view(), other])
    assert error.value.code is ErrorCode.INVALID_REFERENCE
    assert error.value.details == {"reason": "metadata_mismatch", "file_version_id": str(ID1)}


def test_distinct_case_and_unicode_names_stay_distinct() -> None:
    names = ["A.txt", "a.txt", unicodedata.normalize("NFC", "é.txt"), unicodedata.normalize("NFD", "é.txt")]
    plan = plan_materialization([view(i, n) for i, n in zip((ID1, ID2, ID3, ID4), names, strict=True)])
    paths = [entry.relative_path for entry in plan]
    assert [p.split("/")[0] for p in paths] == [str(i) for i in (ID1, ID2, ID3, ID4)]
    folded = {unicodedata.normalize(form, p).casefold() for p in paths for form in ("NFC", "NFD")}
    assert len({p.casefold() for p in paths}) == 4
    assert len(folded) == 4
    assert [e.file_version_id for e in plan] == [ID1, ID2, ID3, ID4]


def test_different_versions_with_the_same_bytes_and_name_are_physically_distinct() -> None:
    plan = plan_materialization([view(ID1), view(ID2)])
    assert len({entry.relative_path for entry in plan}) == 2


def test_an_archive_is_planned_as_one_ordinary_file() -> None:
    (entry,) = plan_materialization([view(name="bundle.tar", size=10240)])
    assert entry.relative_path.endswith("/bundle.tar")


@pytest.mark.parametrize(
    ("source", "reason"),
    [
        (View("not-a-uuid", "a.txt", 1, DIGEST_A), "malformed_version_id"),  # type: ignore[arg-type]
        (View(None, "a.txt", 1, DIGEST_A), "malformed_version_id"),  # type: ignore[arg-type]
        (view(digest="sha256:xyz"), "malformed_digest"),
        (view(digest="sha256:" + "A" * 64), "malformed_digest"),
        (View(ID1, "a.txt", 1, None), "malformed_digest"),  # type: ignore[arg-type]
        (view(size=-1), "malformed_size"),
        (View(ID1, "a.txt", True, DIGEST_A), "malformed_size"),
        (View(ID1, "a.txt", "3", DIGEST_A), "malformed_size"),  # type: ignore[arg-type]
        (view(name=""), "malformed_filename"),
        (View(ID1, None, 1, DIGEST_A), "malformed_filename"),  # type: ignore[arg-type]
    ],
)
def test_malformed_metadata_refuses_the_whole_plan(source: View, reason: str) -> None:
    with pytest.raises(ValidationFailed) as error:
        plan_materialization([view(ID2), source])
    assert error.value.code is ErrorCode.INVALID_REFERENCE
    assert error.value.details["reason"] == reason


def test_an_empty_plan_is_empty() -> None:
    assert plan_materialization([]) == ()
