"""Internal documentation."""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from aicore.util.io import safe_load_json

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_COMMON_DIR = _PACKAGE_ROOT / "configs" / "common" / "agent-packs"
_REVIEW_ROLES = _COMMON_DIR / "review-roles.json"
_ROLES_JSON = _COMMON_DIR / "roles.json"

REQUIRED_SECTIONS = ("criteria", "verdict_gates", "project_overrides", "output")





DIMENSIONS = frozenset({
    "access-layer", "layering", "n-plus-one", "validation", "authorization",
    "migrations-vs-models", "model-conventions", "glossary", "config-honesty",
    "transactions", "idempotency-races", "test-honesty", "over-engineering",
    "generated-assets", "public-api-bc", "service-provider-lifecycle", "publishables",
    "env-outside-config", "composer-constraints", "testbench-infra",
    "multi-version-matrix", "state-management", "resource-lifecycle", "null-safety",
    "pos-embedded", "ffi", "typing", "security", "structure", "reactivity",
    "accessibility",
})


class Violation:
    """Internal documentation."""

    def __init__(self, check, message):
        self.check = check
        self.message = message

    def __str__(self):
        return f"[{self.check}] {self.message}"


def _roles_by_pack(data):
    return {r.get("pack_id"): r for r in data.get("roles", []) if isinstance(r, dict)}


def _canon_reviewer_pack_ids(roles_canon):
    return {
        r.get("pack_id") for r in roles_canon.get("roles", [])
        if isinstance(r, dict) and r.get("role_id") == "reviewer"
    }


def check_schema(data):
    """Internal documentation."""
    if not isinstance(data, dict):
        return [Violation("schema", "review-roles.json: root not dict")]
    v = []
    if not isinstance(data.get("review_version"), str):
        v.append(Violation("schema", "review_version is missing or not a string"))
    if not isinstance(data.get("pack_root"), str):
        v.append(Violation("schema", "pack_root is missing or not a string"))
    if not isinstance(data.get("roles"), list):
        v.append(Violation("schema", "roles missing or not listed"))
    return v


def check_default_deny(data, roles_canon=None):
    """Internal documentation."""
    v = []
    pack_root = data.get("pack_root") or ""
    agent_packs_dir = _PACKAGE_ROOT / "configs" / pack_root
    known_packs = set(_roles_by_pack(data))
    for path in sorted(agent_packs_dir.glob("*/agents/reviewer.md")):
        pack_id = path.parent.parent.name
        if pack_id not in known_packs:
            v.append(Violation(
                "default-deny",
                f"{pack_id}/agents/reviewer.md is on disk, but the entries in "
                f"review-roles.json for pack_id={pack_id} no"))
    if roles_canon is None:
        roles_canon = safe_load_json(_ROLES_JSON, default={})
    for pack_id in sorted(_canon_reviewer_pack_ids(roles_canon)):
        if pack_id not in known_packs:
            v.append(Violation(
                "default-deny",
                f"{pack_id}: role_id=reviewer is in roles.json, but entries in "
                f"review-roles.json no"))
    return v


def check_carrier_paths(data):
    """Internal documentation."""
    v = []
    pack_root = data.get("pack_root") or ""
    agent_packs_dir = _PACKAGE_ROOT / "configs" / pack_root
    for r in data.get("roles", []):
        pack_id = r.get("pack_id")
        for key in ("projection", "overrides"):
            rel = r.get(key)
            if not rel or not (agent_packs_dir / rel).is_file():
                v.append(Violation("carrier-paths", f"{pack_id}: {key}={rel!r} not found on disk"))
    return v


def check_sections_present(data, roles_canon=None):
    """Internal documentation."""
    v = []
    if roles_canon is None:
        roles_canon = safe_load_json(_ROLES_JSON, default={})
    canon_by_pack = {
        r.get("pack_id"): r for r in roles_canon.get("roles", [])
        if isinstance(r, dict) and r.get("role_id") == "reviewer"
    }
    pack_root = data.get("pack_root") or ""
    agent_packs_dir = _PACKAGE_ROOT / "configs" / pack_root
    for r in data.get("roles", []):
        pack_id = r.get("pack_id")
        canon_role = canon_by_pack.get(pack_id)
        canon_lines = set((canon_role or {}).get("content", "").splitlines())
        projection_rel = r.get("projection")
        projection_path = agent_packs_dir / projection_rel if projection_rel else None
        projection_lines = (
            set(projection_path.read_text(encoding="utf-8").splitlines())
            if projection_path and projection_path.is_file() else set()
        )
        for name, heading in (r.get("sections") or {}).items():
            if heading not in canon_lines:
                v.append(Violation(
                    "sections-present",
                    f"{pack_id}: header sections.{name}={heading!r} not found "
                    f"literally in roles.json content"))
            elif heading not in projection_lines:
                v.append(Violation(
                    "sections-present",
                    f"{pack_id}: header sections.{name}={heading!r} is in canon, "
                    f"but diverges from the projection {projection_rel}"))
    return v


