#!/usr/bin/env python3
"""Checks tauri.conf.json for the release (D9, D26). Reads only the configuration; runs no toolchain.

Usage: check-release-config.py [--release] [--conf PATH]
  default:   structure only (bundle targets, updater artifacts, sidecar, updater plugin keys); placeholders are allowed.
  --release: also fails (exit 1) while the updater pubkey is OWNER_PUBKEY_REQUIRED or an endpoint is on `.invalid`.
Exit: 0 ok, 1 problems (listed on stderr), 2 usage or unreadable file.
"""
import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_CONF = Path(__file__).resolve().parents[1] / "src-tauri" / "tauri.conf.json"
PLACEHOLDER_KEY = "OWNER_PUBKEY_REQUIRED"
TARGETS = {"appimage", "deb", "app"}


def structure(conf: dict) -> list:
    problems = []
    bundle = conf.get("bundle") or {}
    if set(bundle.get("targets") or []) != TARGETS:
        problems.append(f"bundle.targets must be exactly {sorted(TARGETS)}")
    if bundle.get("createUpdaterArtifacts") is not True:
        problems.append("bundle.createUpdaterArtifacts must be true")
    if bundle.get("externalBin"):
        problems.append("bundle.externalBin must be absent: the sidecar runs from the onedir resource tree")
    if not bundle.get("resources"):
        problems.append("bundle.resources must carry the sidecar onedir tree")
    updater = (conf.get("plugins") or {}).get("updater")
    if not isinstance(updater, dict):
        return problems + ["plugins.updater is missing"]
    pubkey = updater.get("pubkey")
    if not isinstance(pubkey, str) or not pubkey.strip():
        problems.append("plugins.updater.pubkey must be a non-empty string")
    elif "PRIVATE" in pubkey.upper():
        problems.append("plugins.updater.pubkey looks like private key material")
    endpoints = updater.get("endpoints")
    if not isinstance(endpoints, list) or not endpoints:
        problems.append("plugins.updater.endpoints must be a non-empty list")
    else:
        for endpoint in endpoints:
            if not isinstance(endpoint, str) or urlparse(endpoint).scheme != "https":
                problems.append(f"updater endpoint is not https: {endpoint!r}")
    return problems


def release(conf: dict) -> list:
    updater = (conf.get("plugins") or {}).get("updater") or {}
    problems = []
    pubkey = updater.get("pubkey")
    if not isinstance(pubkey, str) or not pubkey.strip() or PLACEHOLDER_KEY in pubkey:
        problems.append(f"plugins.updater.pubkey is a placeholder ({PLACEHOLDER_KEY}): the owner inserts the public key")
    for endpoint in updater.get("endpoints") or []:
        host = urlparse(endpoint).hostname or ""
        if host == "invalid" or host.endswith(".invalid"):
            problems.append(f"updater endpoint is a placeholder (.invalid): {endpoint}")
    return problems


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--release", action="store_true", help="also reject placeholders")
    parser.add_argument("--conf", type=Path, default=DEFAULT_CONF)
    args = parser.parse_args(argv)
    try:
        conf = json.loads(args.conf.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"check-release-config: cannot read {args.conf}: {error}", file=sys.stderr)
        return 2
    problems = structure(conf) + (release(conf) if args.release else [])
    for problem in problems:
        print(f"check-release-config: {problem}", file=sys.stderr)
    if problems:
        return 1
    print("check-release-config: ok" + (" (release)" if args.release else " (structure; placeholders allowed)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
