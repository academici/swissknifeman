"""maind tests run against temporary homes only: the variables that move the aicore.state places
or add configuration layers must not leak in from the developer's shell."""
import os

for _name in ("SKM_HOME", "XDG_CONFIG_HOME", "XDG_STATE_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME",
              "SKM_UNITS_PATH"):
    os.environ.pop(_name, None)
for _name in [n for n in os.environ if n.startswith("SKM_MAIND_") and n != "SKM_MAIND_ROOT"]:
    os.environ.pop(_name, None)

# No test depends on a harness found on PATH: every process starts from a fake that answers
# harness's public JSON commands from recorded fixtures (see tests/harness_partner.py).
from tests import harness_partner as _harness_partner  # noqa: E402

_harness_partner.install_default()
