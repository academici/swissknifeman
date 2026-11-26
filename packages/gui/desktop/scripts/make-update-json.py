#!/usr/bin/env python3
"""Builds the static update JSON of the Tauri updater from a signed artifact (D9, D26).

Usage: make-update-json.py --version V --platform linux-x86_64 --artifact PATH --sig PATH --url https://... \
           [--notes TEXT] [--pub-date 2026-10-17T12:00:00Z] [--out FILE]
The signature is read from the .sig file as text and is not verified here (the Tauri updater verifies it with the
public key). The output is deterministic (sorted keys); pub_date is UTC without milliseconds (now, unless given).
Refuses: empty signature, a version that is not semver, a url that is not https, missing files. Exit 0 or 1.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
PLATFORM = re.compile(r"^(linux|darwin|windows)-[a-z0-9_]+(-(appimage|deb|rpm|app|msi|nsis))?$")
PUB_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


class Refusal(Exception):
    pass


def build(version, platform, artifact, sig, url, notes="", pub_date=None) -> dict:
    if not SEMVER.match(version):
        raise Refusal(f"version is not semver: {version!r}")
    if not PLATFORM.match(platform):
        raise Refusal(f"platform must look like linux-x86_64: {platform!r}")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise Refusal(f"url must be https: {url!r}")
    if not Path(artifact).is_file():
        raise Refusal(f"artifact does not exist: {artifact}")
    if not Path(sig).is_file():
        raise Refusal(f"signature file does not exist: {sig}")
    signature = Path(sig).read_text(encoding="utf-8").strip()
    if not signature:
        raise Refusal(f"signature is empty: {sig}")
    if pub_date is None:
        pub_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    elif not PUB_DATE.match(pub_date):
        raise Refusal(f"pub_date must be UTC like 2026-10-17T12:00:00Z: {pub_date!r}")
    return {
        "version": version,
        "notes": notes,
        "pub_date": pub_date,
        "platforms": {platform: {"signature": signature, "url": url}},
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--version", required=True)
    parser.add_argument("--platform", required=True)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--sig", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--notes", default="")
    parser.add_argument("--pub-date")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        document = build(args.version, args.platform, args.artifact, args.sig, args.url, args.notes, args.pub_date)
    except Refusal as error:
        print(f"make-update-json: {error}", file=sys.stderr)
        return 1
    text = json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
