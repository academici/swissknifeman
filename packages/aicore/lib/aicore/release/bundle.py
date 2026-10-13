"""The release bundle of a hub: compat manifest, schema package, attestation and checksums.

``aicore release bundle --root HUB --tag TAG --out DIR`` writes four files to ``DIR`` and nothing anywhere else:

* ``compat.json`` - ``compat-manifest/v1`` read from the ``unit.json`` of every module and bridge;
* ``schemas-<tag>.tar.gz`` - every file under ``packages/*/schemas`` and ``bridges/*/schemas`` with an ``index.json``;
  the bytes depend only on the content (sorted paths, zero times and owners), so two runs are identical;
* ``release-attestation.json`` - :func:`aicore.release.attestation.build` at ``HEAD``; the tag is only a label;
* ``SHA256SUMS`` - ``sha256sum`` format over the other files.

``DIR`` must be absent or empty (``OUT_NOT_EMPTY``, exit 2). stdlib and aicore only.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, TextIO

from ..util import schema as _schema
from ..util.io import atomic_write_text
from . import attestation

COMPAT_FILE = "compat.json"
ATTESTATION_FILE = "release-attestation.json"
SUMS_FILE = "SHA256SUMS"
COMPAT_SCHEMA = "urn:swissknifeman:aicore:compat-manifest:v1"
_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas" / "compat-manifest" / "v1"
_TAG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")
_SKIP_PARTS = {"__pycache__", ".git", "node_modules"}


class BundleError(ValueError):
    """A refusal with a stable code; ``str()`` is ``<CODE>: <message>``; ``usage`` marks exit 2."""

    def __init__(self, code: str, message: str, usage: bool = False):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.usage = usage


def dumps(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _unit_files(root: Path, folder: str) -> List[Path]:
    base = root / folder
    return sorted(path / "unit.json" for path in base.iterdir() if (path / "unit.json").is_file()) \
        if base.is_dir() else []


def _unit_entry(root: Path, path: Path, doc: Mapping[str, Any]) -> Dict[str, Any]:
    module = path.parent.relative_to(root).as_posix()
    contracts = [{"id": item["id"], "version": item["version"], "stability": item["stability"],
                  "path": f"{module}/{item['path']}"}
                 for item in doc.get("provides", {}).get("contracts", [])]
    requires = [{"unit": item["unit"], "range": item["range"]} for item in doc.get("requires", [])]
    return {"id": doc["id"], "kind": doc["kind"], "version": doc["version"], "stability": doc["stability"],
            "destination": doc["destination"], "requires": requires, "contracts": contracts}


def compat_manifest(root: Path, umbrella_version: str, tag: str) -> Dict[str, Any]:
    """``compat-manifest/v1`` from the unit.json of ``packages/*`` and ``bridges/*``, each list sorted by id."""
    units: List[Dict[str, Any]] = []
    bridges: List[Dict[str, Any]] = []
    for folder in ("packages", "bridges"):
        for path in _unit_files(root, folder):
            try:
                doc = json.loads(path.read_text(encoding="utf-8"))
                entry = _unit_entry(root, path, doc)
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise BundleError("BUNDLE_UNIT_INVALID", f"{path.relative_to(root).as_posix()}: {exc!r}") from exc
            (bridges if entry["kind"] == "bridge" else units).append(entry)
    manifest = {"schema": COMPAT_SCHEMA, "umbrella": {"version": umbrella_version, "tag": tag},
                "units": sorted(units, key=lambda item: item["id"]),
                "bridges": sorted(bridges, key=lambda item: item["id"])}
    registry, kind = _schema.load_contract(_SCHEMA_DIR)
    issues = _schema.validate(manifest, kind, registry)
    if issues:
        raise BundleError("BUNDLE_COMPAT_INVALID", "; ".join(str(issue) for issue in issues[:5]))
    return manifest


def schema_files(root: Path) -> Dict[str, bytes]:
    """Hub-relative path -> bytes of every regular file under ``packages/*/schemas`` and ``bridges/*/schemas``."""
    found: Dict[str, bytes] = {}
    for folder in ("packages", "bridges"):
        base = root / folder
        if not base.is_dir():
            continue
        for schemas in sorted(base.glob("*/schemas")):
            for path in sorted(schemas.rglob("*")):
                if path.is_symlink() or not path.is_file():
                    continue
                if _SKIP_PARTS & set(path.relative_to(schemas).parts) or path.suffix == ".pyc":
                    continue
                found[path.relative_to(root).as_posix()] = path.read_bytes()
    return found


