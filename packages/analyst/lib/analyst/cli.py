"""Диспетчер команд analyst. Точка входа: main(argv) → cmd_*(env, args).

COMMANDS отображает имя команды на обработчик cmd_*(env, argv). Обработчики живут
в модулях по доменам (digest/review/promote/...). Окружение строится из argv
([repo_root, cmd, *args], которые передаёт bin/analyst) и пробрасывается явно."""
import sys

from .common import Env
from .digest import cmd_digest
from .doctor import cmd_doctor
from .promote import cmd_deprecate, cmd_promote
from .recompute import cmd_recompute
from .review import cmd_review
from .scan import cmd_scan
from .status import cmd_compact, cmd_status
from .suggest import cmd_suggest

COMMANDS = {
    "digest": cmd_digest,
    "scan": cmd_scan,
    "suggest": cmd_suggest,
    "review": cmd_review,
    "recompute": cmd_recompute,
    "promote": cmd_promote,
    "deprecate": cmd_deprecate,
    "status": cmd_status,
    "compact": cmd_compact,
    "doctor": cmd_doctor,
}


def main(argv=None):
    """argv: [repo_root, cmd, *args]. bin/analyst передаёт root и команду явно —
    тесты вызывают main([...]) без подмены argv процесса."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("usage: python3 -m analyst <repo_root> <command> [args...]",
              file=sys.stderr)
        sys.exit(2)
    root, cmd, args = argv[0], argv[1], argv[2:]
    env = Env(root, cmd)
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"Неизвестная команда: {cmd}", file=sys.stderr)
        sys.exit(1)
    handler(env, args)
