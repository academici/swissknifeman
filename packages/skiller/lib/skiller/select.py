"""select — which skills an orchestration role gets, from the selection sidecars in `skills.json` (PLAN4 P8.2).

`select` is a pure function of the registry entries, the group table and one request; `cmd_select` reads the files.
Steps (audit 2.6.6): explicit include (the caller adds what the role always needs) → path and dependency triggers (only
under the policy `auto`) → per-skill filters (`role_not_allowed`, `tool_missing`, `excluded`, `kind_not_preloaded`,
`duplicated_by_role_contract`) → exclusive groups → token budget (`over_budget`). Nothing is cut: a skill either
enters with its whole body or is excluded with a reason. An explicit include is exempt from every filter but `exclude`
and is never dropped by the budget."""
import argparse
import json
import re
import sys
from pathlib import Path

from aicore.content.budget import estimate_tokens
from aicore.content.skill import skill_digest, split_frontmatter

from . import custom
from .selection import read_groups

POLICIES = ("explicit", "auto")
NOT_PRELOADED_KINDS = ("router", "reference", "persona")
# Dependency manifests of a project, as `<ecosystem>:<package>` names.
_PEP508_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


# --- request signals ------------------------------------------------------------------------------------
def glob_regex(pattern):
    """Regular expression of a path glob: `*` and `?` stay inside a segment, `**` crosses segments."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def path_matches(pattern, path):
    """A pattern without a `/` matches the file name anywhere; otherwise the whole relative path."""
    path = path.replace("\\", "/")
    if path.startswith("./"):
        path = path[2:]
    target = path.rsplit("/", 1)[-1] if "/" not in pattern else path
    return glob_regex(pattern).match(target) is not None


def project_deps(project):
    """`<ecosystem>:<package>` dependency names read from composer.json, package.json and pyproject.toml of a project."""
    project = Path(project)
    found = set()

    def read_json(name):
        try:
            data = json.loads((project / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    for section in ("require", "require-dev"):
        found.update(f"composer:{name}" for name in (read_json("composer.json").get(section) or {}) if "/" in name)
    package = read_json("package.json")
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        found.update(f"npm:{name}" for name in (package.get(section) or {}))
    found.update(f"pip:{name}" for name in _pyproject_deps(project / "pyproject.toml"))
    return sorted(found)


def _pyproject_deps(path):
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    names = []
    try:
        import tomllib
        data = tomllib.loads(text)
    except ImportError:  # Python < 3.11: read the two list forms by hand
        data = None
    except ValueError:
        return []
    if data is not None:
        entries = list((data.get("project") or {}).get("dependencies") or [])
        for group in ((data.get("project") or {}).get("optional-dependencies") or {}).values():
            entries.extend(group)
        names = [m.group(1) for m in map(_PEP508_NAME.match, entries) if m]
        names.extend(name for name in ((data.get("tool") or {}).get("poetry") or {}).get("dependencies", {}) if name != "python")
        return names
    return _pyproject_fallback(text)


def _pyproject_fallback(text):
    """Python < 3.11 has no tomllib: the `dependencies = [...]` list of `[project]` (quoted entries, brackets inside an
    entry such as `foo[bar]>=1` kept) and the keys of `[tool.poetry.dependencies]`."""
    names = []
    start = re.search(r"^dependencies\s*=\s*\[", text, re.M)
    if start:
        entries = re.findall(r"\"([^\"]+)\"|'([^']+)'", _bracket_body(text, start.end()))
        names = [m.group(1) for m in (_PEP508_NAME.match(a or b) for a, b in entries) if m]
    poetry = re.search(r"^\[tool\.poetry\.dependencies\]\s*$(.*?)(?=^\[|\Z)", text, re.S | re.M)
    if poetry:
        keys = re.findall(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*=", poetry.group(1), re.M)
        names.extend(key for key in keys if key != "python")
    return names


def _bracket_body(text, position):
    """The text of a TOML array from just after its `[` to the matching `]`, skipping brackets inside strings."""
    depth, quote, i = 1, None, position
    while i < len(text) and depth:
        char = text[i]
        if quote:
            quote = None if char == quote else quote
        elif char in "\"'":
            quote = char
        elif char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
        i += 1
    return text[position:i - 1]


# --- the pure function -------------------------------------------------------------------------------------
def skill_id(entry):
    return custom.entry_id(entry)  # skills/<bucket>/<folder>/SKILL.md, or the id of a custom skill


def select(entries, request, groups, tokens):
    """The skills of one role.

    `entries` — registry skill entries (`name`, `path`, optional `selection`); `groups` — the exclusive-group table;
    `tokens(id)` — the cost of the whole body. `request` keys: `role`, `paths`, `deps`, `tools`, `include`, `exclude`,
    `budget` (None: no limit), `policy`. Returns `{included, excluded, discoverable, tokens, explain}` where `included`
    rows are `{id, name, reason, tokens}` in selection order and `excluded` rows `{id, reason, detail?}`."""
    policy = request.get("policy", "explicit")
    by_id = {skill_id(e): e for e in entries}
    by_name = {e["name"]: skill_id(e) for e in entries}

    def resolve(token):
        return token if token in by_id else by_name.get(token)

    def selection(sid):
        return by_id[sid].get("selection") or {}

    trace, excluded, candidates = [], [], {}
    explicit = []
    for token in request.get("include", ()):
        sid = resolve(token)
        if sid is None:
            excluded.append({"id": token, "reason": "unknown_skill"})
        elif sid not in candidates:
            candidates[sid] = "explicit"
            explicit.append(sid)
    trace.append({"step": "include", "matched": list(explicit)})
    triggered = []
    if policy == "auto":
        for sid in sorted(by_id):
            if sid in candidates:
                continue
            triggers = selection(sid).get("triggers") or {}
            paths = [p for p in request.get("paths", ()) if any(path_matches(pat, p) for pat in triggers.get("paths", ()))]
            deps = [d for d in triggers.get("deps", ()) if d in set(request.get("deps", ()))]
            if paths:
                candidates[sid] = "trigger_path"
            elif deps:
                candidates[sid] = "trigger_dep"
            else:
                continue
            triggered.append({"id": sid, "reason": candidates[sid], "paths": paths[:5], "deps": deps})
        trace.append({"step": "triggers", "matched": triggered})
    else:
        trace.append({"step": "triggers", "skipped": "policy explicit"})

    excluded_by_request = {resolve(t) for t in request.get("exclude", ())} - {None}
    tools, kept = set(request.get("tools", ())), []
    for sid, reason in candidates.items():
        meta, exempt = selection(sid), reason == "explicit"
        missing = sorted(set(meta.get("requires_tools") or ()) - tools)
        allowed = meta.get("roles") or ()
        if sid in excluded_by_request:
            excluded.append({"id": sid, "reason": "excluded"})
        elif allowed and request["role"] not in allowed and not exempt:
            excluded.append({"id": sid, "reason": "role_not_allowed", "detail": ", ".join(allowed)})
        elif missing and not exempt:
            excluded.append({"id": sid, "reason": "tool_missing", "detail": ", ".join(missing)})
        elif meta.get("kind", "domain") in NOT_PRELOADED_KINDS and not exempt:
            excluded.append({"id": sid, "reason": "kind_not_preloaded", "detail": meta["kind"]})
        elif meta.get("replaced_by") and not exempt:
            excluded.append({"id": sid, "reason": "duplicated_by_role_contract", "detail": meta["replaced_by"]})
        else:
            kept.append(sid)
    trace.append({"step": "filters", "kept": list(kept)})

    dropped = {}
    for name, group in sorted(groups.items()):
        members = [sid for sid in kept if sid in group.get("members", ())]
        if "router" in group:
            continue  # a router is a kind that is not preloaded (kind_not_preloaded); only an explicit include takes it
        live = [sid for sid in members if sid not in dropped]
        for sid in live[group["max"]:]:
            if candidates[sid] != "explicit":
                dropped.setdefault(sid, name)
    for sid in kept:
        if sid in dropped:
            excluded.append({"id": sid, "reason": "exclusive_group", "detail": dropped[sid]})
    kept = [sid for sid in kept if sid not in dropped]
    trace.append({"step": "exclusive_group", "dropped": dict(dropped)})

    included, used = [], 0
    budget = request.get("budget")
    for sid in kept:
        cost = tokens(sid)
        if candidates[sid] != "explicit" and budget is not None and used + cost > budget:
            excluded.append({"id": sid, "reason": "over_budget", "detail": f"{cost} tokens, {max(budget - used, 0)} left"})
            continue
        used += cost
        included.append({"id": sid, "name": by_id[sid]["name"], "reason": candidates[sid], "tokens": cost,
                         "origin": by_id[sid].get("origin", "library")})
    trace.append({"step": "budget", "limit": budget, "used": used})
    discoverable = sorted(row["id"] for row in excluded if row["reason"] == "kind_not_preloaded")
    return {"included": included, "excluded": excluded, "discoverable": discoverable, "tokens": used,
            "explain": {"role": request["role"], "policy": policy, "paths": list(request.get("paths", ())),
                        "deps": list(request.get("deps", ())), "tools": sorted(tools), "trace": trace}}


# --- the command -----------------------------------------------------------------------------------------
def _body_tokens(root, entries=()):
    custom_dirs = {skill_id(e): Path(e["skill_dir"]) for e in entries if e.get("skill_dir")}

    def count(sid):
        skill_dir = custom_dirs.get(sid) or Path(root) / "skills" / sid
        text = (skill_dir / "SKILL.md").read_text(encoding="utf-8-sig")
        return estimate_tokens(split_frontmatter(text)[1])
    return count


def _policy(env, project, given):
    if given:
        return given
    from . import settings
    return settings.load(project, env=env, strict=False).values["selection"]["policy"]


def _parser():
    p = argparse.ArgumentParser(prog="skiller select", description="Select the skills of an orchestration role.")
    p.add_argument("--role", required=True, help="orchestration role, such as executor or reviewer")
    p.add_argument("--paths", nargs="+", default=[], metavar="P", help="project paths the work touches")
    p.add_argument("--deps", nargs="+", default=[], metavar="D", help="dependencies as <ecosystem>:<package>")
    p.add_argument("--project", help="project directory: its manifests add dependencies, its config gives the policy")
    p.add_argument("--model-class", dest="model_class", help="model class of the role (echoed, no selection effect yet)")
    p.add_argument("--provider", help="provider of the role (echoed, no selection effect yet)")
    p.add_argument("--budget", type=int, help="token limit of the preloaded bodies; nothing is cut")
    p.add_argument("--include", nargs="+", default=[], metavar="ID", help="skills to take (name or bucket/folder)")
    p.add_argument("--exclude", nargs="+", default=[], metavar="ID", help="skills never to take; wins over include")
    p.add_argument("--tools", nargs="+", default=[], metavar="T", help="tools of the role (for requires_tools)")
    p.add_argument("--custom-dirs", nargs="+", default=[], dest="custom_dirs", metavar="DIR",
                   help="extra directories of custom skills (machine layer, added to skiller.custom_dirs)")
    p.add_argument("--policy", choices=POLICIES, help="explicit: no triggers; auto: path and dependency triggers")
    p.add_argument("--json", action="store_true", dest="json_output")
    p.add_argument("--explain", action="store_true", help="add the trace of every step")
    return p


def _custom_dirs(env, project, given):
    from . import settings
    configured = settings.load(project, env=env, strict=False).values.get("custom_dirs") or []
    return [*configured, *given]


def cmd_select(env, argv):
    args = _parser().parse_args(argv)
    project = Path(args.project) if args.project else Path.cwd()
    deps = sorted(set(args.deps) | set(project_deps(project) if args.project else ()))
    registry = json.loads((env.root / "skills.json").read_text(encoding="utf-8"))
    policy = _policy(env, project, args.policy)
    request = {"role": args.role, "paths": args.paths, "deps": deps, "tools": args.tools, "include": args.include,
               "exclude": args.exclude, "budget": args.budget, "policy": policy}
    try:
        entries, notes = custom.merge(registry["skills"], custom.discover(project, _custom_dirs(env, project, args.custom_dirs)))
    except (custom.ExtensionAmbiguous, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None
    result = select(entries, request, read_groups(env.root), _body_tokens(env.root, entries))
    by_id = {skill_id(e): e for e in entries}
    for row in result["included"]:
        row["path"] = str((env.root / by_id[row["id"]]["path"]).resolve())
        row["digest"] = by_id[row["id"]].get("digest") or skill_digest(Path(row["path"]).parent)
    if notes:
        result["notes"] = notes
        result.setdefault("explain", {})["custom"] = notes
    result["request"] = {"role": args.role, "provider": args.provider, "model_class": args.model_class,
                         "budget": args.budget, "policy": policy}
    if not args.explain:
        result.pop("explain")
    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"role {args.role}, policy {policy}: {len(result['included'])} skills, {result['tokens']} tokens")
    for row in result["included"]:
        print(f"  + {row['id']}  {row['reason']}  {row['tokens']}  {row['origin']}")
    for row in result["excluded"]:
        print(f"  - {row['id']}  {row['reason']}" + (f"  ({row['detail']})" if row.get("detail") else ""))
    for note in result.get("notes", ()):
        print(f"  ! {note['code']}  {note['id']}  ({note['detail']})")
    if result["discoverable"]:
        print("discoverable: " + ", ".join(result["discoverable"]))
    if args.explain:
        for step in result["explain"]["trace"]:
            print("  step " + json.dumps(step, ensure_ascii=False))
