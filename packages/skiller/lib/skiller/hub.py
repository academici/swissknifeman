"""hub — root hub of skills in the project (managed-block CLAUDE.md / .ai/guidelines).

The generator lives here (importable and testable), `scripts/generate-hub.sh` —
thin launcher on top `python3 -m skiller.hub` (like `bin/skiller`).

BLOCK SHAPE IS DETERMINED BY THE TARGET CHANNEL, not by the project:

  short (`short`)  — target that HAS a native skill listing: `CLAUDE.md`
      Claude Code and Boost-fragment `.ai/guidelines/swissknifeman-hub.md` (Boost
      inserts it into CLAUDE.md — residency is the same). The client keeps it anyway
      resident name+description of each available skill (RAG:✅ 2026-07-31
      <https://code.claude.com/docs/en/features-overview> §Skills), therefore the index
      in the block - the second paid copy: it is not printed, priorities remain
      sources, search rules, and a pointer to the full index.
  Codex (`AGENTS.md`) — short form; confirmation via real offline
      `codex debug prompt-input` from cwd project. Unconfirmed names remain.
  full (`full`)    — target WITHOUT native listing: `--root-files GEMINI.md`
      and any third party root files. There the index is the only carrier
      detection, it remains.
  stub (`stub`)  — default for `CLAUDE.md` and `AGENTS.md`: between markers
      only HTML-comments (registry stamp + pointer to `--full-index`).
      Skills and task-commands are connected natively; prose-hub is not duplicated.

`--full-index` returns the full form to ALL targets with one command (rollback path).
`--hub-legacy-short` — former short form with priorities/search (without full index).

REVIEW BEFORE REDUCTION (is required): a skill is removed from the block only if it
is confirmed in the native active set of the project by TWO independent conditions -
(1) it is included in the meter kit `budget.resolve_active_set` (source named
TK P2.5) AND (2) it is delivered by CHANNEL, which Claude Code enumerates natively
(enabled marketplace plugin or physical copy in `.claude/skills`).
The second condition is added because `resolve_active_set` models an axis
vendor-samples and does NOT read `enabledPlugins`: on connect-project he does not respond to
that question (froze agelto 2026-07-31 — 86 skills set versus 20 delivered
by client). The conjunction is strictly stronger than the requirements of the technical specifications: everything that leaves the block
is in both the meter set and the native channel. Unconfirmed skills
remain listed as a separate section and the discrepancy is printed."""
import hashlib
import json
import os
import sys
from pathlib import Path

from aicore.util.repo import find_repo_root

from .common import HUB_MARKER
from .settings import configured_skills_paths
from aicore.delivery.materialize import MANIFEST
from aicore.util.cli import run_cmd

HUB_START = HUB_MARKER
HUB_END = "<!-- swissknifeman:hub:end -->"

FORM_SHORT = "short"
FORM_FULL = "full"
FORM_STUB = "stub"

CLAUDE_TARGET = "CLAUDE.md"
BOOST_TARGET = Path(".ai") / "guidelines" / "swissknifeman-hub.md"
# Layouts of physical copies where the vendor manifest is searched (index source).
SCAN_ROOTS = (".claude/skills", ".cursor/skills", ".ai/skills")
# The layout that Claude Code lists natively as PROJECT skills.
CLAUDE_SKILLS_DIR = ".claude/skills"
MARKETPLACE_SUFFIX = "@swissknifeman"


def hub_artifacts_exist(target):
    if (target / BOOST_TARGET).is_file():
        return True
    claude_md = target / CLAUDE_TARGET
    return claude_md.is_file() and HUB_MARKER in claude_md.read_text(encoding="utf-8")


def generate_hub(env, target, *, full_index=False, root_files=()):
    argv = [str(env.root / "scripts" / "generate-hub.sh"), "--target", str(target)]
    if full_index:
        argv.append("--full-index")
    if root_files:
        argv.extend(["--root-files", ",".join(root_files)])
    run_cmd(argv)


