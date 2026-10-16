"""Answer with the names of the environment variables the process sees."""
import json
import os
import sys

json.dump({"names": sorted(os.environ)}, sys.stdout)
