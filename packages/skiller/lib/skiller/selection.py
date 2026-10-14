"""selection — the selection sidecars `selection.json` (skill-selection/v1, D10) and the table of exclusive groups.

A sidecar sits beside `SKILL.md`; a skill without one is `kind: domain` with no triggers. `skiller registry`
copies the sidecar into `skills.json` (`selection`), `skiller selection check` is the gate of `validate.sh`,
`skiller selection report` compares the decisions with the audit summary (`configs/selection-summary.json`)."""
import json
import sys
from collections import Counter
from pathlib import Path

import aicore
from aicore.util.cli import parse_flags
from aicore.util.schema import load_contract, validate
from aicore.util.term import die

SIDECAR = "selection.json"
SCHEMA_ID = "skill-selection/v1"
GROUPS_FILE = Path("configs") / "exclusive-groups.json"
SUMMARY_FILE = Path("configs") / "selection-summary.json"
GROUPS_SCHEMA_ID = "exclusive-groups/v1"
_CONTRACT_DIR = Path(aicore.__file__).resolve().parents[2] / "schemas" / "skill-selection" / "v1"


def skill_ids(root):
    """{`bucket/folder`: skill directory} of every `skills/<bucket>/<folder>/SKILL.md` of the library."""
    found = {}
    for skill_md in sorted(Path(root).glob("skills/*/*/SKILL.md")):
        found[f"{skill_md.parts[-3]}/{skill_md.parts[-2]}"] = skill_md.parent
    return found


def read_sidecar(skill_dir):
    """The sidecar document of a skill directory, or None when it has none. A broken file is a ValueError."""
    path = Path(skill_dir) / SIDECAR
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{path}: {exc}") from None
    if not isinstance(document, dict):
        raise ValueError(f"{path}: must be a JSON object")
    return document


def registry_selection(document):
    """What `skills.json` keeps of a sidecar: the document without its schema marker."""
    return {key: value for key, value in document.items() if key != "schema"}


def read_groups(root):
    """The exclusive-group table `{group: {description, members, max | router}}`; `{}` when the file is absent."""
    path = Path(root) / GROUPS_FILE
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{GROUPS_FILE}: {exc}") from None
    groups = document.get("groups") if isinstance(document, dict) else None
    if not isinstance(groups, dict) or document.get("schema") != GROUPS_SCHEMA_ID:
        raise ValueError(f"{GROUPS_FILE}: must be an {GROUPS_SCHEMA_ID} object with `groups`")
    return groups


def check(root):
    """Problems (list of strings) of the sidecars and the group table; an empty list is green.

    Checks: the sidecar parses and matches skill-selection/v1; `conflicts` name existing skills (not itself);
    `exclusive_group` is a group of the table that lists the skill as a member; the table is well formed (members
    exist, exactly one of `max` >= 1 and `router` that is a member)."""
    root = Path(root)
    problems = []
    ids = skill_ids(root)
    registry, kind = load_contract(_CONTRACT_DIR)
    try:
        groups = read_groups(root)
    except ValueError as exc:
        groups = {}
        problems.append(str(exc))
    for name, group in sorted(groups.items()):
        where = f"{GROUPS_FILE}: group {name}"
        members = group.get("members") if isinstance(group, dict) else None
        if not isinstance(members, list) or not members:
            problems.append(f"{where}: `members` must be a non-empty list")
            continue
        for member in members:
            if member not in ids:
                problems.append(f"{where}: member {member} is not a skill of the library")
        has_max, has_router = "max" in group, "router" in group
        if has_max == has_router:
            problems.append(f"{where}: exactly one of `max` and `router` is required")
        elif has_max and not (isinstance(group["max"], int) and group["max"] >= 1):
            problems.append(f"{where}: `max` must be an integer >= 1")
        elif has_router and group["router"] not in members:
            problems.append(f"{where}: router {group['router']} must be a member")
    for skill_id, skill_dir in ids.items():
        try:
            document = read_sidecar(skill_dir)
        except ValueError as exc:
            problems.append(f"{exc}")
            continue
        if document is None:
            continue
        rel = f"skills/{skill_id}/{SIDECAR}"
        for issue in validate(document, kind, registry):
            problems.append(f"{rel}: {issue.message}")
        for other in document.get("conflicts", ()) if isinstance(document.get("conflicts"), list) else ():
            if other == skill_id:
                problems.append(f"{rel}: conflicts names the skill itself")
            elif other not in ids:
                problems.append(f"{rel}: conflicts {other} is not a skill of the library")
        group = document.get("exclusive_group")
        if isinstance(group, str):
            if group not in groups:
                problems.append(f"{rel}: exclusive_group {group} is not in {GROUPS_FILE}")
            elif skill_id not in (groups[group].get("members") or ()):
                problems.append(f"{rel}: exclusive_group {group} does not list {skill_id} as a member")
    return problems


