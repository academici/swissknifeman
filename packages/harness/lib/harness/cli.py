"""Internal documentation."""
import sys

from .agentpacks import cmd_agent_packs
from .common import Env
from .doctor import cmd_doctor
from .hooks import cmd_hooks
from .instructions import cmd_instructions
from .mcp import cmd_mcp
from .permissions import cmd_permissions
from .router import cmd_router
from .run import cmd_run
from .safedirs import cmd_safedirs
from .wf_status import cmd_wf

COMMANDS = {
    "permissions": cmd_permissions,
    "apply": cmd_permissions,  # alias
    "mcp": cmd_mcp,
    "hooks": cmd_hooks,
    "router": cmd_router,
    "agent-packs": cmd_agent_packs,
    "safe-dirs": cmd_safedirs,
    "instructions": cmd_instructions,
    "doctor": cmd_doctor,
    "wf": cmd_wf,
    "run": cmd_run,
}


def main(argv=None):
    """Internal documentation."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("usage: python3 -m harness <repo_root> <command> [args...]",
              file=sys.stderr)
        sys.exit(2)
    root, cmd, args = argv[0], argv[1], argv[2:]
    env = Env(root, cmd)
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
    handler(env, args)
