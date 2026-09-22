"""Internal documentation."""
import re
from pathlib import Path

from core import parse_frontmatter

from .common import parse_flags
from .settings import write_json


_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "use", "this", "that", "when",
    "и", "в", "во", "на", "по", "для", "с", "со", "от", "до", "из", "как", "что",
    "это", "или", "при", "над", "под", "без", "если",
}


def _keywords_from_description(desc, limit=12):
    toks = re.findall(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9-]{2,}", (desc or "").lower())
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
        if name.startswith(("task-", "task:")):
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
    print(f"router: каталог — {len(commands)} команд, {len(agents)} агентов, "
          f"{len(skills)} локальных скиллов")
