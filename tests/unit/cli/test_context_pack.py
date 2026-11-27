"""Pack checkout context through the backend-free CLI and bounded checkout reader."""

import json
import os
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from skm.entrypoints.cli.main import main


def _invoke(root: Path, *args: str) -> tuple[int, dict[str, Any]]:
    def backend(*_: object) -> Any:
        pytest.fail("context pack must never attach a backend")

    out, err = StringIO(), StringIO()
    code = main(
        ("--json", "context", "pack", "--checkout-root", str(root), *args),
        stdout=out,
        stderr=err,
        environ={},
        backend=backend,
    )
    assert out.getvalue(), err.getvalue()
    return code, json.loads(out.getvalue())["result"]


def test_pack_rejects_symlink_escape_and_keeps_inside_files(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_text("allowed text", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside bytes", encoding="utf-8")
    (root / "escape").symlink_to(outside)
    (root / "directory-escape").symlink_to(tmp_path, target_is_directory=True)
    code, result = _invoke(root, "file.txt", "escape", "directory-escape/outside.txt", "../outside.txt")
    assert code == 1
    assert [(item["path"], item["content"]) for item in result["files"]] == [("file.txt", "allowed text")]
    assert {item["path"] for item in result["skipped"]} == {
        "escape",
        "directory-escape/outside.txt",
        "../outside.txt",
    }
    assert "outside bytes" not in json.dumps(result)


def test_pack_skips_binary_and_sensitive_files(tmp_path: Path) -> None:
    for name in (".env", ".env.production", "service.key", "certificate.PEM", "id_rsa_backup"):
        (tmp_path / name).write_text("must stay local", encoding="utf-8")
    (tmp_path / "image.bin").write_bytes(b"\0binary\xff")
    (tmp_path / "notes.txt").write_text("ordinary contents", encoding="utf-8")
    code, result = _invoke(tmp_path)
    assert code == 0
    assert [item["path"] for item in result["files"]] == ["notes.txt"]
    skipped = {item["path"]: item["reason"] for item in result["skipped"]}
    assert skipped == {
        ".env": "sensitive",
        ".env.production": "sensitive",
        "service.key": "sensitive",
        "certificate.PEM": "sensitive",
        "id_rsa_backup": "sensitive",
        "image.bin": "binary",
    }
    assert "must stay local" not in json.dumps(result)


def test_pack_checks_stat_before_reading(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    oversized = tmp_path / "oversized.txt"
    with oversized.open("wb") as stream:
        stream.truncate(512_000)
    (tmp_path / "small.txt").write_text("short", encoding="utf-8")
    identity = oversized.stat().st_ino
    real_fdopen = os.fdopen

    def checked_open(fd: int, *args: Any, **kwargs: Any) -> Any:
        stream = real_fdopen(fd, *args, **kwargs)
        if os.fstat(fd).st_ino == identity:

            def unexpected_read(*_: Any) -> Any:
                pytest.fail("oversized file was read")

            monkeypatch.setattr(stream, "read", unexpected_read)
        return stream

    monkeypatch.setattr("skm.adapters.git.host_inputs.os.fdopen", checked_open)
    code, result = _invoke(tmp_path, "--max-bytes", "8", "oversized.txt", "small.txt")
    assert code == 0
    assert result["skipped"] == [{"path": "oversized.txt", "reason": "too_large"}]
    assert result["bytes"] == 5
    assert [item["path"] for item in result["files"]] == ["small.txt"]


def test_pack_signatures_only(tmp_path: Path) -> None:
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "api.py").write_text(
        "HIDDEN = 'implementation only'\n\n"
        "class API:\n    def method(self, name: str) -> bool:\n        return True\n\n"
        "async def fetch(path: str = '/') -> str:\n    return 'private implementation'\n",
        encoding="utf-8",
    )
    (lib / "notes.txt").write_text("text is not a Python signature", encoding="utf-8")
    code, result = _invoke(tmp_path, "--signatures-only", "lib")
    assert code == 0
    (file,) = result["files"]
    assert file["path"] == "lib/api.py"
    assert "class API:" in file["content"]
    assert "def method(self, name: str) -> bool:" in file["content"]
    assert "async def fetch(path: str=" in file["content"]
    assert "return" not in file["content"]
    assert "implementation" not in file["content"]
