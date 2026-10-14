"""Command manager. Entry point: main(argv) -> calls cmd_*(env, args)."""
import sys

from aicore.config import ConfigError
from aicore.util.term import die

from .budget import cmd_budget
from .common import Env
from .connect import cmd_connect
from .describe import cmd_describe
from .doctor import cmd_doctor
from .quality.analyze import cmd_analyze_run
from .quality.audit import cmd_bucket_audit
from .quality.eval import cmd_eval
from .integrate import cmd_integrate
from .listing import cmd_list
from .profiles_list import cmd_profiles
from .lock import cmd_lock
from .registry import cmd_registry
from .resolve import cmd_resolve
from .selection import cmd_selection
from .release import cmd_release
from .release_attestation import cmd_attest, cmd_version
from .delivery import cmd_deliver
from .skillset import cmd_init, cmd_sync
from .status import cmd_status
from .topology_alias import cmd_topology
from .update import cmd_update
from .vendor import cmd_vendor

COMMANDS = {
    "connect": cmd_connect,
    "vendor": cmd_vendor,
    "integrate": cmd_integrate,
    "update": cmd_update,
    "init": cmd_init,
    "sync": cmd_sync,
    "lock": cmd_lock,
    "status": cmd_status,
    "budget": cmd_budget,
    "bucket-audit": cmd_bucket_audit,
    "analyze-run": cmd_analyze_run,
    "eval": cmd_eval,
    "list": cmd_list,
    "profiles": cmd_profiles,
    "registry": cmd_registry,
    "resolve": cmd_resolve,
    "describe": cmd_describe,
    "selection": cmd_selection,
    "doctor": cmd_doctor,
    "topology": cmd_topology,
    "release": cmd_release,
    "attest": cmd_attest,
    "version": cmd_version,
    "deliver": cmd_deliver,
}


def main(argv=None):
    """argv: [repo_root, cmd, *args]. Previously, these values were taken from sys.argv
    in heredoc; now main accepts them explicitly - tests are run by commands without
    substitutions argv process."""
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2:
        print("usage: python3 -m skiller <repo_root> <command> [args...]",
              file=sys.stderr)
        sys.exit(2)
    root, cmd, args = argv[0], argv[1], argv[2:]
    env = Env(root, cmd)
    handler = COMMANDS.get(cmd)
    if handler is None:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
    try:
        handler(env, args)
    except ConfigError as exc:
        die(str(exc))
