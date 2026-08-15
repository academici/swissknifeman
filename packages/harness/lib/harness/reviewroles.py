"""Internal documentation."""
import hashlib
import json
import sys
from pathlib import Path

from core import safe_load_json

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_COMMON_DIR = _PACKAGE_ROOT / "configs" / "common" / "agent-packs"
_REVIEW_ROLES = _COMMON_DIR / "review-roles.json"
_ROLES_JSON = _COMMON_DIR / "roles.json"
_SKILLS_JSON = _PACKAGE_ROOT.parent / "skiller" / "skills.json"

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
        return [Violation("schema", "review-roles.json: корень не dict")]
    v = []
    if not isinstance(data.get("review_version"), str):
        v.append(Violation("schema", "review_version отсутствует или не строка"))
    if not isinstance(data.get("pack_root"), str):
        v.append(Violation("schema", "pack_root отсутствует или не строка"))
    if not isinstance(data.get("roles"), list):
        v.append(Violation("schema", "roles отсутствует или не список"))
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
                f"{pack_id}/agents/reviewer.md есть на диске, но записи в "
                f"review-roles.json для pack_id={pack_id} нет"))
    if roles_canon is None:
        roles_canon = safe_load_json(_ROLES_JSON, default={})
    for pack_id in sorted(_canon_reviewer_pack_ids(roles_canon)):
        if pack_id not in known_packs:
            v.append(Violation(
                "default-deny",
                f"{pack_id}: role_id=reviewer есть в roles.json, но записи в "
                f"review-roles.json нет"))
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
                v.append(Violation("carrier-paths", f"{pack_id}: {key}={rel!r} не найден на диске"))
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
                    f"{pack_id}: заголовок sections.{name}={heading!r} не найден "
                    f"буквально в roles.json content"))
            elif heading not in projection_lines:
                v.append(Violation(
                    "sections-present",
                    f"{pack_id}: заголовок sections.{name}={heading!r} есть в каноне, "
                    f"но расходится с проекцией {projection_rel}"))
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
                f"{pack_id}: required_sections={required!r}, ожидается ровно "
                f"{sorted(REQUIRED_SECTIONS)!r}"))
        missing = [name for name in required if name not in sections]
        if missing:
            v.append(Violation("required-sections", f"{pack_id}: sections не несёт {missing}"))
    return v


def check_dimensions(data):
    """Internal documentation."""
    v = []
    for r in data.get("roles", []):
        pack_id = r.get("pack_id")
        dims = r.get("dimensions") or []
        if len(dims) != len(set(dims)):
            v.append(Violation("dimensions", f"{pack_id}: dimensions содержит дубликаты"))
        unknown = sorted(d for d in dims if d not in DIMENSIONS)
        if unknown:
            v.append(Violation("dimensions", f"{pack_id}: измерения вне словаря: {unknown}"))
    return v


def check_skills(data, roles_canon=None, skills_index=None):
    """Internal documentation."""
    v = []
    if roles_canon is None:
        roles_canon = safe_load_json(_ROLES_JSON, default={})
    if skills_index is None:
        if not _SKILLS_JSON.is_file():
            return [Violation("skills", "индекс скиллов недоступен: "
                               f"{_SKILLS_JSON} не найден (standalone-раскладка пакета)")]
        raw = safe_load_json(_SKILLS_JSON, default={})
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
                v.append(Violation("skills", f"{pack_id}: skill {name!r} не найден в skills.json"))
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
}


def check_version_bump(data):
    """Internal documentation."""
    version = data.get("review_version")
    fingerprint = _composition_fingerprint(data)
    if version not in _VERSION_FINGERPRINTS:
        return [Violation(
            "version-bump",
            f"review_version={version!r} не зарегистрирован в _VERSION_FINGERPRINTS "
            f"reviewroles.py — при бампе впишите новый отпечаток")]
    if _VERSION_FINGERPRINTS[version] != fingerprint:
        return [Violation(
            "version-bump",
            f"review_version={version!r} не сдвинут, а состав roles изменился "
            f"(отпечаток разошёлся с зафиксированным)")]
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
        return [Violation("schema", f"{path} не читается или содержит битый JSON")], 2
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
        print(f"reviewroles: OK — {len(CHECKS)} проверок, {_REVIEW_ROLES.name} чист")
    else:
        for v in violations:
            print(f"  FAIL: {v}", file=sys.stderr)
        print(f"reviewroles: {len(violations)} нарушени(е/й)", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
