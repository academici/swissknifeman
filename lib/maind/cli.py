"""Диспетчер команд maind. Точка входа: main(argv) → cmd_*(env, args).

COMMANDS отображает имя команды на обработчик cmd_*(env, argv). Обработчики
живут в модулях по доменам (memory/graph/agents/...). Окружение строится из
argv ([repo_root, cmd, *args], которые передаёт bin/maind) и пробрасывается явно."""
import sys

from .agents import cmd_agents
from .common import Env
from .deploy import cmd_deploy
from .doctor import cmd_doctor
from .graph import cmd_graph
from .health import cmd_health
from .mcp import cmd_mcp
from .memory import cmd_memory
from .migrate import cmd_migrate
from .onboard import cmd_onboard
from .orchestrate import cmd_run
from .projects import cmd_projects
from .start import cmd_start, cmd_status
from .sync import cmd_sync
from .workspace import cmd_workspace

COMMANDS = {
    "start": cmd_start,
    "status": cmd_status,
    "memory": cmd_memory,
    "graph": cmd_graph,
    "agents": cmd_agents,
    "projects": cmd_projects,
    "deploy": cmd_deploy,
    "sync": cmd_sync,
    "health": cmd_health,
    "workspace": cmd_workspace,
    "run": cmd_run,
    "onboard": cmd_onboard,
    "migrate": cmd_migrate,
    "mcp": cmd_mcp,
    "doctor": cmd_doctor,
}


def main(argv=None):
    """argv: [repo_root, cmd, *args]. bin/maind передаёт root и команду явно —
    тесты вызывают main([...]) без подмены argv процесса."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("usage: python3 -m maind <repo_root> <command> [args...]",
              file=sys.stderr)
        sys.exit(2)
    root, cmd, args = argv[0], argv[1], argv[2:]
    env = Env(root, cmd)
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"Неизвестная команда: {cmd}", file=sys.stderr)
        sys.exit(1)
    handler(env, args)
