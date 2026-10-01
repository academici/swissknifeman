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
            "exec": "manual",
            "exec_error": None,
            "drivable": False,
            "refusal": "EXEC-NOT-PLAN-EXEC",
            "refusal_detail": "fixture: manual item is intentionally not plan-exec drivable",
            "argv": None,
            "argv_error": None,
        }],
        "excluded_terminal": [],
    }
