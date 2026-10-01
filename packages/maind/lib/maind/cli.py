"""Command Manager maind. Entry point: main(argv) → cmd_*(env, args).

COMMANDS maps the command name to the handler cmd_*(env, argv). Handlers
live in modules by domain (memory/graph/agents/...). The environment is built from
argv ([repo_root, cmd, *args], which transmits bin/maind) and is forwarded explicitly."""
import sys

from .agents import cmd_agents
from .analysis.analyze import cmd_analyze
from .common import Env
from .provision.deploy import cmd_deploy
from .doctor import cmd_doctor
from .analysis.fleet import cmd_fleet
from .graph import cmd_graph
from .health import cmd_health
from .mcp import cmd_mcp
from .memory import cmd_memory
from .provision.migrate import cmd_migrate
from .provision.onboard import cmd_onboard
from .provision.orchestrate import cmd_run
from .projects import cmd_namespaces, cmd_projects
from .provision.service import cmd_service
from .provision.start import cmd_start, cmd_status
from .provision.sync import cmd_sync
from .verify import cmd_verify
from .provision.workspace import cmd_workspace

COMMANDS = {
    "start": cmd_start,
    "status": cmd_status,
    "memory": cmd_memory,
    "service": cmd_service,
    "graph": cmd_graph,
    "agents": cmd_agents,
    "projects": cmd_projects,
    "namespaces": cmd_namespaces,
    "deploy": cmd_deploy,
    "sync": cmd_sync,
    "health": cmd_health,
    "workspace": cmd_workspace,
    "run": cmd_run,
    "fleet": cmd_fleet,
    "onboard": cmd_onboard,
    "migrate": cmd_migrate,
    "mcp": cmd_mcp,
    "doctor": cmd_doctor,
    "verify": cmd_verify,
    "analyze": cmd_analyze,
}


def main(argv=None):
    """argv: [repo_root, cmd, *args]. bin/maind transmits root and the command explicitly -
    tests call main([...]) without substitution argv process."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("usage: python3 -m maind <repo_root> <command> [args...]",
              file=sys.stderr)
        sys.exit(2)
    root, cmd, args = argv[0], argv[1], argv[2:]
    env = Env(root, cmd)
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
    handler(env, args)
