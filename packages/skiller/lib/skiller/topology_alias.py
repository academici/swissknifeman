"""topology — alias of `maind topology` (the machine topology map moved to maind)."""
import subprocess
import sys

from aicore.util.partners import PartnerUnavailable, require_partner
from aicore.util.term import warn


def cmd_topology(env, argv):
    warn("SKILLER_TOPOLOGY_MOVED: skiller topology moved to maind topology")
    try:
        command = require_partner("maind")
    except PartnerUnavailable as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(3)
    sys.exit(subprocess.run(command + ["topology", *argv]).returncode)  # no-timeout: passes the maind topology command through; its duration is the user's
