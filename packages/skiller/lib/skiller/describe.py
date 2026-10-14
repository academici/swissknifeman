"""describe — the skill-descriptor/v1 of one skill of the library or of a host module (read-only)."""
import argparse
import dataclasses
import json
import sys
from pathlib import Path

from aicore.content.skill import describe_skill

from . import custom
from .registry import _package_license
from .skillset import _match, _registry_index


def _find_custom(env, args):
    """The custom skill (project over machine) named by the token, or None."""
    from . import settings
    project = Path(args.project) if args.project else Path.cwd()
    configured = settings.load(project, env=env, strict=False).values.get("custom_dirs") or []
    try:
        layers = custom.discover(project, configured)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    found = [e for _, entries in layers for e in entries if args.skill in (e["id"], e["name"])]
    return found[-1] if found else None


def cmd_describe(env, argv):
    parser = argparse.ArgumentParser(prog="skiller describe",
                                     description="Describe a skill: license, version, digest, provenance.")
    parser.add_argument("skill", metavar="SKILL", help="skill name or bucket/rel")
    parser.add_argument("--project", help="project directory whose .swissknifeman/skills (and configured custom_dirs) count")
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    entry, origin = _find_custom(env, args), "library"
    if entry is not None:
        origin, identity = entry["origin"], entry["id"]
    else:
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
    document = dict(descriptor.to_json(), origin=origin)
    if args.json_output:
        print(json.dumps(document, ensure_ascii=False, indent=2))
        return
    print(f"name: {document['name']}")
    print(f"version: {document['version'] or '-'}")
    print(f"license: {document['license'] or '-'}")
    print(f"source: {document['provenance'].get('source', 'local')}")
    print(f"origin: {document['origin']}")
    print(f"digest: {document['digest']}")
    print(f"requires: {', '.join(document['requires']) or '-'}")
    print(f"adapters: {', '.join(document['adapters']) or '-'}")
    if document["compatibility"]:
        print(f"compatibility: {document['compatibility']}")
    if document["allowed_tools"]:
        print(f"allowed_tools: {' '.join(document['allowed_tools'])}")