# --- installed sources --------------------------------------------------
def _load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def enabled_marketplace_buckets(target):
    """Buckets enabled by channel marketplace: enabledPlugins."<bucket>@swissknifeman"."""
    names = []
    for settings_name in ("settings.local.json", "settings.json"):
        data = _load_json(Path(target) / ".claude" / settings_name)
        if not isinstance(data, dict):
            continue
        for key, enabled in (data.get("enabledPlugins") or {}).items():
            if enabled and key.endswith(MARKETPLACE_SUFFIX):
                name = key.split("@", 1)[0]
                if name not in names:
                    names.append(name)
    return names


def collect_installed(registry, target):
    """Installed in the project: {bucket: {name: entry}} + list of found channels.

    Two channels (are merged as before): marketplace-plugins by bucket name
    and vendor manifests in known layouts."""
    target = Path(target)
    by_bucket = {}
    for s in registry["skills"]:
        by_bucket.setdefault(s["bucket"], []).append(s)
    by_source_path = {str(Path(s["path"]).parent): s for s in registry["skills"]}

    installed, channels = {}, {"plugins": [], "manifests": []}

    def add_skill(entry):
        installed.setdefault(entry["bucket"], {})[entry["name"]] = entry

    for bucket in enabled_marketplace_buckets(target):
        channels["plugins"].append(bucket)
        for s in by_bucket.get(bucket, []):
            add_skill(s)

    scan_roots = list(SCAN_ROOTS)
    for sp in configured_skills_paths(target):
        if sp not in scan_roots:
            scan_roots.append(sp)

    for rel_root in scan_roots:
        data = _load_json(target / rel_root / MANIFEST)
        if not isinstance(data, dict):
            continue
        channels["manifests"].append(rel_root)
        for entry in data.get("skills", []):
            skill = by_source_path.get(entry.get("source_path", ""))
            if skill:
                add_skill(skill)
    return installed, channels


def installed_names(installed):
    return {name for bucket in installed.values() for name in bucket}


# --- project agents -------------------------------------------------------------
def parse_agent_frontmatter(path):
    """name + description (scalars) + skills (inline [..] or block list)."""
    fm = {"name": "", "description": "", "skills": []}
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    lines_ = text.splitlines()
    if not lines_ or lines_[0].strip() != "---":
        return fm
    list_key = None
    for line in lines_[1:]:
        if line.strip() == "---":
            break
        stripped = line.strip()
        if list_key and line[:1] in (" ", "\t") and stripped.startswith("- "):
            fm[list_key].append(stripped[2:].strip().strip('"').strip("'"))
            continue
        list_key = None
        if ":" in line and not line.startswith((" ", "\t", "-")):
            key, value = line.split(":", 1)
            key, value = key.strip(), value.strip()
            if key in ("name", "description"):
                fm[key] = value.strip('"').strip("'")
            elif key == "skills":
                if value.startswith("["):
                    fm["skills"] = [v.strip().strip('"').strip("'")
                                    for v in value.strip("[]").split(",") if v.strip()]
                elif value == "":
                    list_key = "skills"  # next block list
    return fm


def collect_agents(target, registry_names):
    """Project Agents (.claude/agents/*.md) + checking them `skills:` with the registry.

    Regression «skills are not visible»: native field skills: at the subagent silently no-op on
    unknown name, so each name is checked."""
    agents, unknown = [], set()
    agents_dir = Path(target) / ".claude" / "agents"
    if not agents_dir.is_dir():
        return agents, unknown
    for af in sorted(agents_dir.glob("*.md")):
        a = parse_agent_frontmatter(af)
        a["file"] = af.name
        checked = []
        for sk in a["skills"]:
            bare = sk.split(":", 1)[1] if ":" in sk else sk  # allowed bucket:name
            ok = bare in registry_names
            if not ok:
                unknown.add(sk)
            checked.append((sk, ok))
        a["skills_checked"] = checked
        agents.append(a)
    return agents, unknown