def _summary(root):
    path = Path(root) / SUMMARY_FILE
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def report(root):
    """Decision summary of the library and its difference from the audit summary.

    `{skills, with_selection, decisions, leaves_runtime, expected, differences}`: `differences` lists the codes whose
    count is not the audited one (a list, not a failure); `expected` is None without `configs/selection-summary.json`."""
    ids = skill_ids(root)
    counts = Counter()
    leaves = 0
    missing = []
    summary = _summary(root)
    runtime_out = set((summary or {}).get("leaves_runtime_decisions", ()))
    for skill_id, skill_dir in ids.items():
        document = read_sidecar(skill_dir)
        if document is None:
            missing.append(skill_id)
            continue
        code = document.get("decision")
        counts[code] += 1
        if code in runtime_out:
            leaves += 1
    differences = []
    if summary is not None:
        expected = summary["decisions"]
        for code in sorted(set(expected) | set(counts)):
            if expected.get(code, 0) != counts.get(code, 0):
                differences.append({"decision": code, "expected": expected.get(code, 0),
                                    "actual": counts.get(code, 0)})
        if summary.get("leaves_runtime") is not None and summary["leaves_runtime"] != leaves:
            differences.append({"decision": "leaves_runtime", "expected": summary["leaves_runtime"],
                                "actual": leaves})
        if summary.get("total") is not None and summary["total"] != len(ids):
            differences.append({"decision": "skills", "expected": summary["total"], "actual": len(ids)})
    return {
        "skills": len(ids),
        "with_selection": len(ids) - len(missing),
        "without_selection": sorted(missing),
        "decisions": dict(sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))),
        "leaves_runtime": leaves,
        "expected": summary["decisions"] if summary else None,
        "source": summary.get("source") if summary else None,
        "differences": differences,
    }


def cmd_selection(env, argv):
    usage = ("skiller selection report [--json]   decisions of the library against the audit summary (3.5)\n"
             "skiller selection check            sidecars and exclusive groups; exit 1 on a problem")
    if not argv or argv[0] in ("-h", "--help"):
        print(usage)
        return
    sub, args = argv[0], argv[1:]
    if sub == "report":
        opts = parse_flags(args, {"--json": "bool"})
        if opts["help"]:
            print(usage)
            return
        data = report(env.root)
        if opts["json"]:
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return
        print(f"skills: {data['skills']}, with selection.json: {data['with_selection']}")
        for code, count in data["decisions"].items():
            print(f"  {code}: {count}")
        print(f"leave the orchestration runtime: {data['leaves_runtime']}")
        if data["expected"] is None:
            print("audit summary: not available (configs/selection-summary.json)")
        elif data["differences"]:
            print(f"differences from the audit summary ({data['source']}):")
            for item in data["differences"]:
                print(f"  {item['decision']}: audit {item['expected']}, library {item['actual']}")
        else:
            print(f"matches the audit summary ({data['source']})")
        return
    if sub == "check":
        parse_flags(args, {})
        problems = check(env.root)
        if problems:
            for problem in problems:
                print(f"selection: {problem}", file=sys.stderr)
            raise SystemExit(1)
        print("selection: sidecars and exclusive groups are valid")
        return
    die(f"unknown selection command: {sub}\n{usage}")
