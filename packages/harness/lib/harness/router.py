"""Internal documentation."""
import re
from pathlib import Path

from aicore.util.text import parse_frontmatter

from aicore.util.cli import parse_flags
from .settings import write_json


_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "use", "this", "that", "when",
    "and", "in", "in", "on", "by", "for", "with", "with", "from", "to", "from", "like", "what",
    "this", "or", "when", "over", "under", "without", "if",
}


def _keywords_from_description(desc, limit=12):
    toks = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", (desc or "").lower())
    seen, out = set(), []
    for t in toks:
        if t in _STOPWORDS or t in seen:
            continue
        seen.add(t)
        out.append(t)
        if len(out) >= limit:
            break
    return out


def _frontmatter(path):
    """Internal documentation."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    return parse_frontmatter(text)


def _scan_agents(claude_dir):
    out = []
    for f in sorted((claude_dir / "agents").glob("*.md")):
        fm = _frontmatter(f)
        name = fm.get("name")
        if not name:
            continue
        out.append({"name": f"@{name}", "weight": 1,
                    "keywords": _keywords_from_description(fm.get("description", ""))})
    return out


def _scan_local_skills(claude_dir):
    """Internal documentation."""
    out = []
    for d in sorted((claude_dir / "skills").glob("*")):
        f = d / "SKILL.md"
        if not f.is_file():
            continue
        fm = _frontmatter(f)
        name = fm.get("name") or d.name
        # Compatibility alias: remove in the next minor release (the `task-`/`task:` spellings).
        if name.startswith(("planner-", "planner:", "task-", "task:")):
            continue
        out.append({"name": f"skill:{name}", "weight": 1,
                    "keywords": _keywords_from_description(fm.get("description", ""))})
    return out


def cmd_router(env, argv):
    opts = parse_flags(argv, {
        "--target": "str", "--generate": "bool", "--dry-run": "bool",
    })
    if opts["help"] or not opts["target"]:
        print("harness router --generate --target P [--dry-run]")
        return
    target = Path(opts["target"]).expanduser()
    claude = target / ".claude"
    commands = []
    agents = _scan_agents(claude)
    skills = _scan_local_skills(claude)
    catalog = {
        "version": 1,
        "hint_template": "[intent-router] bias (non-authoritative): "
                         "top={name} score={score}{runners}",
        "commands": commands,
        "agents": agents,
        "skills": skills,
    }
    write_json(claude / "agent-router.config.json", catalog, opts["dry_run"])
    print(f"router: directory - {len(commands)} commands, {len(agents)} agents, "
          f"{len(skills)} local skills")
