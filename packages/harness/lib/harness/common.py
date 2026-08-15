"""Internal documentation."""
from dataclasses import dataclass

from core import (  # noqa: F401
    HOME, BaseEnv, atomic_write_text, backup_file, confirm, die,
    find_monorepo_root, now_iso, parse_args, parse_flags, run_cmd,
    safe_load_json, sanitize, warn,
)


@dataclass(frozen=True)
class Env(BaseEnv):
    """Internal documentation."""

    @property
    def configs_dir(self):
        """Internal documentation."""
        return self.root / "configs" / "claude-code"

    @property
    def mcp_dir(self):
        return self.configs_dir / "mcp"

    @property
    def agent_packs_dir(self):
        """Internal documentation."""
        return self.configs_dir / "agent-packs"

    @property
    def apply_script(self):
        return self.root / "scripts" / "apply-permissions.sh"
