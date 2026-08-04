"""Fixture helpers intentionally keep process payloads independent of compiler logic."""
from __future__ import annotations

import copy
import json


def load_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def clone(value):
    return copy.deepcopy(value)
