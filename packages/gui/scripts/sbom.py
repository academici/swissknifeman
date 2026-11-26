#!/usr/bin/env python3
"""CycloneDX 1.5 SBOM of the gui module (stdlib only; runs on the hub Python too).

Usage: sbom.py [--out FILE] [--root DIR]

Components, one per lock entry: ``requirements.lock`` (pypi, with sha256), ``frontend/package-lock.json`` (npm, with the
integrity hash), the Rust crates of ``desktop/src-tauri`` (from ``Cargo.lock`` when it exists; otherwise the
requirements of the member ``Cargo.toml`` files, marked ``skm:locked=false``) and, when a sidecar was built, the digest
of its tree. The output is deterministic: sorted, the serial number derives from the content, the only time is
``SOURCE_DATE_EPOCH`` (default 1970-01-01T00:00:00Z). Without ``--out`` the document goes to stdout.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

MODULE_ROOT = Path(__file__).resolve().parents[1]
INTEGRITY_ALGS = {"sha512": "SHA-512", "sha384": "SHA-384", "sha256": "SHA-256", "sha1": "SHA-1"}
EXIT_FAILURE = 1


class SbomError(Exception):
    pass


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise SbomError(f"SBOM_INPUT_UNREADABLE: {path}: {error.strerror}") from None


def pypi_components(lock: Path) -> List[Dict[str, Any]]:
    """``name==version --hash=sha256:<hex>`` lines (``#`` comments, ``\\`` continuations tolerated)."""
    found = []
    text = _read(lock).replace("\\\n", " ")
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        name, sep, version = parts[0].partition("==")
        if not sep or not name or not version:
            raise SbomError(f"SBOM_LOCK_INVALID: {lock}:{number}: expected name==version")
        hashes = [{"alg": "SHA-256", "content": part[len("--hash=sha256:"):]}
                  for part in parts[1:] if part.startswith("--hash=sha256:")]
        normal = re.sub(r"[-_.]+", "-", name).lower()
        component: Dict[str, Any] = {"type": "library", "bom-ref": f"pypi:{normal}=={version}", "name": name,
                                     "version": version, "purl": f"pkg:pypi/{normal}@{version}"}
        if hashes:
            component["hashes"] = hashes
        found.append(component)
    return found


def _integrity(value: Any) -> List[Dict[str, str]]:
    if not isinstance(value, str) or not value.strip():
        return []
    first = value.split()[0]
    algorithm, sep, encoded = first.partition("-")
    if not sep or algorithm not in INTEGRITY_ALGS:
        return []
    try:
        content = binascii.hexlify(base64.b64decode(encoded, validate=True)).decode("ascii")
    except (binascii.Error, ValueError):
        return []
    return [{"alg": INTEGRITY_ALGS[algorithm], "content": content}]


def npm_components(lock: Path) -> List[Dict[str, Any]]:
    try:
        document = json.loads(_read(lock))
    except ValueError as error:
        raise SbomError(f"SBOM_LOCK_INVALID: {lock}: {error}") from None
    packages = document.get("packages") if isinstance(document, dict) else None
    if not isinstance(packages, dict):
        raise SbomError(f"SBOM_LOCK_INVALID: {lock}: no packages object (lockfileVersion 2 or 3 is needed)")
    found = []
    for key in sorted(packages):
        if key == "":  # the root project itself
            continue
        entry = packages[key] if isinstance(packages[key], dict) else {}
        name = entry.get("name") or key.rpartition("node_modules/")[2]
        version = str(entry.get("version", ""))
        scoped = name.startswith("@")
        purl_name = "%40" + quote(name[1:], safe="/") if scoped else quote(name, safe="")
        component: Dict[str, Any] = {"type": "library", "bom-ref": f"npm:{key}", "name": name}
        if version:
            component["version"] = version
            component["purl"] = f"pkg:npm/{purl_name}@{version}"
        hashes = _integrity(entry.get("integrity"))
        if hashes:
            component["hashes"] = hashes
        if entry.get("dev"):
            component["scope"] = "optional"
        found.append(component)
    return found


_SECTION = re.compile(r"^\[+([^\]]+)\]+\s*$")
_DEP_SECTIONS = {"dependencies", "build-dependencies", "dev-dependencies", "workspace.dependencies"}


def _strip_comment(line: str) -> str:
    in_string = False
    for index, char in enumerate(line):
        if char == '"':
            in_string = not in_string
        elif char == "#" and not in_string:
            return line[:index]
    return line


def _cargo_requirements(manifest: Path) -> List[Tuple[str, str]]:
    """``(crate, version requirement)`` of a manifest; path-only dependencies are workspace members, not components."""
    found, section = [], ""
    for raw in _read(manifest).splitlines():
        line = _strip_comment(raw).strip()
        if not line:
            continue
        header = _SECTION.match(line)
        if header:
            section = header.group(1).strip()
            continue
        if section not in _DEP_SECTIONS:
            continue
        name, sep, value = line.partition("=")
        if not sep:
            continue
        name, value = name.strip(), value.strip()
        if value.startswith('"'):
            found.append((name, value.strip('"')))
            continue
        version = re.search(r'\bversion\s*=\s*"([^"]+)"', value)
        if version:
            found.append((name, version.group(1)))
    return found


def _cargo_members(workspace: Path) -> List[Path]:
    text = _read(workspace / "Cargo.toml")
    members = re.search(r"^members\s*=\s*\[([^\]]*)\]", text, re.MULTILINE)
    names = re.findall(r'"([^"]+)"', members.group(1)) if members else []
    return [workspace / name / "Cargo.toml" for name in names]


def cargo_components(workspace: Path) -> List[Dict[str, Any]]:
    lock = workspace / "Cargo.lock"
    found: List[Dict[str, Any]] = []
    if lock.is_file():
        packages = re.split(r"^\[\[package\]\]\s*$", _read(lock), flags=re.MULTILINE)[1:]
        for block in packages:
            fields = dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"', block, re.MULTILINE))
            if "source" not in fields:  # workspace member
                continue
            component: Dict[str, Any] = {"type": "library", "bom-ref": f"cargo:{fields['name']}@{fields['version']}",
                                         "name": fields["name"], "version": fields["version"],
                                         "purl": f"pkg:cargo/{fields['name']}@{fields['version']}",
                                         "properties": [{"name": "skm:locked", "value": "true"}]}
            if "checksum" in fields:
                component["hashes"] = [{"alg": "SHA-256", "content": fields["checksum"]}]
            found.append(component)
        return found
    seen = set()
    for manifest in _cargo_members(workspace):
        for name, requirement in _cargo_requirements(manifest):
            if (name, requirement) in seen:
                continue
            seen.add((name, requirement))
            found.append({"type": "library", "bom-ref": f"cargo:{name}@{requirement}", "name": name,
                          "version": requirement, "purl": f"pkg:cargo/{name}",
                          "properties": [{"name": "skm:locked", "value": "false"}]})
    return found


def sidecar_components(root: Path) -> List[Dict[str, Any]]:
    found = []
    for digest_file in sorted((root / "sidecar" / "dist").glob("gui-backend-*/gui-backend.digest")):
        try:
            tree = json.loads(_read(digest_file))["tree"]
        except (ValueError, KeyError, TypeError):
            raise SbomError(f"SBOM_LOCK_INVALID: {digest_file}: not a sidecar digest") from None
        triple = digest_file.parent.name[len("gui-backend-"):]
        found.append({"type": "file", "bom-ref": f"sidecar:{triple}", "name": f"gui-backend-{triple}",
                      "hashes": [{"alg": "SHA-256", "content": tree}]})
    return found


def _timestamp() -> str:
    epoch = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    seconds = int(epoch) if epoch.isdigit() else 0
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _module_version(root: Path) -> str:
    try:
        return str(json.loads(_read(root / "unit.json")).get("version", "0.0.0"))
    except ValueError:
        return "0.0.0"


def build(root: Path = MODULE_ROOT) -> Dict[str, Any]:
    root = Path(root)
    components = (pypi_components(root / "requirements.lock")
                  + npm_components(root / "frontend" / "package-lock.json")
                  + cargo_components(root / "desktop" / "src-tauri")
                  + sidecar_components(root))
    components.sort(key=lambda component: component["bom-ref"])
    refs = [component["bom-ref"] for component in components]
    if len(set(refs)) != len(refs):
        duplicate = next(ref for ref in refs if refs.count(ref) > 1)
        raise SbomError(f"SBOM_LOCK_INVALID: duplicate component {duplicate}")
    body = json.dumps(components, sort_keys=True, separators=(",", ":"))
    serial = uuid.uuid5(uuid.NAMESPACE_URL, "skm-gui-sbom:" + hashlib.sha256(body.encode("utf-8")).hexdigest())
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:{serial}",
        "version": 1,
        "metadata": {
            "timestamp": _timestamp(),
            "component": {"type": "application", "bom-ref": "gui", "name": "swissknifeman-gui",
                          "version": _module_version(root)},
        },
        "components": components,
    }


def render(document: Dict[str, Any]) -> str:
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="sbom.py", description="CycloneDX 1.5 SBOM of the gui module")
    parser.add_argument("--out", metavar="FILE", default=None, help="output file (default: stdout)")
    parser.add_argument("--root", metavar="DIR", default=str(MODULE_ROOT), help="module root (default: this module)")
    args = parser.parse_args(argv)
    try:
        text = render(build(Path(args.root)))
    except SbomError as error:
        print(str(error), file=sys.stderr)
        return EXIT_FAILURE
    if args.out is None:
        sys.stdout.write(text)
    else:
        with open(args.out, "w", encoding="utf-8") as handle:  # plain write: --out /dev/null must work
            handle.write(text)
    print(f"sbom: {len(json.loads(text)['components'])} component(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
