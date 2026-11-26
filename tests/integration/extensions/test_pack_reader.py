"""Integration tests for ``FilesystemPackReader`` and ``safe_extract_to_payload`` (extensions §6, §7.1)."""

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from skm.adapters.resources.archive import safe_extract_to_payload
from skm.adapters.resources.pack_reader import FilesystemPackReader
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed


@pytest.mark.integration
def test_read_dir_valid_and_rejects_symlinks_and_limits(tmp_path: Path) -> None:
    pack_dir = tmp_path / "my-pack"
    (pack_dir / "prompts" / "shared").mkdir(parents=True)
    (pack_dir / "pack.toml").write_text('slug = "my-pack"\n', encoding="utf-8")
    (pack_dir / "prompts" / "shared" / "greeting.md").write_text("Hello\n", encoding="utf-8")

    reader = FilesystemPackReader()
    payload = reader.read_dir(str(pack_dir))
    assert payload.manifest_text == 'slug = "my-pack"\n'
    assert len(payload.files) == 1
    assert payload.files[0].path == "prompts/shared/greeting.md"
    assert payload.files[0].content == b"Hello\n"

    # File count limit
    small_reader = FilesystemPackReader(max_files=0)
    with pytest.raises(ValidationFailed) as exc_info:
        small_reader.read_dir(str(pack_dir))
    assert exc_info.value.details["reason"] == "too_many_files"

    # Symlink inside directory is rejected
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    (pack_dir / "prompts" / "shared" / "link.md").symlink_to(outside)
    with pytest.raises(ValidationFailed) as sym_err:
        reader.read_dir(str(pack_dir))
    assert sym_err.value.code is ErrorCode.SCHEMA_INVALID
    assert sym_err.value.details["reason"] == "unexpected_symlink"


@pytest.mark.integration
def test_read_dir_missing_or_without_manifest_raises_not_found(tmp_path: Path) -> None:
    reader = FilesystemPackReader()
    with pytest.raises(NotFound):
        reader.read_dir(str(tmp_path / "does-not-exist"))

    empty_dir = tmp_path / "no-manifest"
    empty_dir.mkdir()
    (empty_dir / "note.md").write_text("hi\n", encoding="utf-8")
    with pytest.raises(NotFound) as exc_info:
        reader.read_dir(str(empty_dir))
    assert exc_info.value.details["reason"] == "missing_pack_manifest"


@pytest.mark.integration
def test_safe_extract_tar_gz_and_zip_valid(tmp_path: Path) -> None:
    tar_path = tmp_path / "pack.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        for name, data in (
            ("pack.toml", b'slug = "tar-pack"\n'),
            ("prompts/shared/a.md", b"Alpha"),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

    payload_tar = safe_extract_to_payload(tar_path)
    assert payload_tar.manifest_text == 'slug = "tar-pack"\n'
    assert [(f.path, f.content) for f in payload_tar.files] == [("prompts/shared/a.md", b"Alpha")]

    tar_bytes = tar_path.read_bytes()
    assert safe_extract_to_payload(tar_bytes) == payload_tar
    assert safe_extract_to_payload(io.BytesIO(tar_bytes)) == payload_tar

    zip_path = tmp_path / "pack.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("pack.toml", b'slug = "zip-pack"\n')
        zf.writestr("prompts/shared/b.md", b"Beta")

    payload_zip = safe_extract_to_payload(zip_path)
    assert payload_zip.manifest_text == 'slug = "zip-pack"\n'
    assert [(f.path, f.content) for f in payload_zip.files] == [("prompts/shared/b.md", b"Beta")]

    zip_bytes = zip_path.read_bytes()
    assert safe_extract_to_payload(zip_bytes) == payload_zip
    assert safe_extract_to_payload(io.BytesIO(zip_bytes)) == payload_zip


