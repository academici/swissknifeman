#!/usr/bin/env python3
"""A fake command source: the query comes on stdin, a JSON object goes to stdout."""
import json
import sys

query = sys.stdin.read().strip()
json.dump({"text": f"command answer: {query}", "sources": ["https://example.org/c"]}, sys.stdout)
