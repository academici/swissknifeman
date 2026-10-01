"""Internal documentation."""
import re
import sys
from pathlib import Path

from core import safe_load_json

_PACKAGE_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _PACKAGE_ROOT.parent.parent
_COMMON_DIR = _PACKAGE_ROOT / "configs" / "common" / "agent-packs"
_EXECUTION_POLICY = _COMMON_DIR / "execution-policy.json"
_ROLES_JSON = _COMMON_DIR / "roles.json"

SUPPORTED_MAJOR = 1

_TOP_LEVEL_KEYS = frozenset({
    "policy_version", "spawn_threshold", "max_parallel_agents",
    "allowed_agent_roles", "delegation_contract",
})

_CONDITION_ROW_KEYS = frozenset({"id", "text", "provenance"})
_SCALE_ROW_KEYS = frozenset({"task_class", "agents", "tool_calls_hint", "unverified", "provenance"})
_TASK_CLASSES = frozenset({"fact-finding", "direct-comparison", "complex-research"})

_SUBJECT_ROW_KEYS = frozenset({
    "subject", "provider", "total", "total_scope", "concurrent",
    "nesting_depth", "settings", "controlled_by_us", "provenance",
})
_SUBJECTS = frozenset({"session-agent-tool", "workflow-runtime", "codex-subagents"})
_PROVIDERS = frozenset({"claude-code", "codex", "cursor"})
_TOTAL_SCOPES = frozenset({"session", "run"})
_FLEET_CAP_KEYS = frozenset({"value", "applies_to", "condition", "provenance"})

_ALLOWED_ROLES_KEYS = frozenset({"source", "key", "rule", "exclusions"})
_EXCLUSION_ROW_KEYS = frozenset({"pack_id", "role_id", "reason"})

_REQUIRED_FIELD_IDS = ("objective", "output_format", "tool_guidance", "source_guidance", "boundaries")
_DELEGATION_CONTRACT_KEYS = frozenset({"required_fields", "refusal_rule", "enforcement_points"})
_FIELD_MARKERS = {
    "objective": "- objective:",
    "output_format": "- output:",
    "tool_guidance": "- tools:",
    "source_guidance": "- sources:",
    "boundaries": "- boundaries:",
}
_GRAMMAR_MARKER = "; output:"
_POINT_KEYS = frozenset({
    "id", "carrier", "carrier_kind", "selector", "field_markers",
    "grammar_marker", "status", "pending_until",
})
_CARRIER_KINDS = frozenset({"role-canon-content", "markdown-template"})
_SELECTOR_KEYS = frozenset({"pack_id", "role_id", "field"})
_STATUSES = frozenset({"pending", "enforced"})
_PENDING_UNTIL_RE = re.compile(r"^\S+\s+P\d+(\.\d+)+$")


class Violation:
    """Internal documentation."""

    def __init__(self, check, message):
        self.check = check
        self.message = message

    def __str__(self):
        return f"[{self.check}] {self.message}"


def check_top_level_keys(data):
    """Internal documentation."""
    v = []
    if not isinstance(data, dict):
        return [Violation("top-level", "root execution-policy.json not dict")]
    keys = set(data)
    for extra in sorted(keys - _TOP_LEVEL_KEYS):
        v.append(Violation("top-level", f"unknown top level key: {extra!r}"))
    for missing in sorted(_TOP_LEVEL_KEYS - keys):
        v.append(Violation("top-level", f"missing required top-level key: {missing!r}"))
    return v


def check_policy_version(data):
    """Internal documentation."""
    version = data.get("policy_version")
    if not isinstance(version, str) or not re.match(r"^\d+\.\d+$", version):
        return [Violation("policy-version", f"policy_version={version!r} is not a form string 'major.minor'")]
    major = int(version.split(".")[0])
    if major != SUPPORTED_MAJOR:
        return [Violation(
            "policy-version",
            f"policy_version={version!r}: major={major} not supported by validator "
            f"(supported {SUPPORTED_MAJOR})")]
    return []


def _check_condition_rows(rows, section):
    v = []
    if not isinstance(rows, list) or not rows:
        return [Violation("spawn-threshold", f"{section} missing or empty")]
    for row in rows:
        if not isinstance(row, dict) or set(row) != _CONDITION_ROW_KEYS:
            v.append(Violation("spawn-threshold", f"{section}: string {row!r} does not carry smoothly {sorted(_CONDITION_ROW_KEYS)}"))
    return v


