"""Command Manager analyst. Entry point: main(argv) → cmd_*(env, args).

COMMANDS maps the command name to the handler cmd_*(env, argv). Handlers live
in modules by domain (digest/review/promote/...). The environment is built from argv
([repo_root, cmd, *args], which transmits bin/analyst) and is forwarded explicitly."""
import sys

from .common import Env
from .capture import cmd_capture, cmd_migrate
from .digest import cmd_digest
from .doctor import cmd_doctor
from .ecosystem_events import cmd_events
from .ingest import cmd_ingest
from .promote import cmd_deprecate, cmd_promote
from .proposals import cmd_proposals
from .recompute import cmd_recompute
from .review import cmd_review
from .runs_cli import cmd_runs
from .scan import cmd_scan
from .sessions import cmd_sessions
from .status import cmd_compact, cmd_status
from .suggest import cmd_suggest
from .token_report import cmd_token_report
from .workflow_scan import cmd_workflow_scan

COMMANDS = {
    "digest": cmd_digest,
    "capture": cmd_capture,
    "migrate": cmd_migrate,
    "ingest": cmd_ingest,
    "scan": cmd_scan,
    "suggest": cmd_suggest,
    "proposals": cmd_proposals,
    "review": cmd_review,
    "recompute": cmd_recompute,
    "promote": cmd_promote,
    "deprecate": cmd_deprecate,
    "status": cmd_status,
    "compact": cmd_compact,
    "token-report": cmd_token_report,
    "runs": cmd_runs,
    "sessions": cmd_sessions,
    "doctor": cmd_doctor,
    "events": cmd_events,
    "workflow-scan": cmd_workflow_scan,
}


def main(argv=None):
    """argv: [repo_root, cmd, *args]. bin/analyst transmits root and the command explicitly -
    tests call main([...]) without substitution argv process."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("usage: python3 -m analyst <repo_root> <command> [args...]",
              file=sys.stderr)
        sys.exit(2)
    root, cmd, args = argv[0], argv[1], argv[2:]
    env = Env(root, cmd)
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
    handler(env, args)
