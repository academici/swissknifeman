"""Fixture helpers intentionally keep process payloads independent of compiler logic."""
from __future__ import annotations

import copy
import json
from pathlib import Path


FIXTURE_PLAN = Path(__file__).resolve().parent / "fixtures_data" / "plan"


def load_json(path):
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def clone(value):
    return copy.deepcopy(value)


def p2_1_pending_s3_fixture():
    """Independent expected Harness source for compiler conformance tests."""
    return {
        "degraded": False,
        "items": [{
            "item_id": "P2.1",
            "status": "⬜ Not started",
            "route": {"model_class": "implementation", "effort": "high"},
            "route_error": None,
            "exec": "run",
            "exec_error": None,
            "drivable": True,
            "refusal": None,
            "refusal_detail": None,
            "argv": None,
            "argv_error": None,
        }],
        "excluded_terminal": [],
    }
