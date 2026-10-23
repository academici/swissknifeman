"""Paths a provider refuses to write in a session where nobody can approve the write.

Known before a role starts, so the executor is told at the start of its round instead of meeting the refusal at its
end; the conductor says them once per piece as the beacon ``WRITE_PROTECTED_PATH``."""
from __future__ import annotations

# Claude Code 2.1.309, measured 2026-10-23 with the executor flags (--permission-mode acceptEdits,
# --permission-prompts none): Write and Edit of these names are refused at any depth of the tree. A name that ends in
# "/" is a folder: everything under it. Written as usual: CLAUDE.md, .claude-plugin/, .github/, pyproject.toml and the
# other tool configurations. Repeat the measurement and update the list when the CLI changes.
CLAUDE_CODE = (".bashrc", ".claude.json", ".env", ".envrc", ".gitmodules", ".mcp.json", ".npmrc",
               ".pre-commit-config.yaml", ".profile", "pyrightconfig.json",
               ".claude/", ".devcontainer/", ".git/", ".husky/", ".idea/", ".vscode/")
PROTECTED = {"claude-code": CLAUDE_CODE}
NO_PROMPT = "--permission-prompts"  # the flag of a session without an approval surface


def protected(provider: str, argv, patterns) -> list:
    """The write-set ``patterns`` that name a path ``provider`` refuses to write when its ``argv`` runs without prompts."""
    names = PROTECTED.get(provider)
    if not names or NO_PROMPT not in (argv or []):
        return []
    return sorted({pattern for pattern in patterns or [] if isinstance(pattern, str) and named(pattern, names)})


def named(pattern: str, names) -> bool:
    """Whether a write-set ``pattern`` names one of ``names``: its last part is a protected file, or one of its parts a
    protected folder (``.claude/skills/**``, ``packages/x/.vscode/settings.json``)."""
    parts = [part for part in pattern.split("/") if part and part != "."]
    if not parts:
        return False
    folders = {name[:-1] for name in names if name.endswith("/")}
    files = {name for name in names if not name.endswith("/")}
    return parts[-1] in files or any(part in folders for part in parts)