def check_spawn_threshold(data):
    """Internal documentation."""
    st = data.get("spawn_threshold")
    if not isinstance(st, dict):
        return [Violation("spawn-threshold", "spawn_threshold missing or not object")]
    v = []
    if not isinstance(st.get("decision_rule"), str) or not st.get("decision_rule"):
        v.append(Violation("spawn-threshold", "decision_rule missing or empty"))
    positive = st.get("positive_conditions")
    negative = st.get("negative_conditions")
    v.extend(_check_condition_rows(positive, "positive_conditions"))
    v.extend(_check_condition_rows(negative, "negative_conditions"))
    if isinstance(negative, list):
        neg_ids = {row.get("id") for row in negative if isinstance(row, dict)}
        if "parent-reuses-raw-material" not in neg_ids:
            v.append(Violation("spawn-threshold", "negative_conditions does not carry the required line parent-reuses-raw-material"))
    if isinstance(positive, list) and isinstance(negative, list):
        ids = [row.get("id") for row in positive + negative if isinstance(row, dict)]
        seen = set()
        for cid in ids:
            if cid in seen:
                v.append(Violation("spawn-threshold", f"duplicate id conditions: {cid!r}"))
            seen.add(cid)
    scale = st.get("scale_by_task_class")
    if not isinstance(scale, list) or not scale:
        v.append(Violation("spawn-threshold", "scale_by_task_class missing or empty"))
    else:
        for row in scale:
            if not isinstance(row, dict) or set(row) != _SCALE_ROW_KEYS:
                v.append(Violation("spawn-threshold", f"scale_by_task_class: string {row!r} does not carry smoothly {sorted(_SCALE_ROW_KEYS)}"))
                continue
            if row.get("task_class") not in _TASK_CLASSES:
                v.append(Violation("spawn-threshold", f"task_class={row.get('task_class')!r} out {sorted(_TASK_CLASSES)}"))
            if row.get("unverified") is True and "[UNVERIFIED]" not in str(row.get("provenance", "")):
                v.append(Violation("spawn-threshold", f"scale_by_task_class[{row.get('task_class')!r}]: unverified=true, but provenance does not carry [UNVERIFIED]"))
    return v


def check_max_parallel_agents(data):
    """Internal documentation."""
    mpa = data.get("max_parallel_agents")
    if not isinstance(mpa, dict):
        return [Violation("max-parallel-agents", "max_parallel_agents missing or not object (is not a scalar)")]
    v = []
    subjects = mpa.get("subjects")
    if not isinstance(subjects, list):
        v.append(Violation("max-parallel-agents", "subjects missing or not listed"))
        subjects = []
    seen_subjects = []
    by_subject = {}
    for row in subjects:
        if not isinstance(row, dict) or set(row) != _SUBJECT_ROW_KEYS:
            v.append(Violation("max-parallel-agents", f"subjects: string {row!r} does not carry smoothly {sorted(_SUBJECT_ROW_KEYS)}"))
            continue
        seen_subjects.append(row.get("subject"))
        by_subject[row.get("subject")] = row
        if row.get("provider") not in _PROVIDERS:
            v.append(Violation("max-parallel-agents", f"subjects[{row.get('subject')!r}]: provider={row.get('provider')!r} out {sorted(_PROVIDERS)}"))
        if row.get("total_scope") not in _TOTAL_SCOPES:
            v.append(Violation("max-parallel-agents", f"subjects[{row.get('subject')!r}]: total_scope={row.get('total_scope')!r} out {sorted(_TOTAL_SCOPES)}"))
    for subject in sorted(_SUBJECTS):
        if seen_subjects.count(subject) != 1:
            v.append(Violation("max-parallel-agents", f"subject {subject!r} present {seen_subjects.count(subject)} times(a) instead of exactly one"))
    fleet_cap = mpa.get("fleet_cap")
    if not isinstance(fleet_cap, dict) or set(fleet_cap) != _FLEET_CAP_KEYS:
        v.append(Violation("max-parallel-agents", f"fleet_cap is missing or not straight {sorted(_FLEET_CAP_KEYS)}"))
        return v
    applies_to = fleet_cap.get("applies_to")
    subject_row = by_subject.get(applies_to)
    if subject_row is None:
        v.append(Violation("max-parallel-agents", f"fleet_cap.applies_to={applies_to!r} does not name an existing subject"))
    else:
        concurrent = subject_row.get("concurrent")
        value = fleet_cap.get("value")
        if isinstance(concurrent, int) and isinstance(value, int) and value > concurrent:
            v.append(Violation("max-parallel-agents", f"fleet_cap.value={value} exceeds concurrent={concurrent} subject {applies_to!r}"))
    return v


