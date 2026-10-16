"""Provider-specific runtime artifacts used by generated projections."""
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
