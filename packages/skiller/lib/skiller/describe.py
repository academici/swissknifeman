"""describe — the skill-descriptor/v1 of one skill of the library or of a host module (read-only)."""
import argparse
import dataclasses
import json
import sys

from aicore.content.skill import describe_skill

from .registry import _package_license
from .skillset import _match, _registry_index


def cmd_describe(env, argv):
    parser = argparse.ArgumentParser(prog="skiller describe",
                                     description="Describe a skill: license, version, digest, provenance.")
    parser.add_argument("skill", metavar="SKILL", help="skill name or bucket/rel")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    by_key, by_name = _registry_index(env)
    entry = _match(args.skill, by_key, by_name)
    if entry is None:
        print(f"unknown skill: {args.skill}", file=sys.stderr)
        raise SystemExit(1)
    identity = f"{entry['bucket']}/{entry['rel']}" if entry["rel"] else f"{entry['bucket']}/{entry['name']}"
    try:
        descriptor = describe_skill(entry["skill_dir"], skill_id=identity)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    if not descriptor.license:
        descriptor = dataclasses.replace(descriptor, license=_package_license(env.root))
    document = descriptor.to_json()
    if args.json_output:
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return
    print(f"name: {document['name']}")
    print(f"version: {document['version'] or '-'}")
    print(f"license: {document['license'] or '-'}")
    print(f"source: {document['provenance'].get('source', 'local')}")
    print(f"digest: {document['digest']}")
    print(f"requires: {', '.join(document['requires']) or '-'}")
    print(f"adapters: {', '.join(document['adapters']) or '-'}")
    if document["compatibility"]:
        print(f"compatibility: {document['compatibility']}")
    if document["allowed_tools"]:
        print(f"allowed_tools: {' '.join(document['allowed_tools'])}")