def _walk_provenance(node, path, violations):
    """Internal documentation."""
    if isinstance(node, dict):
        has_numeric = any(
            isinstance(val, (int, float)) and not isinstance(val, bool) and key != "provenance"
            for key, val in node.items()
        )
        if has_numeric and not isinstance(node.get("provenance"), str):
            violations.append(Violation("provenance", f"{path}: object carries a numeric field, but does not carry provenance"))
        for key, val in node.items():
            _walk_provenance(val, f"{path}.{key}", violations)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _walk_provenance(item, f"{path}[{i}]", violations)


def check_provenance(data):
    v = []
    _walk_provenance(data, "$", v)
    return v


def check_allowed_agent_roles(data, roles_canon=None):
    """Internal documentation."""
    aar = data.get("allowed_agent_roles")
    if not isinstance(aar, dict):
        return [Violation("allowed-agent-roles", "allowed_agent_roles missing or not object")]
    v = []
    keys = set(aar)
    for extra in sorted(keys - _ALLOWED_ROLES_KEYS):
        v.append(Violation("allowed-agent-roles", f"unknown key: {extra!r} (second list of roles is prohibited)"))
    for missing in sorted(_ALLOWED_ROLES_KEYS - keys):
        v.append(Violation("allowed-agent-roles", f"missing required key: {missing!r}"))
    source = aar.get("source")
    if not isinstance(source, str) or not (_REPO_ROOT / source).is_file():
        v.append(Violation("allowed-agent-roles", f"source={source!r} not found on disk"))
    if roles_canon is None:
        roles_canon = safe_load_json(_ROLES_JSON, default={})
    known = {
        (r.get("pack_id"), r.get("role_id"))
        for r in roles_canon.get("roles", []) if isinstance(r, dict)
    }
    for row in aar.get("exclusions") or []:
        if not isinstance(row, dict) or set(row) != _EXCLUSION_ROW_KEYS:
            v.append(Violation("allowed-agent-roles", f"exclusions: string {row!r} does not carry smoothly {sorted(_EXCLUSION_ROW_KEYS)}"))
            continue
        if (row.get("pack_id"), row.get("role_id")) not in known:
            v.append(Violation("allowed-agent-roles", f"exclusions: role ({row.get('pack_id')!r}, {row.get('role_id')!r}) not found in canon {source}"))
    return v


def _resolve_carrier_text(point, roles_canon):
    """Internal documentation."""
    carrier_path = _REPO_ROOT / point.get("carrier", "")
    if not carrier_path.is_file():
        return None
    if point.get("carrier_kind") == "role-canon-content":
        selector = point.get("selector") or {}
        for r in roles_canon.get("roles", []):
            if (isinstance(r, dict) and r.get("pack_id") == selector.get("pack_id")
                    and r.get("role_id") == selector.get("role_id")):
                return r.get(selector.get("field", "content"), "")
        return None
    return carrier_path.read_text(encoding="utf-8")


