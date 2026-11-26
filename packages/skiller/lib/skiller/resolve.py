"""Read-only skill identity resolution from skills.json using the shared dependency BFS."""
import argparse
import json
from pathlib import Path

from aicore.content.skill import resolve_requires_bfs
from aicore.util.io import safe_load_json
from aicore.util.term import die


def resolve_skills(registry, requested, provider=None):
    """Return the deterministic v1 response, including errors and partial results."""
    entries = registry["skills"] if isinstance(registry, dict) else registry
    entries = [s for s in entries if not s.get("quarantined")]  # compat-report.json quarantine (P8.6)
    by_id = {f"{s['bucket']}/{s['name']}": s for s in entries}
    by_name = {}
    for identity, entry in sorted(by_id.items()):
        by_name.setdefault(entry["name"], []).append(identity)

    def candidates(token):
        normalized = token.replace(":", "/", 1)
        if "/" in normalized:
            return [normalized] if normalized in by_id else []
        return by_name.get(normalized, [])

    def dependency_token(token):
        matches = candidates(token)
        return matches[0] if len(matches) == 1 else token.replace(":", "/", 1)

    diagnostics, requested_ids = [], []
    selected = set()

    def ambiguous(token, matches):
        diagnostic = {"code": "SKILL_AMBIGUOUS", "severity": "error",
                      "skill": token, "candidates": matches}
        if diagnostic not in diagnostics:
            diagnostics.append(diagnostic)

    for token in requested:
        matches = candidates(token)
        identity = matches[0] if len(matches) == 1 else token.replace(":", "/", 1)
        if identity not in requested_ids:
            requested_ids.append(identity)
        if len(matches) == 1:
            selected.add(identity)
        elif matches:
            ambiguous(token, matches)
        else:
            diagnostic = {"code": "SKILL_UNKNOWN", "severity": "error", "skill": token}
            if diagnostic not in diagnostics:
                diagnostics.append(diagnostic)

    def lookup(token):
        matches = candidates(token)
        if len(matches) > 1:
            ambiguous(token, matches)
            return None
        if not matches:
            return None
        identity = matches[0]
        entry = by_id[identity]
        return {"key": identity, "exclude_tokens": set(),
                "requires": [dependency_token(dep) for dep in entry.get("requires", [])]}

    # Use canonical IDs for both queue tokens and selected keys. Mixing bare names
    # with qualified keys would defeat the BFS's visited check on cyclic requires.
    seed = [(dependency_token(dep), identity) for identity in sorted(selected)
            for dep in by_id[identity].get("requires", [])]
    dependency_diagnostics = []
    resolve_requires_bfs(seed, lookup, selected, set(), diagnostics=dependency_diagnostics)
    ambiguous_tokens = {d["skill"] for d in diagnostics if d["code"] == "SKILL_AMBIGUOUS"}
    diagnostics.extend(d for d in dependency_diagnostics
                       if d["required_skill"] not in ambiguous_tokens)

    # Closure traversal is owned by the shared BFS; this projection collects all
    # direct incoming edges, including diamonds and explicitly requested parents.
    required_by = {identity: set() for identity in selected}
    for parent in sorted(selected):
        for dep in by_id[parent].get("requires", []):
            identity = dependency_token(dep)
            if identity in required_by:
                required_by[identity].add(parent)

    skills = []
    for identity in sorted(selected, key=lambda key: (by_id[key]["name"], key)):
        entry = by_id[identity]
        skills.append({"name": entry["name"], "id": identity, "bucket": entry["bucket"],
                       "path": entry["path"], "requested": identity in requested_ids,
                       "required_by": sorted(required_by[identity])})
        if provider is not None and "adapters" in entry:
            accepted = {provider, "claude"} if provider == "claude-code" else {provider}
            if not accepted.intersection(entry["adapters"]):
                diagnostics.append({"code": "SKILL_PROVIDER_UNSUPPORTED", "severity": "warning",
                                    "skill": identity, "provider": provider})

    document = {"schema": "skiller.resolve/v1", "requested": requested_ids,
                "provider": provider, "skills": skills, "diagnostics": diagnostics}
    _validate_resolve(document)
    return document


def _validate_resolve(document):
    """Refuse a resolve document the schema does not accept (``SKILLER_RESOLVE_INVALID``)."""
    from aicore.util.schema import load_contract, validate
    directory = Path(__file__).resolve().parents[2] / "schemas" / "resolve" / "v1"
    registry, kind = load_contract(directory, urn_prefix="urn:swissknifeman:skiller:")
    issues = validate(document, kind, registry)
    if issues:
        die("SKILLER_RESOLVE_INVALID: " + "; ".join(issue.message for issue in issues[:5]))


def cmd_resolve(env, argv):
    parser = argparse.ArgumentParser(prog="skiller resolve",
                                     description="Resolve skills and their transitive requirements.")
    parser.add_argument("skills", nargs="+", metavar="SKILL")
    parser.add_argument("--provider", choices=("claude-code", "codex", "grok", "antigravity"))
    parser.add_argument("--json", action="store_true", dest="json_output")
    args = parser.parse_args(argv)
    registry = safe_load_json(env.root / "skills.json",
                              on_error=lambda error: die(f"skills.json: {error}"))
    result = resolve_skills(registry, args.skills, args.provider)
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("id  requested|required_by")
        for skill in result["skills"]:
            detail = "requested" if skill["requested"] else "required_by: " + ", ".join(skill["required_by"])
            print(f"{skill['id']}  {detail}")
        for diagnostic in result["diagnostics"]:
            print(json.dumps(diagnostic, ensure_ascii=False))
    if any(d["severity"] == "error" for d in result["diagnostics"]):
        raise SystemExit(1)