# --- native active set (reconciliation before reduction) -------------------------
def _marketplace_plugin_skills(env, registry):
    """Skills that are NATIVELY listed by the client for each marketplace plugin.

    Source: generated marketplace entries. Curated plugins explicitly list skills;
    bucket plugins expose their canonical skill directories. Sibling plugin entries
    declared by the host config need native confirmation before their skills count.
    → {plugin: set(names)}; empty dict, if the manifest is not available."""
    monorepo = find_repo_root(env.root) or env.root
    data = _load_json(Path(monorepo) / ".claude-plugin" / "marketplace.json")
    if not isinstance(data, dict):
        return {}
    try:
        pkg_prefix = f"./{Path(env.root).relative_to(monorepo).as_posix()}/"
    except ValueError:
        return {}
    by_source_path = {str(Path(s["path"]).parent): s for s in registry["skills"]}
    out = {}
    for plugin in data.get("plugins", []):
        name = plugin.get("name")
        if not name:
            continue
        names = set()
        paths = plugin.get("skills")
        if isinstance(paths, list):
            for p in paths:
                skill = by_source_path.get(str(p).replace(pkg_prefix, "", 1))
                if skill:
                    names.add(skill["name"])
        else:
            source = str(plugin.get("source", ""))
            if source.startswith(pkg_prefix):
                rel = source[len(pkg_prefix):].rstrip("/")
                for src, skill in by_source_path.items():
                    if src == rel or src.startswith(rel + "/"):
                        names.add(skill["name"])
        out[name] = names
    return out


def _project_skill_names(target):
    """Skills that are physically located in `.claude/skills/<name>/SKILL.md` — their client
    lists natively as project skills."""
    d = Path(target) / CLAUDE_SKILLS_DIR
    if not d.is_dir():
        return set()
    return {p.name for p in sorted(d.iterdir())
            if p.is_dir() and (p / "SKILL.md").is_file()}


def _codex_installed(env, target, registry, installed, channels, inventory):
    """Scope fallback pointers to Codex selection, never Claude-only extras.

    Explicit native config also covers selected plugins whose cache is missing;
    those need fallback pointers even though native ``plugin list`` omits them.
    Discovery/config failure retains the original conservative inventory.
    """
    if not inventory.get("ok"):
        return installed
    from aicore.delivery.codex import SUFFIX, _read, codex_home
    selected = set(inventory.get("enabled", ()))
    overrides = {}
    try:
        for path in (codex_home(env) / "config.toml", Path(target) / ".codex/config.toml"):
            _, config = _read(path)
            for identifier, options in config.get("plugins", {}).items():
                if identifier.endswith(SUFFIX) and "enabled" in options:
                    if not isinstance(options["enabled"], bool):
                        raise ValueError("native plugin enabled is not boolean")
                    overrides[identifier[:-len(SUFFIX)]] = options["enabled"]
    except (OSError, ValueError, TypeError, AttributeError) as error:
        inventory["notes"].append(f"Codex selection unavailable; keeping fallback inventory: {error}")
        return installed
    for plugin, enabled in overrides.items():
        if enabled:
            selected.add(plugin)
        else:
            selected.discard(plugin)
    plugin_skills = _marketplace_plugin_skills(env, registry)
    if not plugin_skills and selected:
        inventory["notes"].append("Codex plugin catalog unavailable; keeping fallback inventory")
        return installed
    candidates = set().union(*(plugin_skills.get(plugin, set()) for plugin in selected))
    by_source = {str(Path(skill["path"]).parent): skill["name"] for skill in registry["skills"]}
    for folder in set(channels["manifests"]) | {".agents/skills"}:
        manifest = _load_json(Path(target) / folder / MANIFEST)
        if not isinstance(manifest, dict):
            continue
        for entry in manifest.get("skills", []):
            if isinstance(entry, dict) and entry.get("source_path") in by_source:
                candidates.add(by_source[entry["source_path"]])
    result = {}
    for skill in registry["skills"]:
        if skill["name"] in candidates:
            result.setdefault(skill["bucket"], {})[skill["name"]] = skill
    return result


