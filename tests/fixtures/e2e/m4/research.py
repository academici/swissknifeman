"""Offline bounded research protocol: empty lower tiers, evidence in higher tiers."""

import json
import sys

json.load(sys.stdin)
tier = sys.argv[1]
documents = (
    []
    if tier in {"local_docs", "codegraph"}
    else [
        {
            "origin": "repo:repo/guide.md",
            "title": tier,
            "text": "M4 research evidence: café 🧪 password=very-secret-value",
        }
    ]
)
print(json.dumps({"documents": documents}))
