"""``python3 -m aicore``: the command line of the foundation."""
import sys

from .config.cli import main

sys.exit(main())
