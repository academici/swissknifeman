"""The offline pack CLI produces payloads accepted by both installation readers."""

from __future__ import annotations

import hashlib
import io
import json
import shutil
import zipfile
from pathlib import Path
from typing import Never

import pytest

from contracts.extensions.harness import FakeEstimator
from skm.adapters.resources.builtin_packs import PackagedBuiltinPacks
from skm.adapters.resources.pack_reader import FilesystemPackReader
from skm.entrypoints.cli.main import main
from skm.kernel.errors import ValidationFailed
from skm.modules.extensions.application.candidate import build_candidate

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures/overlays/example"
ASSET = "prompts/shared/work_policy.md"


def _cli(*args: str) -> tuple[int, dict[str, object]]:
    stdout = io.StringIO()

    def backend(*_args: object) -> Never:
        pytest.fail("the pack CLI attached an instance backend")

    code = main(
        ["--json", "pack", "compile", *args],
        environ={},
        stdout=stdout,
        stderr=io.StringIO(),
        backend=backend,
    )
    return code, json.loads(stdout.getvalue())


@pytest.mark.integration
def test_cli_compile_and_check_keep_install_payloads_and_registry_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "resources/packs"
    first, second = root / "example", root / "alternate"
    shutil.copytree(FIXTURE, first)
    shutil.copytree(FIXTURE, second)
    manifest = second / "pack.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'slug = "example-overlay"', 'slug = "alternate-overlay"'
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    reader = FilesystemPackReader()
    before = reader.read_dir(str(first))
    builtins = PackagedBuiltinPacks(root)
    before_builtins = builtins.payloads()
    candidate = build_candidate(before, estimator=FakeEstimator(), scan=False)

    code, problem = _cli("--check")
    assert code == 1
    assert problem["ok"] is False
    assert not (root / "pack.lock.json").exists()
    code, response = _cli()
    assert code == 0
    assert response["command"] == "cli.pack.compile"
    assert isinstance(response["result"], dict)
    assert response["result"]["duplicate_copies"] == 1
    assert _cli("--check", "--path", str(root))[0] == 0

    assert not (first / ASSET).exists()
    assert not (second / ASSET).exists()
    assert reader.read_dir(str(first)) == before
    assert builtins.payloads() == before_builtins
    restored = build_candidate(reader.read_dir(str(first)), estimator=FakeEstimator(), scan=False)
    assert restored.digest == candidate.digest

    blob = root / ".pack-blobs" / hashlib.sha256((FIXTURE / ASSET).read_bytes()).hexdigest()
    blob.write_bytes(b"tampered bytes")
    assert _cli("--check")[0] == 1
    with pytest.raises(ValidationFailed, match="SHA-256 mismatch"):
        reader.read_dir(str(first))
    with pytest.raises(ValidationFailed, match="SHA-256 mismatch"):
        builtins.payloads()


@pytest.mark.integration
def test_cli_compiles_a_standalone_pack(tmp_path: Path) -> None:
    pack = tmp_path / "standalone"
    shutil.copytree(FIXTURE, pack)
    shutil.copyfile(pack / ASSET, pack / "prompts/shared/duplicate.md")
    reader = FilesystemPackReader()
    expected = reader.read_dir(str(pack))
    assert _cli("--path", str(pack))[0] == 0
    assert _cli("--path", str(pack), "--check")[0] == 0
    assert reader.read_dir(str(pack)) == expected
    assert PackagedBuiltinPacks(tmp_path).payloads() == (expected,)
    archive = tmp_path / "standalone.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        for path in pack.rglob("*"):
            if path.is_file():
                zipped.write(path, path.relative_to(pack))
    assert reader.read_archive(str(archive)) == expected
