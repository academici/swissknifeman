"""Диспетчер команд. Точка входа: main(argv) -> вызывает cmd_*(env, args)."""
import sys

from .common import Env
from .connect import cmd_connect
from .doctor import cmd_doctor
from .listing import cmd_list
from .registry import cmd_registry
from .status import cmd_status
from .topology import cmd_topology
from .update import cmd_update
from .vendor import cmd_vendor

COMMANDS = {
    "connect": cmd_connect,
    "vendor": cmd_vendor,
    "update": cmd_update,
    "status": cmd_status,
    "list": cmd_list,
    "registry": cmd_registry,
    "doctor": cmd_doctor,
    "topology": cmd_topology,
}


def main(argv=None):
    """argv: [repo_root, cmd, *args]. Раньше эти значения брались из sys.argv
    в heredoc; теперь main принимает их явно — тесты гоняют команды без
    подмены argv процесса."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("usage: python3 -m swissknifeman <repo_root> <command> [args...]",
              file=sys.stderr)
        sys.exit(2)
    root, cmd, args = argv[0], argv[1], argv[2:]
    env = Env(root, cmd)
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"Неизвестная команда: {cmd}", file=sys.stderr)
        sys.exit(1)
    handler(env, args)