def check_required_sections(data):
    """Internal documentation."""
    v = []
    for r in data.get("roles", []):
        pack_id = r.get("pack_id")
        required = r.get("required_sections") or []
        sections = r.get("sections") or {}
        if set(required) != set(REQUIRED_SECTIONS):
            v.append(Violation(
                "required-sections",
                f"{pack_id}: required_sections={required!r}, expected exactly "
                f"{sorted(REQUIRED_SECTIONS)!r}"))
        missing = [name for name in required if name not in sections]
        if missing:
            v.append(Violation("required-sections", f"{pack_id}: sections does not carry {missing}"))
    return v


def check_dimensions(data):
    """Internal documentation."""
    v = []
    for r in data.get("roles", []):
        pack_id = r.get("pack_id")
        dims = r.get("dimensions") or []
        if len(dims) != len(set(dims)):
            v.append(Violation("dimensions", f"{pack_id}: dimensions contains duplicates"))
        unknown = sorted(d for d in dims if d not in DIMENSIONS)
        if unknown:
            v.append(Violation("dimensions", f"{pack_id}: dimensions outside the dictionary: {unknown}"))
    return v


def skills_index_path():
    """`skills.json` of the skiller partner (`SKM_SKILLER_ROOT`, then the `skiller` command on PATH), or None."""
    candidates = []
    if os.environ.get("SKM_SKILLER_ROOT"):
        candidates.append(Path(os.path.expanduser(os.environ["SKM_SKILLER_ROOT"])))
    found = shutil.which("skiller")
    if found:
        candidates.append(Path(found).resolve().parent.parent)
    for root in candidates:
        if (root / "skills.json").is_file():
            return root / "skills.json"
    return None


def check_skills(data, roles_canon=None, skills_index=None):
    """Internal documentation."""
    v = []
    if roles_canon is None:
        roles_canon = safe_load_json(_ROLES_JSON, default={})
    if skills_index is None:
        index_path = skills_index_path()
        if index_path is None:
            print("PARTNER_UNAVAILABLE: skiller not found (set SKM_SKILLER_ROOT or put skiller on PATH); "
                  "skills of reviewer roles are not checked", file=sys.stderr)
            return []
        raw = safe_load_json(index_path, default={})
        skills_index = {s.get("name") for s in raw.get("skills", []) if isinstance(s, dict)}
    known_packs = set(_roles_by_pack(data))
    for r in roles_canon.get("roles", []):
        if not isinstance(r, dict) or r.get("role_id") != "reviewer":
            continue
        pack_id = r.get("pack_id")
        if pack_id not in known_packs:
            continue
        for name in r.get("skills") or []:
            if name not in skills_index:
                v.append(Violation("skills", f"{pack_id}: skill {name!r} not found in skills.json"))
    return v


def _composition_fingerprint(data):
    roles = sorted(
        (r for r in data.get("roles", []) if isinstance(r, dict)),
        key=lambda r: (r.get("pack_id", ""), r.get("role_id", "")),
    )
    canonical = json.dumps(roles, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()






_VERSION_FINGERPRINTS = {
    "1.0.0": "acf0b20936e11c64970fa9354350f000c55be4efaccff7f04b34424b1ffbbd76",
    "1.0.1": "b3a45a771472aa93532414a1cdbe4e3c6726b3334fb607adae15e86c754a6ca2",
}


def check_version_bump(data):
    """Internal documentation."""
    version = data.get("review_version")
    fingerprint = _composition_fingerprint(data)
    if version not in _VERSION_FINGERPRINTS:
        return [Violation(
            "version-bump",
            f"review_version={version!r} is not registered in _VERSION_FINGERPRINTS "
            f"reviewroles.py — when bumping, enter a new fingerprint")]
    if _VERSION_FINGERPRINTS[version] != fingerprint:
        return [Violation(
            "version-bump",
            f"review_version={version!r} is not shifted, but the composition roles changed "
            f"(the fingerprint diverged from the recorded one)")]
    return []


CHECKS = (
    check_schema, check_default_deny, check_carrier_paths, check_sections_present,
    check_required_sections, check_dimensions, check_skills, check_version_bump,
)


def run_checks(review_roles_path=None):
    """Internal documentation."""
    path = review_roles_path or _REVIEW_ROLES
    data = safe_load_json(path)
    if data is None:
        return [Violation("schema", f"{path} is not readable or contains a broken JSON")], 2
    violations = []
    for check in CHECKS:
        violations.extend(check(data))
    return violations, (1 if violations else 0)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--check" not in argv:
        print("usage: python3 -m harness.reviewroles --check", file=sys.stderr)
        return 2
    violations, code = run_checks()
    if not violations:
        print(f"reviewroles: OK — {len(CHECKS)} checks, {_REVIEW_ROLES.name} clean")
    else:
        for v in violations:
            print(f"  FAIL: {v}", file=sys.stderr)
        print(f"reviewroles: {len(violations)} violation(e/th)", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