def check_delegation_contract(data, roles_canon=None):
    """Internal documentation."""
    dc = data.get("delegation_contract")
    if not isinstance(dc, dict):
        return [Violation("delegation-contract", "delegation_contract missing or not object")]
    v = []
    keys = set(dc)
    for extra in sorted(keys - _DELEGATION_CONTRACT_KEYS):
        v.append(Violation("delegation-contract", f"unknown key: {extra!r}"))
    for missing in sorted(_DELEGATION_CONTRACT_KEYS - keys):
        v.append(Violation("delegation-contract", f"missing required key: {missing!r}"))

    required = dc.get("required_fields")
    ids = [row.get("id") for row in required if isinstance(row, dict)] if isinstance(required, list) else None
    if ids != list(_REQUIRED_FIELD_IDS):
        v.append(Violation("delegation-contract", f"required_fields={ids!r}, expected exactly {list(_REQUIRED_FIELD_IDS)} in order"))
    if isinstance(required, list):
        for row in required:
            if not isinstance(row, dict) or set(row) != _CONDITION_ROW_KEYS:
                v.append(Violation("delegation-contract", f"required_fields: string {row!r} does not carry smoothly {sorted(_CONDITION_ROW_KEYS)}"))

    if not isinstance(dc.get("refusal_rule"), str) or not dc.get("refusal_rule"):
        v.append(Violation("delegation-contract", "refusal_rule missing or empty"))

    points = dc.get("enforcement_points")
    if not isinstance(points, list) or not points:
        v.append(Violation("delegation-contract", "enforcement_points missing or empty"))
        return v

    if roles_canon is None:
        roles_canon = safe_load_json(_ROLES_JSON, default={})
    seen_ids = set()
    for point in points:
        if not isinstance(point, dict):
            v.append(Violation("delegation-contract", f"enforcement_points: string {point!r} not object"))
            continue
        pid = point.get("id")
        if pid in seen_ids:
            v.append(Violation("delegation-contract", f"enforcement_points: duplicate id {pid!r}"))
        seen_ids.add(pid)

        carrier_kind = point.get("carrier_kind")
        expected_keys = set(_POINT_KEYS)
        if carrier_kind != "role-canon-content":
            expected_keys = expected_keys - {"selector"}
        actual = set(point)
        if point.get("status") == "enforced":
            expected_keys = expected_keys - {"pending_until"}


        for extra in sorted(actual - _POINT_KEYS):
            v.append(Violation("delegation-contract", f"{pid}: unknown enforcement point key: {extra!r}"))

        if not isinstance(point.get("carrier"), str) or not (_REPO_ROOT / point.get("carrier", "")).is_file():
            v.append(Violation("delegation-contract", f"{pid}: carrier={point.get('carrier')!r} not found on disk"))
        if carrier_kind not in _CARRIER_KINDS:
            v.append(Violation("delegation-contract", f"{pid}: carrier_kind={carrier_kind!r} out {sorted(_CARRIER_KINDS)}"))

        has_selector = "selector" in point
        if carrier_kind == "role-canon-content" and not has_selector:
            v.append(Violation("delegation-contract", f"{pid}: carrier_kind=role-canon-content requires selector"))
        elif carrier_kind != "role-canon-content" and has_selector:
            v.append(Violation("delegation-contract", f"{pid}: selector is prohibited when carrier_kind={carrier_kind!r}"))
        elif has_selector and (not isinstance(point.get("selector"), dict) or set(point["selector"]) != _SELECTOR_KEYS):
            v.append(Violation("delegation-contract", f"{pid}: selector does not carry smoothly {sorted(_SELECTOR_KEYS)}"))

        field_markers = point.get("field_markers")
        if not isinstance(field_markers, dict) or set(field_markers) != set(_FIELD_MARKERS):
            v.append(Violation("delegation-contract", f"{pid}: field_markers does not carry smoothly {sorted(_FIELD_MARKERS)}"))
        else:
            for fid, marker in _FIELD_MARKERS.items():
                if field_markers.get(fid) != marker:
                    v.append(Violation("delegation-contract", f"{pid}: field_markers[{fid!r}]={field_markers.get(fid)!r} ≠ canonical literal {marker!r}"))
        if point.get("grammar_marker") != _GRAMMAR_MARKER:
            v.append(Violation("delegation-contract", f"{pid}: grammar_marker={point.get('grammar_marker')!r} ≠ canonical literal {_GRAMMAR_MARKER!r}"))

        status = point.get("status")
        if status not in _STATUSES:
            v.append(Violation("delegation-contract", f"{pid}: status={status!r} out {sorted(_STATUSES)}"))
            continue
        pending_until = point.get("pending_until")
        if status == "pending":
            if not isinstance(pending_until, str) or not _PENDING_UNTIL_RE.match(pending_until):
                v.append(Violation("delegation-contract", f"{pid}: status=pending requires pending_until forms '<PLAN-ID> Pn.m', received {pending_until!r}"))
        elif "pending_until" in point:
            v.append(Violation("delegation-contract", f"{pid}: status=enforced prohibits pending_until, received {pending_until!r}"))

        if status == "enforced":
            text = _resolve_carrier_text(point, roles_canon)
            if text is None:
                v.append(Violation("delegation-contract", f"{pid}: status=enforced, but the carrier/selector field does not resolve"))
            else:
                missing_markers = [fid for fid, marker in _FIELD_MARKERS.items() if marker not in text]
                if missing_markers:
                    v.append(Violation("delegation-contract", f"{pid}: status=enforced, but the markers are physically missing: {missing_markers}"))
                if _GRAMMAR_MARKER not in text:
                    v.append(Violation("delegation-contract", f"{pid}: status=enforced, but grammar_marker is not physically present"))
    return v


CHECKS = (
    check_top_level_keys, check_policy_version, check_spawn_threshold,
    check_max_parallel_agents, check_provenance, check_allowed_agent_roles,
    check_delegation_contract,
)


def run_checks(execution_policy_path=None):
    """Internal documentation."""
    path = execution_policy_path or _EXECUTION_POLICY
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
        print("usage: python3 -m harness.execpolicy --check", file=sys.stderr)
        return 2
    violations, code = run_checks()
    if not violations:
        print(f"execpolicy: OK — {len(CHECKS)} checks, {_EXECUTION_POLICY.name} clean")
    else:
        for v in violations:
            print(f"  FAIL: {v}", file=sys.stderr)
        print(f"execpolicy: {len(violations)} violation(e/th)", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
