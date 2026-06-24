"""Диспетчер команд harness. Точка входа: main(argv) → cmd_*(env, args).

COMMANDS отображает имя команды на обработчик cmd_*(env, argv). Окружение
строится из argv ([repo_root, cmd, *args], которые передаёт bin/harness) и
пробрасывается явно (тестируемо в tmpdir)."""
import sys

from .agentpacks import cmd_agent_packs
from .common import Env
from .doctor import cmd_doctor
from .hooks import cmd_hooks
from .mcp import cmd_mcp
from .permissions import cmd_permissions

COMMANDS = {
    "permissions": cmd_permissions,
    "apply": cmd_permissions,  # alias
    "mcp": cmd_mcp,
    "hooks": cmd_hooks,
    "agent-packs": cmd_agent_packs,
    "doctor": cmd_doctor,
}


def main(argv=None):
    """argv: [repo_root, cmd, *args]. bin/harness передаёт root и команду явно —
    тесты вызывают main([...]) без подмены argv процесса."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("usage: python3 -m harness <repo_root> <command> [args...]",
              file=sys.stderr)
        sys.exit(2)
    root, cmd, args = argv[0], argv[1], argv[2:]
    env = Env(root, cmd)
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"Неизвестная команда: {cmd}", file=sys.stderr)
        sys.exit(1)
    handler(env, args)
