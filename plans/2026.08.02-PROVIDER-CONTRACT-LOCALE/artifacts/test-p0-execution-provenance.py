#!/usr/bin/env python3
"""Adversarial checks for the P0.8 forward-provenance ledger."""
from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SOURCE = Path(__file__).with_name("p0-execution-provenance.py")
spec = importlib.util.spec_from_file_location("p0_execution_provenance", SOURCE)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


def rejected(mutator) -> None:
    ledger = module.build_ledger(ROOT)
    mutator(ledger)
    try:
        module.validate_ledger(ROOT, ledger)
    except module.ProvenanceError:
        return
    raise AssertionError("mutation unexpectedly accepted")


def main() -> int:
    ledger = module.build_ledger(ROOT)
    module.validate_ledger(ROOT, ledger)
    rejected(lambda value: value["items"][0].__setitem__("item_commit", "0" * 40))
    rejected(lambda value: value["items"][1]["historical_executor_route"].__setitem__("effort", "medium"))
    rejected(lambda value: value["items"][2]["contract_codes"].__setitem__("pre_final", "block:ROUTE_UNDERSHOOT"))
    rejected(lambda value: value["items"][3]["changed_paths"].pop())
    rejected(lambda value: value["items"][0]["validations"][0].__setitem__("anchor", "0" * 40))
    assert module.correction_note(ledger["items"][0]).startswith(module.WRITE_SITE)
    projection = module.compact_projection(ROOT)
    assert projection == module.COMPACT_PROJECTION
    mutated_projection = dict(projection)
    mutated_projection["classification_rows"] -= 1
    assert mutated_projection != module.COMPACT_PROJECTION
    old_digest, new_digest = module.p0_6_declaration_digests(ROOT)
    assert old_digest != new_digest
    with tempfile.TemporaryDirectory() as temp:
        plan = Path(temp)
        (plan / "journal.jsonl").write_text(json.dumps({"item_id": "P0.1", "attempt": 1}) + "\n")
        events = module.correction_events(plan, ledger, "gpt-5.6-sol/high", "test")
        assert len(events) == 4
        (plan / "journal.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n")
        try:
            module.correction_events(plan, ledger, "gpt-5.6-sol/high", "test")
        except module.ProvenanceError:
            pass
        else:
            raise AssertionError("duplicate correction evidence ID accepted")
    with tempfile.TemporaryDirectory() as temp:
        plan = Path(temp)
        (plan / "journal.jsonl").write_text("")
        event = module.p0_6_correction_event(ROOT, plan, "gpt-5.6-sol/high", "test")
        assert event is not None
        (plan / "journal.jsonl").write_text(json.dumps(event) + "\n")
        before = (plan / "journal.jsonl").read_bytes()
        assert module.p0_6_correction_event(ROOT, plan, "gpt-5.6-sol/high", "test") is None
        assert (plan / "journal.jsonl").read_bytes() == before
    print("p0 execution provenance: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
