"""Echo the JSON object read from stdin."""
import json
import sys

json.dump(json.load(sys.stdin), sys.stdout)
