"""Answer with a document that contains the secret in argv[1]."""
import json
import sys

json.dump({"note": "got " + sys.argv[1], "list": [sys.argv[1]]}, sys.stdout)