def _measurer_active_names(env, target):
    """Active METER set (`budget.resolve_active_set`) — source named
    TK P2.5. Lazy import: budget → vendor → hub, direct import would close the loop.
    → (names, detail); names=None, if the set does not resolve (then we don’t reduce)."""
    try:
        from .budget import resolve_active_set
        from .config import load_config
        config = load_config(env, Path(target))
        skills, _meta = resolve_active_set(env, Path(target), config)
        names = {fm_name or Path(d).name for _b, _r, d, fm_name in skills}
        return names, f"{len(names)} skills"
    except (Exception, SystemExit) as error:  # noqa: BLE001 — fail-closed, not silently
        return None, f"n/a ({error})"


def native_check(env, target, names):
    """Reconciliation before reduction: which of `names` are confirmed by the native set.

    → {confirmed, unconfirmed, native_channel, measurer_detail, notes}."""
    plugin_skills = _marketplace_plugin_skills(env, registry_of(env))
    delivered, plugin_notes = set(), []
    for bucket in enabled_marketplace_buckets(target):
        known = plugin_skills.get(bucket)
        if known is None:
            plugin_notes.append(f"plugin {bucket}@ not found in marketplace.json")
            continue
        delivered |= known
    project_skills = _project_skill_names(target)
    delivered |= project_skills

    measurer_names, measurer_detail = _measurer_active_names(env, target)
    if measurer_names is None:
        confirmed = set()
        notes = [f"meter set does not resolve - abbreviation is disabled: {measurer_detail}"]
    else:
        confirmed = set(names) & delivered & measurer_names
        notes = []
    notes.extend(plugin_notes)
    return {
        "confirmed": confirmed,
        "unconfirmed": sorted(set(names) - confirmed),
        "native_channel": sorted(delivered),
        "measurer_detail": measurer_detail,
        "notes": notes,
    }


_REGISTRY_CACHE = {}


def registry_of(env):
    """skills.json registry (cache per process - reconciliation and index read one file)."""
    key = str(env.root)
    if key not in _REGISTRY_CACHE:
        _REGISTRY_CACHE[key] = json.loads(
            (Path(env.root) / "skills.json").read_text(encoding="utf-8"))
    return _REGISTRY_CACHE[key]


# --- assembly markdown ------------------------------------------------------------
def _priority_lines(boost_mode, form):
    where = ("index below" if form == FORM_FULL
             else "native listing of client skills")
    out = ["## Rule source priority", "",
           "1. Project rules and skills (`.ai/guidelines/`, `.ai/skills/`, "
           "project root instructions) specify local conventions."]
    if boost_mode:
        out.append("2. Laravel Boost: for version-specific themes (Laravel, Pest, "
                   "Inertia, Livewire, Tailwind, Filament) use built-in "
                   "skills/guidelines Boost — they are tied to package versions.")
        out.append(f"3. Skills swissknifeman ({where}) — architecture, structure, "
                   "practices, processes.")
    else:
        out.append(f"2. Skills swissknifeman ({where}) — architecture, structure, "
                   "practices, processes. If they add to the project Laravel Boost, him "
                   "version-specific skills have priority over overlapping ones.")
    out += ["", "Skills complement the environment's instructions and the owner's request; within compatible rules, choose a more specific source "
                "(project > Boost > registry swissknifeman).", ""]
    return out


def _search_lines(form):
    out = ["## How to find the skill you need", ""]
    if form == FORM_FULL:
        out.append("1. Define the task scope and find the bucket in the index below.")
    else:
        out.append("1. Skills swissknifeman are already listed by NATIVE listing "
                   "client (name + description of each available resident skill "
                   "since the beginning of the session) — search for it; the index is not duplicated here.")
    out += ["2. Select a skill according to the description; inside the skill, open snippets only "
            "according to his table «when to open which snippet» — don't download everything.",
            "3. Unlock architectural skills when changing the corresponding contracts; "
            "normal edits follow the existing project structure.",
            "4. The structure of the skill system in the project (source of truth, symlinks, "
            "gitignore) — skill `skills-ssot`."]
    if form == FORM_SHORT:
        out.append("5. Full index with descriptions (if a person needs): "
                   "`skiller status` in the project or "
                   "`generate-hub.sh --target <project> --full-index --dry-run`.")
    out.append("")
    return out