def schema_index(files: Mapping[str, bytes]) -> List[Dict[str, str]]:
    """One entry per ``*.schema.json``: ``$id`` (else the path), the ``v<N>`` directory, path and sha256."""
    index = []
    for path, data in sorted(files.items()):
        if not path.endswith(".schema.json"):
            continue
        try:
            identifier = json.loads(data).get("$id")
        except (ValueError, AttributeError):
            identifier = None
        version = next((part for part in reversed(path.split("/")) if re.fullmatch(r"v[0-9]+", part)), "")
        index.append({"id": identifier if isinstance(identifier, str) else path, "version": version,
                      "path": path, "sha256": hashlib.sha256(data).hexdigest()})
    return index


def schemas_archive(files: Mapping[str, bytes]) -> bytes:
    """Deterministic ``tar.gz``: ``index.json`` first, then the files by path; times, owners and gzip name zero."""
    members = {"index.json": dumps({"schemas": schema_index(files)})}
    members.update(files)
    raw = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as stream:
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.GNU_FORMAT) as tar:
            for name in ["index.json"] + sorted(files):
                info = tarfile.TarInfo(name)
                info.size = len(members[name])
                info.mtime = 0
                info.mode = 0o644
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                tar.addfile(info, io.BytesIO(members[name]))
    return raw.getvalue()


def checksums(files: Mapping[str, bytes]) -> bytes:
    lines = [f"{hashlib.sha256(files[name]).hexdigest()}  {name}\n" for name in sorted(files)]
    return "".join(lines).encode("utf-8")


def _package_root(root: Path) -> Optional[Path]:
    """The module that owns ``configs/publication-versions.json`` (the attestation reads versions there); one or none."""
    owners = sorted((root / "packages").glob("*/configs/publication-versions.json"))
    return owners[0].parent.parent if len(owners) == 1 else None


def build_bundle(root: Path, tag: str) -> Dict[str, bytes]:
    """File name -> bytes of the whole bundle, nothing written; the attestation is taken at ``HEAD``."""
    if not _TAG.match(tag):
        raise BundleError("TAG_INVALID", f"{tag!r}: use letters, digits and . _ + - only", usage=True)
    try:
        attested = attestation.build(root, ref="HEAD", package_root=_package_root(root))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        raise BundleError("BUNDLE_ATTESTATION", f"{exc}") from exc
    files = {
        COMPAT_FILE: dumps(compat_manifest(root, attested["umbrella"]["version"], tag)),
        f"schemas-{tag}.tar.gz": schemas_archive(schema_files(root)),
        ATTESTATION_FILE: dumps(attested),
    }
    files[SUMS_FILE] = checksums(files)
    return files


def write_bundle(files: Mapping[str, bytes], out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        if name.endswith(".tar.gz"):
            (out / name).write_bytes(data)
        else:
            atomic_write_text(out / name, data.decode("utf-8"))


def _check_out(out: Path) -> None:
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise BundleError("OUT_NOT_EMPTY", f"{out} must be absent or an empty directory", usage=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aicore release", description="Release tools of a hub.")
    commands = parser.add_subparsers(dest="command", required=True)
    bundle = commands.add_parser("bundle", help="write compat.json, the schema package, the attestation and SHA256SUMS")
    bundle.add_argument("--root", required=True, help="hub root (a git repository)")
    bundle.add_argument("--tag", required=True, help="release label used in names and compat.json")
    bundle.add_argument("--out", required=True, help="output directory: absent or empty")
    return parser


def main(argv: Sequence[str], *, env: Optional[Mapping[str, str]] = None, cwd: Optional[Path] = None,
         out: Optional[TextIO] = None, err: Optional[TextIO] = None) -> int:
    """``aicore release bundle``: exit 0 done, 1 refusal, 2 usage (including ``OUT_NOT_EMPTY``)."""
    out, err = out or sys.stdout, err or sys.stderr
    try:
        args = build_parser().parse_args(list(argv))
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    def resolve(value: str) -> Path:
        path = Path(value)
        return (Path(cwd) / path if not path.is_absolute() and cwd is not None else path).resolve()

    root, target = resolve(args.root), resolve(args.out)
    try:
        _check_out(target)
        files = build_bundle(root, args.tag)
        write_bundle(files, target)
    except BundleError as exc:
        err.write(f"aicore release bundle: {exc}\n")
        return 2 if exc.usage else 1
    for name in sorted(files):
        out.write(f"wrote {name}\n")
    return 0
