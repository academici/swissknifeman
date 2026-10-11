"""Skills of an orch role: closure of the manifest's ``skills`` and the provider's skill delivery mode.

Reads ``roles/<role>.json`` (or ``--manifest``; its ``skills``, else this bridge's ``role-skills.json``) and the capability seed ``bindings/capabilities/<binding>--<provider>.json``
of this package, and asks the partner's generic resolver (``skiller resolve <skill…> --json``, as a process) for the
transitive requirements. Nothing is installed or delivered.

Each skill carries the ``digest`` of its content (``skiller describe <id> --json``, skill-descriptor/v1); when the
partner cannot describe it the digest is absent and the diagnostic ``SKILL_DIGEST_UNKNOWN`` (warning) says so.

Run as ``python3 bridges/orch-skiller/resolve_role.py (--role ID | --manifest PATH) --provider P [--binding B] [--json]``.
Output with ``--json``: ``{"role", "provider", "skills": [{"name", "id", "bucket", "path", "digest"?, "required",
"required_by"}], "delivery": {"mode", "source"}, "diagnostics": []}``. ``required`` is true for a manifest-required
skill and for anything a required skill needs. Exit 1 on an error diagnostic.

``--all-roles --provider P [--binding B]`` resolves every role manifest of orch and prints ``{role_id: [{"name",
"digest"}]}`` as JSON: the input of ``orch.py prepare --skills``. A skill without a digest is left out and its
warning goes to stderr.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from partners import require_orch_root, require_skiller

CONTRACT_VERSION = "exec/v1"
PROVIDERS = ("claude-code", "codex", "grok")
BINDINGS = ("native", "cao", "claude-only")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="resolve_role.py", description=__doc__.splitlines()[0])
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--role", help="role id: roles/<id>.json of this package")
    source.add_argument("--manifest", type=Path, help="path to a role manifest")
    source.add_argument("--all-roles", action="store_true", dest="all_roles",
                        help="every role of orch; prints {role_id: [{name, digest}]} as JSON")
    p.add_argument("--provider", required=True, choices=PROVIDERS)
    p.add_argument("--binding", default="native", choices=BINDINGS, help="capability seed binding (default native)")
    p.add_argument("--json", action="store_true", dest="json_output")
    return p


class RoleRefused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")


def load_manifest(role: str | None, manifest: Path | None) -> dict:
    path = manifest if manifest else require_orch_root() / "roles" / f"{role}.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise RoleRefused("ROLE_UNKNOWN", f"no role manifest {path}") from error
    except (OSError, ValueError) as error:
        raise RoleRefused("ROLE_MANIFEST_INVALID", f"{path}: {error}") from error
    if not isinstance(doc, dict) or doc.get("contract_version") != CONTRACT_VERSION:
        found = doc.get("contract_version") if isinstance(doc, dict) else None
        raise RoleRefused("CONTRACT_VERSION", f"{path}: expected {CONTRACT_VERSION}, found {found!r}")
    if not isinstance(doc.get("role_id"), str) or not isinstance(doc.get("skills", []), list):
        raise RoleRefused("ROLE_MANIFEST_INVALID", f"{path}: needs role_id and a skills list")
    return doc


def role_skills(role_id: str) -> list[dict]:
    """Skills this bridge lists for a role whose manifest names none (the neutral core does not name skills)."""
    try:
        return json.loads((Path(__file__).resolve().parent / "role-skills.json").read_text(encoding="utf-8"))["roles"].get(role_id, [])
    except (OSError, ValueError, KeyError) as error:
        raise RoleRefused("ROLE_MANIFEST_INVALID", f"role-skills.json: {error}") from error


def delivery(binding: str, provider: str, diagnostics: list[dict]) -> dict:
    orch_root = require_orch_root()
    seed = orch_root / "bindings" / "capabilities" / f"{binding}--{provider}.json"
    source = seed.relative_to(orch_root.parent.parent).as_posix() if seed.is_relative_to(orch_root.parent.parent) else str(seed)
    try:
        mode = json.loads(seed.read_text(encoding="utf-8"))["skill_delivery"]["mode"]
    except (OSError, ValueError, KeyError, TypeError) as error:
        diagnostics.append({"code": "DELIVERY_UNKNOWN", "severity": "warning", "binding": binding, "provider": provider,
                            "message": f"no usable skill_delivery in {seed.name}: {error.__class__.__name__}"})
        return {"mode": "unknown", "source": source}
    return {"mode": mode, "source": source}


def run_skiller(skills: list[str], provider: str) -> dict:
    launcher = require_skiller()
    done = subprocess.run([str(launcher), "resolve", *skills, "--provider", provider, "--json"],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    try:
        return json.loads(done.stdout)
    except ValueError as error:
        raise RoleRefused("RESOLVE_FAILED", (done.stderr.strip() or f"skiller exit {done.returncode}: {error}")) from error


def run_describe(skill_id: str) -> str | None:
    """The content digest of a skill from ``skiller describe <id> --json``, or ``None`` when it cannot be read."""
    launcher = require_skiller()
    done = subprocess.run([str(launcher), "describe", skill_id, "--json"],
                          capture_output=True, text=True, encoding="utf-8", check=False)
    try:
        digest = json.loads(done.stdout)["digest"]
    except (ValueError, KeyError, TypeError):
        return None
    return digest if isinstance(digest, str) and DIGEST.match(digest) else None


def required_closure(declared: dict[str, bool], found: list[dict]) -> set[str]:
    """Ids that a manifest-required skill is or (transitively) needs; ``declared`` maps requested id to ``required``."""
    required = {item["id"] for item in found if item["id"] in declared and declared[item["id"]]}
    changed = True
    while changed:
        changed = False
        for item in found:
            if item["id"] not in required and required.intersection(item["required_by"]):
                required.add(item["id"])
                changed = True
    return required


def resolve_role(manifest: dict, provider: str, binding: str, digests: dict | None = None) -> tuple[dict, bool]:
    """``digests`` caches ``skill id -> digest or None`` across roles."""
    digests = digests if digests is not None else {}
    diagnostics: list[dict] = []
    wanted = manifest.get("skills") or role_skills(manifest["role_id"])
    found: list[dict] = []
    if wanted:
        result = run_skiller([item["name"] for item in wanted], provider)
        found = result["skills"]
        diagnostics.extend(result["diagnostics"])
        ids = dict(zip([item["name"] for item in wanted], result["requested"]))
        declared = {ids[item["name"]]: bool(item["required"]) for item in wanted if item["name"] in ids}
        required = required_closure(declared, found)
    else:
        required = set()
    skills = []
    for item in found:
        if item["id"] not in digests:
            digests[item["id"]] = run_describe(item["id"])
        digest = digests[item["id"]]
        skill = {"name": item["name"], "id": item["id"], "bucket": item["bucket"], "path": item["path"]}
        if digest is not None:
            skill["digest"] = digest
        else:
            diagnostics.append({"code": "SKILL_DIGEST_UNKNOWN", "severity": "warning", "skill": item["id"],
                                "message": f"skiller describe gave no digest for {item['id']}"})
        skills.append({**skill, "required": item["id"] in required, "required_by": item["required_by"]})
    out = {"role": manifest["role_id"], "provider": provider, "skills": skills,
           "delivery": delivery(binding, provider, diagnostics), "diagnostics": diagnostics}
    return out, any(d.get("severity") == "error" for d in diagnostics)


def all_roles(provider: str, binding: str) -> tuple[dict, list[dict], bool]:
    """``({role_id: [{name, digest}]}, diagnostics, failed)`` for every role manifest of orch."""
    cache: dict = {}
    delivered, diagnostics, failed = {}, [], False
    for path in sorted((require_orch_root() / "roles").glob("*.json")):
        out, role_failed = resolve_role(load_manifest(None, path), provider, binding, cache)
        delivered[out["role"]] = [{"name": skill["name"], "digest": skill["digest"]}
                                  for skill in out["skills"] if "digest" in skill]
        diagnostics.extend({**item, "role": out["role"]} for item in out["diagnostics"])
        failed = failed or role_failed
    return delivered, diagnostics, failed


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.all_roles:
        try:
            delivered, diagnostics, failed = all_roles(args.provider, args.binding)
        except RoleRefused as error:
            print(error, file=sys.stderr)
            return 1
        for diagnostic in diagnostics:
            print(json.dumps(diagnostic, ensure_ascii=False), file=sys.stderr)
        print(json.dumps(delivered, ensure_ascii=False, indent=2))
        return 1 if failed else 0
    try:
        out, failed = resolve_role(load_manifest(args.role, args.manifest), args.provider, args.binding)
    except RoleRefused as error:
        print(error, file=sys.stderr)
        return 1
    if args.json_output:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(f"role {out['role']} on {out['provider']}: delivery {out['delivery']['mode']}")
        for skill in out["skills"]:
            print(f"{skill['id']}  {'required' if skill['required'] else 'optional'}")
        for diagnostic in out["diagnostics"]:
            print(json.dumps(diagnostic, ensure_ascii=False))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