def _agents_lines(agents, unknown_skills):
    if not agents:
        return []
    out = [f"## Project Agents ({len(agents)})", "",
           "Roles in `.claude/agents/`. Preloaded skills - field `skills:` "
           "(⚠ = name not found in the registry, preload will not work silently).", "",
           "| Agent | Purpose | Preloaded skills |", "|---|---|---|"]
    for a in agents:
        sk = ", ".join((f"⚠ {n}" if not ok else n)
                       for n, ok in a["skills_checked"]) or "—"
        desc = (a["description"] or "").replace("|", "\\|").replace("\n", " ")
        if len(desc) > 120:
            desc = desc[:117] + "…"
        out.append(f"| `{a['name'] or a['file']}` | {desc} | {sk} |")
    out.append("")
    if unknown_skills:
        out.append("> ⚠ **Inconsistency:** names in `skills:` not found in the registry: "
                   + ", ".join("`" + u + "`" for u in sorted(unknown_skills))
                   + ". Check the names or connect the right bucket - otherwise preload silently "
                     "won't work.")
        out.append("")
    return out


def _index_lines(installed, buckets_meta, title, note=""):
    total = sum(len(v) for v in installed.values())
    out = [f"## {title} ({total})", ""]
    if note:
        out += [note, ""]
    for bucket in sorted(installed):
        desc = buckets_meta.get(bucket, {}).get("description", "")
        out.append(f"### {bucket}" + (f" — {desc}" if desc else ""))
        out.append("")
        for name in sorted(installed[bucket]):
            out.append(f"- **{name}** — {installed[bucket][name].get('description', '')}")
        out.append("")
    return out


def build_stub_markdown(*, reg_sha, reg_count):
    """Comment-only hub: no resident prose; discovery stays native (plugins/skills/commands)."""
    return "\n".join([
        "<!-- swissknifeman hub: stub — skills and task-commands are connected natively; "
        "index and priority rules are not duplicated here. -->",
        f"<!-- swissknifeman:registry sha={reg_sha} skills={reg_count} -->",
        "<!-- Full index: `skiller status` or generate-hub.sh --target <dir> --full-index. -->",
        "",
    ])


def build_hub_markdown(*, installed, buckets_meta, agents, unknown_skills, reg_sha,
                       reg_count, boost_mode, form, unconfirmed=()):
    """Markdown block in the given FORM. The short form does not print the index except
    skills not confirmed by the native set (they remain listed)."""
    if form == FORM_STUB:
        return build_stub_markdown(reg_sha=reg_sha, reg_count=reg_count)
    lines = ["# Swissknifeman: skills hub", "",
             "<!-- Generated scripts/generate-hub.sh from the registry swissknifeman. -->",
             "<!-- DO NOT edit manually: regeneration will overwrite the edits. -->",
             f"<!-- swissknifeman:registry sha={reg_sha} skills={reg_count} -->", ""]
    lines += _priority_lines(boost_mode, form)
    lines += _search_lines(form)
    lines += _agents_lines(agents, unknown_skills)
    if form == FORM_FULL:
        lines += _index_lines(installed, buckets_meta, "Installed skills")
    else:
        residual = {b: {n: e for n, e in skills.items() if n in set(unconfirmed)}
                    for b, skills in installed.items()}
        residual = {b: s for b, s in residual.items() if s}
        if residual:
            lines += _index_lines(
                residual, buckets_meta, "Skills outside the native listing",
                "> These skills are installed swissknifeman, but not confirmed in "
                "in the project's native active set - listed by name so that "
                "do not lose detection.")
    return "\n".join(lines).rstrip() + "\n"


