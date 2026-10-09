"""Provider-specific runtime locators used by generated projections."""
from __future__ import annotations

import json
from pathlib import Path


def codex_migrated_command_skill(source: Path, relative_path: str) -> bytes | None:
    """Render only Codex's known, source-bound command migration artifact.

    A recognized namespace alone never proves ownership: consumers compare these exact
    bytes with the extra file, while retaining their comparison of all managed files.
    """
    parts = Path(relative_path).parts
    if len(parts) != 4 or parts[:2] != (".codex-plugin", "migrated-command-skills"):
        return None
    name = parts[2]
    if not name.startswith("source-command-") or parts[3] != "SKILL.md":
        return None
    command = name.removeprefix("source-command-")
    canonical = source / "commands" / f"{command}.md"
    if not canonical.is_file():
        return None
    lines = canonical.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        return None
    closing = lines.index("---", 1)
    description = next((line.split(":", 1)[1].strip() for line in lines[1:closing]
                        if line.startswith("description:")), None)
    if not description:
        return None
    body = "\n".join(lines[closing + 1:]).strip()
    return (f'---\nname: {json.dumps(name)}\ndescription: {description}\n---\n\n'
            f'# {name}\n\nUse this skill when the user asks to run the migrated source '
            f'command `{command}`.\n\n## Command Template\n\n{body}\n').encode("utf-8")


def codex_task_plugin_root_expression() -> str:
    """Return the shared planner runtime from the configured SKM marketplace.

    Codex's marketplace cache deliberately contains only declared skills, not
    the planner Python runtime.  Project-selected skills therefore link to the
    canonical marketplace checkout; this locator discovers that single shared
    checkout and never falls back to a consumer-local `packages/planner` copy.
    """
    return (
        "$(codex plugin marketplace list --json | python3 -c "
        "'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item[\"root\"] "
        "for item in data.get(\"marketplaces\", []) if item.get(\"name\")==\"swissknifeman\" "
        "and (pathlib.Path(item[\"root\"])/\"packages/planner/lib/planner\").is_dir()]; "
        "len(roots)==1 or sys.exit(\"planner runtime unavailable: expected one marketplace "
        "root with packages/planner/lib/planner\"); print(roots[0]+\"/packages/planner\")')"
    )
