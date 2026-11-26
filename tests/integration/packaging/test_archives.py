"""Compare resource inventories and digests against the release inputs, including Vite's hidden files."""

import hashlib
import tarfile
import zipfile
from pathlib import Path

from integration.packaging.conftest import ROOT

# An sdist keeps the build input names so Hatchling can rebuild the wheel from it alone.
RESOURCES = {
    "src/skm/schemas": "skm/schemas",
    "src/skm/adapters/postgres/migrations/sql": "skm/adapters/postgres/migrations/sql",
    "src/skm/entrypoints/api/openapi.json": "skm/entrypoints/api/openapi.json",
    "resources": "skm/_resources",
    "deploy/compose.local.yaml": "skm/_deploy/compose.local.yaml",
    "web/dist": "skm/_web",
}


def _digest(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def _verify(contents: dict[str, bytes], *, wheel: bool) -> None:
    assert all({"tests", "working", "__pycache__"}.isdisjoint(Path(name).parts) for name in contents)
    for source, packaged in RESOURCES.items():
        prefix = packaged if wheel else source
        root = ROOT / source
        files = sorted(root.rglob("*")) if root.is_dir() else [root]
        expected = {
            str(Path(prefix) / path.relative_to(root)): _digest(path.read_bytes())
            for path in files
            if path.is_file() and "__pycache__" not in path.parts
        }
        assert expected
        assert {k: v for k, v in contents.items() if k == prefix or k.startswith(prefix + "/")} == expected


def test_release_inventory(distributions: Path) -> None:
    (wheel,) = distributions.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        contents = {item.filename: _digest(archive.read(item)) for item in archive.infolist()}
        assert len(contents) == len(archive.infolist())
        _verify(contents, wheel=True)
    (sdist,) = distributions.glob("*.tar.gz")
    with tarfile.open(sdist) as archive:
        contents = {}
        for member in archive:
            if member.isdir():
                continue
            name = member.name.split("/", 1)[1]
            assert member.isfile()
            assert name not in contents
            stream = archive.extractfile(member)
            assert stream is not None
            contents[name] = _digest(stream.read())
        _verify(contents, wheel=False)