@pytest.mark.integration
@pytest.mark.parametrize("bad_entry", ["../evil.md", "prompts/../../evil.md", "/etc/passwd", "a\\b.md"])
def test_safe_extract_rejects_zip_slip_and_bad_paths(tmp_path: Path, bad_entry: str) -> None:
    tar_path = tmp_path / "slip.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        for name, data in (("pack.toml", b'slug = "x"\n'), (bad_entry, b"evil")):
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))

    with pytest.raises(ValidationFailed) as exc_info:
        safe_extract_to_payload(tar_path)
    assert exc_info.value.details["reason"] == "path_invalid"

    zip_path = tmp_path / "slip.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("pack.toml", b'slug = "x"\n')
        zf.writestr(bad_entry, b"evil")

    with pytest.raises(ValidationFailed) as zip_exc:
        safe_extract_to_payload(zip_path)
    assert zip_exc.value.details["reason"] == "path_invalid"


@pytest.mark.integration
def test_safe_extract_rejects_tar_and_zip_symlinks_and_hardlinks(tmp_path: Path) -> None:
    tar_path = tmp_path / "symlink.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        info = tarfile.TarInfo("pack.toml")
        info.size = 10
        tf.addfile(info, io.BytesIO(b'slug="x"\n\n'))
        sym = tarfile.TarInfo("prompts/shared/link.md")
        sym.type = tarfile.SYMTYPE
        sym.linkname = "/etc/passwd"
        tf.addfile(sym)

    with pytest.raises(ValidationFailed) as exc_info:
        safe_extract_to_payload(tar_path)
    assert exc_info.value.details["reason"] == "unexpected_symlink"

    hardlink_tar = tmp_path / "hardlink.tar.gz"
    with tarfile.open(hardlink_tar, "w:gz") as tf:
        info = tarfile.TarInfo("pack.toml")
        info.size = 10
        tf.addfile(info, io.BytesIO(b'slug="x"\n\n'))
        lnk = tarfile.TarInfo("prompts/shared/hardlink.md")
        lnk.type = tarfile.LNKTYPE
        lnk.linkname = "pack.toml"
        tf.addfile(lnk)

    with pytest.raises(ValidationFailed) as hl_exc:
        safe_extract_to_payload(hardlink_tar)
    assert hl_exc.value.details["reason"] == "unexpected_symlink"

    zip_path = tmp_path / "symlink.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("pack.toml", b'slug = "x"\n')
        zinfo = zipfile.ZipInfo("prompts/shared/link.md")
        zinfo.external_attr = 0o120777 << 16  # S_IFLNK
        zf.writestr(zinfo, b"/etc/passwd")

    with pytest.raises(ValidationFailed) as zip_exc:
        safe_extract_to_payload(zip_path)
    assert zip_exc.value.details["reason"] == "unexpected_symlink"


@pytest.mark.integration
def test_safe_extract_enforces_streaming_byte_and_file_caps(tmp_path: Path) -> None:
    bomb_path = tmp_path / "bomb.zip"
    with zipfile.ZipFile(bomb_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pack.toml", b'slug = "bomb"\n')
        zf.writestr("prompts/shared/huge.md", b"0" * 200_000)

    with pytest.raises(ValidationFailed) as exc_info:
        safe_extract_to_payload(bomb_path, max_bytes=50_000)
    assert exc_info.value.details["reason"] == "archive_too_large"

    with pytest.raises(ValidationFailed) as files_exc:
        safe_extract_to_payload(bomb_path, max_files=0)
    assert files_exc.value.details["reason"] == "too_many_files"

    no_manifest_zip = tmp_path / "no_manifest.zip"
    with zipfile.ZipFile(no_manifest_zip, "w") as zf:
        zf.writestr("prompts/shared/a.md", b"hello")
    with pytest.raises(NotFound) as missing_exc:
        safe_extract_to_payload(no_manifest_zip)
    assert missing_exc.value.details["reason"] == "missing_pack_manifest"
