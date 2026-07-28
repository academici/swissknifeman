"""Валидатор реестра ролей ревью (`configs/common/agent-packs/review-roles.json`) — L2.

Extension-таблица по ключу `(pack_id, role_id)` рядом с каноном тел ролей
`configs/common/agent-packs/roles.json` (D126, research/26-P9.2-registry-carrier.md):
`role-bindings.json`/`agentpacks.py` НЕ трогаются, реестр их не расширяет. Восемь
проверок research/18-P9-target-design.md §3.3 (входы 1/2/4/7/8 изменены research/26
§3); каждая несёт в докстринге, какой из семи режимов отказа policy-as-data
(findings/P9-review-stability-facts.md §3, FC-3) она закрывает. Реестр ИНДЕКСИРУЕТ
канон (`projection` — путь к compatibility-asset `agents/reviewer.md`, не носитель
текста правил) — валидатор сверяет форму и наличие, а не содержание правил ревью
(то остаётся треком 1 OQ-4). stdlib-only, без сети."""
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

# Закрытый словарь измерений (research/18 §3.2) — собран из уже написанного в пяти
# `agent-packs/*/agents/reviewer.md` и в `packages/task/commands/review.md` Stage B.
# Новое измерение сюда добавляется ТОЛЬКО синхронно с находкой в реальном паке —
# см. Implementation Rules P9.2 (if-then эскалация).
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
    """Одно нарушение: имя проверки + человекочитаемое сообщение."""

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
    """#1 unvalidated schema (FC-3 #5): реестр — dict с review_version(str), pack_root(str) и roles(list)."""
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
    """#2 default-allow gaps (FC-3 #4): двусторонне. (а) каждый `*/agents/reviewer.md`
    на диске имеет запись в реестре; (б) каждая роль role_id=reviewer из канона
    `roles.json` имеет запись — раньше проверялась только ветка (а), канон не
    участвовал."""
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
    """#3 policy drift from actual behavior (FC-3 #1): projection/overrides
    существуют на диске."""
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
    """#4 policy drift from actual behavior (FC-3 #1): каждый заголовок из `sections`
    реально встречается в каноне `roles.json` `content` (не в проекции); дополнительно
    проверяется, что `projection` несёт те же заголовки — расхождение канона и
    проекции есть отдельное нарушение."""
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
    """#5 unvalidated schema (FC-3 #5): required_sections — ровно четыре канонических
    ключа, и каждый из них объявлен в sections."""
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
    """#6 over-granular roles (FC-3 #7): dimensions ⊆ закрытого словаря, без дублей."""
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
    """#7 duplicate sources of truth (FC-3 #6): вход — `roles.json.skills` (канон),
    не копия в реестре ролей ревью — реестр `skills` не несёт вовсе. Сверка с
    `packages/skiller/skills.json` — канон против канона."""
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


# Отпечаток состава `roles`, зафиксированный на каждую известную review_version —
# вписывается вручную при осознанном бампе (не выводится из даты/времени, ниже
# нарочно нет автогенерации). Смена состава без правки этой карты + review_version
# краснит проверку #8 на самой себе.
_VERSION_FINGERPRINTS = {
    "1.0.0": "acf0b20936e11c64970fa9354350f000c55be4efaccff7f04b34424b1ffbbd76",
}


def check_version_bump(data):
    """#8 unversioned policy (FC-3 #2): review_version сверяется с ЗАФИКСИРОВАННЫМ
    отпечатком состава `roles` (не с датой изменения файла) — состав разошёлся, а
    версия/карта отпечатков не обновлены ⇒ ERROR."""
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
    """Прогоняет все восемь проверок. Возвращает (violations, exit_code):
    0 — чисто, 1 — есть нарушения, 2 — битый/нечитаемый вход."""
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