# --- entry ------------------------------------------------------------------------------
def upsert_block(out, block):
    """Paste/update managed-block between markers; content outside markers is not
    starts moving; the file is created if it is missing."""
    if out.exists():
        text = out.read_text(encoding="utf-8")
        if HUB_START in text and HUB_END in text:
            head, rest = text.split(HUB_START, 1)
            _, tail = rest.split(HUB_END, 1)
            return head + block + tail.lstrip("\n")
        sep = "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
        return text + sep + block
    return block


def target_form(name, *, boost_mode=False, full_index=False, legacy_short=False):
    """Block shape according to the TARGET CHANNEL. `--full-index` returns full to everyone."""
    if full_index:
        return FORM_FULL
    if legacy_short:
        if boost_mode:
            return FORM_SHORT
        return FORM_SHORT if name in (CLAUDE_TARGET, "AGENTS.md") else FORM_FULL
    if boost_mode:
        return FORM_STUB
    return FORM_STUB if name in (CLAUDE_TARGET, "AGENTS.md") else FORM_FULL


def run(env, target, *, dry_run=False, root_files=(), full_index=False, legacy_short=False,
        out=print):
    """Generate and record hub. → dict with summary (for tests and reports)."""
    target = Path(os.path.expanduser(str(target))).resolve()
    registry = registry_of(env)
    buckets_meta = json.loads(
        (Path(env.root) / "buckets.json").read_text(encoding="utf-8"))

    installed, channels = collect_installed(registry, target)
    # CHANNEL gate, not index: there is a distribution - we write the block, even if the index
    # empty (the short form does not need it; the full form with an empty index gets
    # WARNING below). There is no distribution at all - there is nothing to write.
    if not (channels["plugins"] or channels["manifests"]):
        out("ERROR: no skill distribution found in project swissknifeman\n"
            "  (no enabledPlugins in .claude/settings*.json and no "
            f"{MANIFEST}) — first connect-claude.sh or install.sh",
            file=sys.stderr)
        raise SystemExit(1)

    agents, unknown_skills = collect_agents(
        target, {s["name"] for s in registry["skills"]})
    reg_sha = hashlib.sha256(
        (Path(env.root) / "skills.json").read_bytes()).hexdigest()[:12]

    boost_mode = (target / "boost.json").exists()
    names = installed_names(installed)
    targets = ([str(BOOST_TARGET)] if boost_mode
               else [CLAUDE_TARGET] + [f for f in root_files if f != CLAUDE_TARGET])
    forms = {name: target_form(name, boost_mode=boost_mode, full_index=full_index,
                               legacy_short=legacy_short)
             for name in targets}

    if not names and channels["plugins"]:
        out("WARNING: index empty: enabled plugins ("
            + ", ".join(channels["plugins"]) + ") do not expand into buckets "
            "registry - their skills are listed only by the native client listing",
            file=sys.stderr)

    check = None
    if any(form == FORM_SHORT and name != "AGENTS.md" for name, form in forms.items()) and names:
        check = native_check(env, target, names)
        for note in check["notes"]:
            out(f"WARNING: verification of the native set: {note}", file=sys.stderr)
        out(f"Reconciliation before reduction: confirmed {len(check['confirmed'])} "
            f"from {len(names)} (meter set: {check['measurer_detail']})")
        if check["unconfirmed"]:
            out(f"Not confirmed by native set ({len(check['unconfirmed'])}), "
                "remain listed: " + ", ".join(check["unconfirmed"]))
    unconfirmed = check["unconfirmed"] if check else sorted(names)

    codex_check = None
    codex_installed = installed
    if forms.get("AGENTS.md") == FORM_SHORT:
        from aicore.delivery.codex import native_inventory
        codex_check = native_inventory(env, target)
        codex_installed = _codex_installed(env, target, registry, installed, channels, codex_check)
        for note in codex_check["notes"]:
            out(f"WARNING: {note}; AGENTS.md saves unverified skills", file=sys.stderr)

    rendered = {}
    for name, form in forms.items():
        remaining = (sorted(installed_names(codex_installed) - codex_check["names"])
                     if name == "AGENTS.md" and codex_check is not None else unconfirmed)
        rendered[name] = build_hub_markdown(
            installed=codex_installed if name == "AGENTS.md" else installed,
            buckets_meta=buckets_meta, agents=agents,
            unknown_skills=unknown_skills, reg_sha=reg_sha,
            reg_count=len(registry["skills"]), boost_mode=boost_mode, form=form,
            unconfirmed=remaining)
        if form == FORM_FULL and not names:
            out(f"WARNING: {name}: full form with an empty index - channel without "
                "of the native listing remains undetected", file=sys.stderr)

    written = []
    for name, hub_md in rendered.items():
        out_path = target / name
        if boost_mode:
            if dry_run:
                out(f"[dry-run] would write {out_path} "
                    f"({len(hub_md.splitlines())} lines)")
                out(hub_md)
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(hub_md, encoding="utf-8")
                out(f"Hub recorded: {out_path}")
                out("Detected Laravel Boost: do `php artisan boost:update`, "
                    "so that the fragment gets into CLAUDE.md/AGENTS.md.")
        else:
            block = f"{HUB_START}\n{hub_md}{HUB_END}\n"
            new_text = upsert_block(out_path, block)
            if dry_run:
                out(f"[dry-run] would update managed-block in {out_path} "
                    f"(form: {forms[name]}, {len(hub_md.splitlines())} lines)")
                out(block)
            else:
                out_path.write_text(new_text, encoding="utf-8")
                out(f"Hub recorded: {out_path} (form: {forms[name]}, managed-block "
                    "between markers swissknifeman:hub)")
        written.append(name)

    total = len(names)
    out(f"Skills in the index: {total}, buckets: {len(installed)}")
    out("Goal forms: " + ", ".join(f"{n}={forms[n]}" for n in targets))
    if agents:
        out(f"Agents indexed: {len(agents)}")
    if unknown_skills:
        out("WARNING: skills: for agents were not found in the registry (preload no-op): "
            + ", ".join(sorted(unknown_skills)), file=sys.stderr)
    return {"forms": forms, "written": written, "rendered": rendered,
            "installed": installed, "check": check, "codex_check": codex_check, "channels": channels}


