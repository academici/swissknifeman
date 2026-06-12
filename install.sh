#!/usr/bin/env bash
# Context-aware installer for swissknifeman skills.
#
# New mode:    ./install.sh [options]
# Legacy mode: ./install.sh [target_dir] [bucket]   (deprecated)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<'EOF'
Usage: ./install.sh [options]
       ./install.sh [target_dir] [bucket]   (legacy, deprecated)

Options:
  --target DIR      Project root or install root (default: ~)
  --agent NAME      claude | cursor | generic (default: generic)
                    claude flattens skills into <skills-path>/<name>/SKILL.md
                    (Claude Code only discovers flat skill dirs)
  --profile NAME    obsidian-vault | laravel-project | php-package | standalone
                    (default: autodetect from target, see below)
  --buckets a,b,c   Explicit bucket list (overrides profile)
  --exclude x,y     Skill names, dir names or bucket-relative paths to skip
  --skills-path P   Skills destination relative to target
                    (default per agent: claude=.claude/skills,
                     cursor=.cursor/skills, generic=.ai/skills)
  --list            Print resolved profile + skill list, install nothing
  --dry-run         Print every copy action, write nothing
  --force           Overwrite existing skill dirs not installed by swissknifeman
                    (bucket layout only; default: abort on collision)
  --hub             After install, generate the root skills hub in the target
                    (scripts/generate-hub.sh: CLAUDE.md managed block, or
                     .ai/guidelines/swissknifeman-hub.md when Laravel Boost detected)
  -h, --help        Show help

Resolution precedence: flags > .swissknife.json (in target) > autodetect.
Autodetect: .obsidian/ -> obsidian-vault; artisan+composer.json -> laravel-project;
composer.json -> php-package; otherwise standalone.

Legacy mode: copies skills/<bucket> verbatim into target_dir (bucket layout).
EOF
}

# --- legacy mode -------------------------------------------------------------
legacy_install() {
  local target="${1:-${HOME}/.ai/skills}"
  local bucket="${2:-all}"
  echo "NOTE: legacy mode (deprecated) — use ./install.sh --target ... instead"
  mkdir -p "$target"
  if [[ "$bucket" == "all" ]]; then
    for dir in "$REPO_ROOT"/skills/*/; do
      echo "Installing bucket: $(basename "$dir")"
      cp -r "$dir" "$target/"
    done
    [[ -d "$REPO_ROOT/generate-skill/generate-skill" ]] && \
      cp -r "$REPO_ROOT/generate-skill/generate-skill" "$target/../generate-skill" 2>/dev/null || true
  else
    [[ -d "$REPO_ROOT/skills/$bucket" ]] || { echo "Unknown bucket: $bucket"; exit 1; }
    echo "Installing bucket: $bucket"
    cp -r "$REPO_ROOT/skills/$bucket" "$target/"
  fi
  echo "Installed to $target"
  exit 0
}

if [[ $# -eq 0 ]]; then
  legacy_install
fi
if [[ "$1" != -* ]]; then
  legacy_install "$@"
fi

# --- new mode: parse flags -----------------------------------------------------
TARGET="$HOME"
AGENT=""
PROFILE=""
BUCKETS=""
EXCLUDE=""
SKILLS_PATH=""
LIST=false
DRY_RUN=false
FORCE=false
HUB=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) TARGET="$2"; shift 2 ;;
    --agent) AGENT="$2"; shift 2 ;;
    --profile) PROFILE="$2"; shift 2 ;;
    --buckets) BUCKETS="$2"; shift 2 ;;
    --exclude) EXCLUDE="$2"; shift 2 ;;
    --skills-path) SKILLS_PATH="$2"; shift 2 ;;
    --list) LIST=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --force) FORCE=true; shift ;;
    --hub) HUB=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 1 ;;
  esac
done

export SKM_TARGET="$TARGET" SKM_AGENT="$AGENT" SKM_PROFILE="$PROFILE" \
       SKM_BUCKETS="$BUCKETS" SKM_EXCLUDE="$EXCLUDE" SKM_SKILLS_PATH="$SKILLS_PATH" \
       SKM_LIST="$LIST" SKM_DRY_RUN="$DRY_RUN" SKM_FORCE="$FORCE"

python3 - "$REPO_ROOT" <<'PY'
import json, os, re, shutil, sys
from datetime import date
from pathlib import Path

root = Path(sys.argv[1])
target = Path(os.path.expanduser(os.environ["SKM_TARGET"])).resolve()
flag_agent = os.environ["SKM_AGENT"]
flag_profile = os.environ["SKM_PROFILE"]
flag_buckets = [b for b in os.environ["SKM_BUCKETS"].split(",") if b]
flag_exclude = [e for e in os.environ["SKM_EXCLUDE"].split(",") if e]
flag_skills_path = os.environ["SKM_SKILLS_PATH"]
list_only = os.environ["SKM_LIST"] == "true"
dry_run = os.environ["SKM_DRY_RUN"] == "true"
force = os.environ["SKM_FORCE"] == "true"

AGENT_DEFAULTS = {"claude": ".claude/skills", "cursor": ".cursor/skills",
                  "generic": ".ai/skills"}
MANIFEST = ".swissknifeman-manifest.json"


def die(msg):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def parse_frontmatter_name(skill_md):
    lines = skill_md.read_text(encoding="utf-8").replace("\r\n", "\n").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip().strip('"').strip("'")
    return ""


# --- 1. project config + autodetect -----------------------------------------
CONFIG_KEYS = {
    "project_type": str, "buckets": list, "exclude": list,
    "skills_path": str, "agent": str,
}


def validate_config(config, cfg_file, profiles_dir):
    """Schema check for .swissknife.json; keys starting with _ are comments."""
    import difflib
    profile_names = sorted(p.stem for p in profiles_dir.glob("*.json"))
    for key, value in config.items():
        if key.startswith("_"):
            continue
        if key not in CONFIG_KEYS:
            hint = difflib.get_close_matches(key, CONFIG_KEYS, n=1)
            suffix = f" — did you mean '{hint[0]}'?" if hint else ""
            die(f"{cfg_file}: unknown key '{key}'{suffix}")
        if not isinstance(value, CONFIG_KEYS[key]):
            die(f"{cfg_file}: '{key}' must be a "
                f"{'list of strings' if CONFIG_KEYS[key] is list else 'string'}")
        if CONFIG_KEYS[key] is list and not all(isinstance(v, str) for v in value):
            die(f"{cfg_file}: '{key}' must be a list of strings")
    if config.get("project_type") and config["project_type"] not in profile_names:
        die(f"{cfg_file}: unknown project_type '{config['project_type']}' "
            f"(available: {', '.join(profile_names)})")
    if config.get("agent") and config["agent"] not in AGENT_DEFAULTS:
        die(f"{cfg_file}: unknown agent '{config['agent']}' "
            f"(available: {', '.join(AGENT_DEFAULTS)})")


config = {}
cfg_file = target / ".swissknife.json"
if cfg_file.exists():
    try:
        config = json.loads(cfg_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{cfg_file}: invalid JSON: {e}")
    validate_config(config, cfg_file, root / "profiles")


def autodetect():
    if (target / ".obsidian").is_dir():
        return "obsidian-vault"
    if (target / "artisan").is_file() and (target / "composer.json").is_file():
        return "laravel-project"
    if (target / "composer.json").is_file():
        return "php-package"
    return "standalone"


def load_profile(name):
    f = root / "profiles" / f"{name}.json"
    if not f.exists():
        available = ", ".join(sorted(p.stem for p in (root / "profiles").glob("*.json")))
        die(f"unknown profile '{name}' (available: {available})")
    return json.loads(f.read_text(encoding="utf-8"))


all_buckets = sorted(d.name for d in (root / "skills").iterdir() if d.is_dir())

profile_name = None
include_meta = False
if flag_buckets:
    buckets, source = flag_buckets, "--buckets"
elif flag_profile:
    prof = load_profile(flag_profile)
    profile_name, source = flag_profile, "--profile"
    buckets = all_buckets if prof["buckets"] == ["*"] else prof["buckets"]
    include_meta = prof.get("include_meta", False)
elif config.get("buckets"):
    buckets, source = config["buckets"], ".swissknife.json buckets"
elif config.get("project_type"):
    prof = load_profile(config["project_type"])
    profile_name, source = config["project_type"], ".swissknife.json project_type"
    buckets = all_buckets if prof["buckets"] == ["*"] else prof["buckets"]
    include_meta = prof.get("include_meta", False)
else:
    profile_name, source = autodetect(), "autodetect"
    prof = load_profile(profile_name)
    buckets = all_buckets if prof["buckets"] == ["*"] else prof["buckets"]
    include_meta = prof.get("include_meta", False)

for b in buckets:
    if b not in all_buckets:
        die(f"unknown bucket: {b}")

# exclude = union of flag and config (safety-oriented, not precedence-based)
exclude = set(flag_exclude) | set(config.get("exclude", []))

agent = flag_agent or config.get("agent", "") or "generic"
if agent not in AGENT_DEFAULTS:
    die(f"unknown agent '{agent}' (available: {', '.join(AGENT_DEFAULTS)})")

skills_path = flag_skills_path or config.get("skills_path", "") or AGENT_DEFAULTS[agent]
dest_root = target / skills_path

# --- 2. collect skills (dir directly containing SKILL.md) ---------------------
skills = []  # (bucket, rel_path_under_bucket, dir, fm_name)
all_skill_rels = {}  # bucket -> [rel paths of every skill dir, excluded or not]
for bucket in buckets:
    bucket_dir = root / "skills" / bucket
    for skill_md in sorted(bucket_dir.rglob("SKILL.md")):
        d = skill_md.parent
        rel = d.relative_to(bucket_dir)
        all_skill_rels.setdefault(bucket, []).append(str(rel))
        fm_name = parse_frontmatter_name(skill_md)
        ids = {fm_name, d.name, f"{bucket}/{rel}".replace("\\", "/")}
        if ids & exclude:
            continue
        skills.append((bucket, str(rel), d, fm_name))

if include_meta and (root / "generate-skill/generate-skill/SKILL.md").exists():
    d = root / "generate-skill/generate-skill"
    fm_name = parse_frontmatter_name(d / "SKILL.md")
    if not ({fm_name, "generate-skill"} & exclude):
        skills.append(("generate-skill", ".", d, fm_name))


def sanitize(name):
    name = name.lower().replace(" ", "-").replace("_", "-")
    name = re.sub(r"[^a-z0-9-]", "", name)
    return re.sub(r"-{2,}", "-", name).strip("-")


# --- 3. flat names for claude --------------------------------------------------
def flat_names():
    """Map skill tuple index -> flat dir name, with collision handling."""
    names = {}
    for i, (bucket, rel, d, fm_name) in enumerate(skills):
        base = sanitize(fm_name) or sanitize(rel.replace("/", "-")) or sanitize(d.name)
        names[i] = base
    # collision pass 1: prefix bucket
    seen = {}
    for i, n in names.items():
        seen.setdefault(n, []).append(i)
    for n, idxs in list(seen.items()):
        if len(idxs) > 1:
            for i in idxs:
                bucket = skills[i][0]
                if not names[i].startswith(bucket + "-"):
                    print(f"WARN collision: '{n}' -> '{bucket}-{n}'", file=sys.stderr)
                    names[i] = f"{bucket}-{n}"
    # collision pass 2: full path slug
    seen = {}
    for i, n in names.items():
        seen.setdefault(n, []).append(i)
    for n, idxs in seen.items():
        if len(idxs) > 1:
            for i in idxs:
                bucket, rel = skills[i][0], skills[i][1]
                slug = sanitize(f"{bucket}-{rel.replace('/', '-')}")
                print(f"WARN collision: '{n}' -> '{slug}'", file=sys.stderr)
                names[i] = slug
    return names


# --- 4. report / list ----------------------------------------------------------
print(f"Target:      {target}")
print(f"Profile:     {profile_name or '-'} (via {source})")
print(f"Agent:       {agent}")
print(f"Skills path: {skills_path}")
print(f"Buckets:     {' '.join(buckets)}")
if exclude:
    print(f"Exclude:     {' '.join(sorted(exclude))}")
print(f"Skills:      {len(skills)}")

flats = flat_names() if agent == "claude" else {}
if list_only:
    for i, (bucket, rel, d, fm_name) in enumerate(skills):
        suffix = f" -> {flats[i]}/" if agent == "claude" else ""
        print(f"  {bucket}/{rel}{suffix}")
    sys.exit(0)


# --- 5. install ------------------------------------------------------------------
def copy_skill(src, dst):
    """Copy a skill dir excluding registry/plugin metadata."""
    if dry_run:
        print(f"[dry-run] {src.relative_to(root)} -> {dst}")
        return
    shutil.copytree(src, dst, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("upstream.json", ".claude-plugin"))


def load_manifest(manifest_file):
    if manifest_file.exists():
        return json.loads(manifest_file.read_text(encoding="utf-8"))
    return {}


def contained(path):
    return str(path.resolve()).startswith(str(dest_root.resolve()) + os.sep)


def write_manifest(manifest_file, layout, installed, support_files=None):
    data = {
        "installed_at": date.today().isoformat(),
        "profile": profile_name,
        "agent": agent,
        "layout": layout,
        "skills": installed,
    }
    if support_files is not None:
        data["support_files"] = support_files
    manifest_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                             encoding="utf-8")


if agent == "claude":
    print("NOTE: --agent claude vendoring is deprecated for Claude Code projects — "
          "prefer the plugin marketplace: scripts/connect-claude.sh", file=sys.stderr)
    # flatten: <skills_path>/<flat_name>/SKILL.md
    manifest_file = dest_root / MANIFEST
    if not dry_run:
        for entry in load_manifest(manifest_file).get("skills", []):
            stale = dest_root / entry["flat_name"]
            if stale.is_dir() and contained(stale):
                shutil.rmtree(stale)
        dest_root.mkdir(parents=True, exist_ok=True)
    installed = []
    for i, (bucket, rel, d, fm_name) in enumerate(skills):
        copy_skill(d, dest_root / flats[i])
        installed.append({"flat_name": flats[i],
                          "source_path": str(d.relative_to(root))})
    if not dry_run:
        write_manifest(manifest_file, "flat", installed)
else:
    # bucket layout: manifest-driven clean reinstall, no silent overwrites
    manifest_file = dest_root / MANIFEST
    old = load_manifest(manifest_file)
    old_paths = {e["path"] for e in old.get("skills", [])}

    # collect support files (e.g. skills/oss-dev/references/) for selected buckets
    support = []  # (src, rel "<bucket>/<rel_item>")
    for bucket in buckets:
        bucket_dir = root / "skills" / bucket
        for item in sorted(bucket_dir.rglob("*")):
            if item.is_dir() or item.name in ("SKILL.md", "upstream.json"):
                continue
            rel_item = item.relative_to(bucket_dir)
            if ".claude-plugin" in rel_item.parts:
                continue
            # skip files inside any skill dir (copied already, or excluded)
            if any(str(rel_item).startswith(r + os.sep)
                   for r in all_skill_rels.get(bucket, []) if r != "."):
                continue
            support.append((item, f"{bucket}/{rel_item}"))

    # pre-flight: existing dirs not from a previous install are collisions
    planned = [(bucket, rel, d, f"{bucket}/{rel}" if rel != "." else bucket)
               for bucket, rel, d, fm_name in skills]
    collisions = [p for _, _, _, p in planned
                  if (dest_root / p).exists() and p not in old_paths]
    if collisions and not force:
        for p in collisions:
            print(f"ERROR: exists and was not installed by swissknifeman: "
                  f"{dest_root / p}", file=sys.stderr)
        die(f"{len(collisions)} collision(s) — rerun with --force to overwrite")

    if not dry_run:
        # clean previous install (skills + support files), prune empty dirs
        for p in sorted(old_paths | {e for e in old.get("support_files", [])},
                        reverse=True):
            stale = dest_root / p
            if not contained(stale):
                continue
            if stale.is_dir():
                shutil.rmtree(stale)
            elif stale.is_file():
                stale.unlink()
            parent = stale.parent
            while parent != dest_root and parent.is_dir() and \
                    not any(parent.iterdir()):
                parent.rmdir()
                parent = parent.parent
        dest_root.mkdir(parents=True, exist_ok=True)

    installed = []
    for bucket, rel, d, path in planned:
        copy_skill(d, dest_root / path)
        installed.append({"path": path, "source_path": str(d.relative_to(root))})
    support_rels = []
    for item, rel_path in support:
        dst = dest_root / rel_path
        support_rels.append(rel_path)
        if dry_run:
            print(f"[dry-run] {item.relative_to(root)} -> {dst}")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, dst)
    if not dry_run:
        write_manifest(manifest_file, "bucket", installed, support_rels)

print(("[dry-run] " if dry_run else "") + f"Installed {len(skills)} skills -> {dest_root}")
PY

if [[ "$HUB" == true && "$LIST" == false && "$DRY_RUN" == false ]]; then
  "$REPO_ROOT/scripts/generate-hub.sh" --target "$TARGET"
elif [[ "$LIST" == false && "$DRY_RUN" == false ]]; then
  echo "Hint: generate the root skills hub: $REPO_ROOT/scripts/generate-hub.sh --target $TARGET (or rerun with --hub)"
fi