USAGE = """generate-hub.sh — root «hub» skills in the project.

  --target <dir>        target project (required)
  --dry-run             do not write anything, show block
  --root-files A,B      additional root files (AGENTS.md,GEMINI.md)
  --full-index          full form (with index) ALL targets - rollback path
  --hub-legacy-short    short form with priorities (to stub default)
"""


def main(argv=None):
    """argv: [repo_root, *args] — like `python3 -m skiller`."""
    from .common import Env
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(USAGE, file=sys.stderr)
        return 2
    root, args = argv[0], argv[1:]
    target, dry_run, root_files, full_index, legacy_short = "", False, [], False, False
    while args:
        arg = args.pop(0)
        if arg == "--target" and args:
            target = args.pop(0)
        elif arg == "--dry-run":
            dry_run = True
        elif arg == "--full-index":
            full_index = True
        elif arg == "--hub-legacy-short":
            legacy_short = True
        elif arg == "--root-files" and args:
            root_files = [f.strip() for f in args.pop(0).split(",") if f.strip()]
        elif arg in ("-h", "--help"):
            print(USAGE)
            return 0
        else:
            print(f"Unknown argument: {arg}", file=sys.stderr)
            print(USAGE, file=sys.stderr)
            return 1
    if not target:
        print("Error: --target required", file=sys.stderr)
        return 1
    if not Path(os.path.expanduser(target)).is_dir():
        print(f"Error: directory not found: {target}", file=sys.stderr)
        return 1
    run(Env(root, "generate-hub"), target, dry_run=dry_run,
        root_files=root_files, full_index=full_index, legacy_short=legacy_short)
    return 0


if __name__ == "__main__":
    sys.exit(main())
