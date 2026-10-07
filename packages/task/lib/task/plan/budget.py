"""``plan.py context --budget``: where the bytes of an item's context pack come from. Pure reading, never a trim."""
from __future__ import annotations

import copy
import json

from . import context, store
from .model import item_phase

TOP_SOURCES = 5
SOURCE_KEYS = ("documents", "decisions", "reads", "upstream", "phase_dependencies")


def _size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8"))


def _sources(plan: store.Plan, item_id: str, pack: dict) -> list[dict]:
    mode, phase_id = context.pack_mode(plan), item_phase(item_id)
    pinned = set(plan.items[item_id].get("decisions", []))
    sources = []
    for doc in pack["documents"]:
        reason = context.scope_reason(doc, item_id, phase_id, mode)
        sources.append({"key": "documents", "ref": f"knowledge/{doc.get('id')}", "bytes": _size(doc),
                        "reason": reason or "unbound"})
    for doc in pack["decisions"]:
        reason = "explicit" if doc.get("id") in pinned or doc.get("id") not in plan.decisions \
            else context.scope_reason(doc, item_id, phase_id, mode)
        sources.append({"key": "decisions", "ref": str(doc.get("id")), "bytes": _size(doc),
                        "reason": reason or "unbound"})
    for index, entry in enumerate(pack["reads"]):
        source = {"key": "reads", "ref": str(entry.get("ref") or entry.get("path")), "bytes": _size(entry)}
        target = entry.get("included") or context.duplicate_target(plan, item_id, pack, index)
        if target:
            source["duplicate_of"] = target
        sources.append(source)
    for key in ("upstream", "phase_dependencies"):
        sources += [{"key": key, "ref": str(doc.get("id")), "bytes": _size(doc)} for doc in pack[key]]
    return sorted(sources, key=lambda s: (-s["bytes"], s["key"], s["ref"]))


def measure(plan: store.Plan, item_id: str, *, repos=None) -> dict:
    """Size report of the pack of ``item_id``. ``bytes`` is the exact rendered size; ``by_key`` and the per-source
    ``bytes`` are sized on their own (a nested value loses its indentation level, so the parts are approximate)."""
    pack = context.collect(plan, item_id, with_scout=False, repos=repos)
    mode = context.pack_mode(plan)
    sources = _sources(plan, item_id, pack)
    unbound = [s for s in sources if s.get("reason") == "unbound"]
    duplicates = [s for s in sources if s["key"] == "reads" and s.get("duplicate_of")]
    total = len(context.render(plan, item_id, with_scout=False, repos=repos).encode("utf-8"))
    report = {
        "item": item_id, "mode": mode, "bytes": total, "budget_bytes": context.budget_bytes(plan),
        "over_budget": total > context.budget_bytes(plan),
        "by_key": {key: _size(value) for key, value in pack.items()}, "sources": sources,
        "unbound": {"documents": sum(s["key"] == "documents" for s in unbound),
                    "decisions": sum(s["key"] == "decisions" for s in unbound),
                    "bytes": sum(s["bytes"] for s in unbound)},
        "duplicates": {"reads": len(duplicates), "bytes": sum(s["bytes"] for s in duplicates)},
    }
    if mode == "legacy":
        preview = copy.deepcopy(plan)
        preview.plan.setdefault("settings", {})["context_pack"] = "scoped"
        report["scoped_preview_bytes"] = len(
            context.render(preview, item_id, with_scout=False, repos=repos).encode("utf-8"))
    return report


def _kb(size: int) -> int:
    return size // 1024


def text(report: dict) -> str:
    head = (f"{report['item']} {_kb(report['bytes'])} KB ({report['mode']}; budget "
            f"{_kb(report['budget_bytes'])} KB{'; OVER' if report['over_budget'] else ''})")
    keys = sorted(report["by_key"].items(), key=lambda kv: (-kv[1], kv[0]))
    lines = [head, "  " + ", ".join(f"{k} {_kb(v)} KB" for k, v in keys if v)]
    unbound, dup = report["unbound"], report["duplicates"]
    if unbound["documents"] or unbound["decisions"]:
        lines.append(f"  unbound: {unbound['documents']} document(s), {unbound['decisions']} decision(s), "
                     f"{_kb(unbound['bytes'])} KB — bind with plan.py link <plan> knowledge/<id> <Pn|Pn.m> "
                     "--kind applies_to or set global: true")
    if dup["reads"]:
        lines.append(f"  duplicate reads: {dup['reads']}, {_kb(dup['bytes'])} KB")
    if "scoped_preview_bytes" in report:
        lines.append(f"  scoped preview: {_kb(report['scoped_preview_bytes'])} KB (settings.context_pack: scoped)")
    top = [f"{s['ref']} {_kb(s['bytes'])} KB" + (f" ({s['reason']})" if s.get("reason") else "")
           for s in report["sources"][:TOP_SOURCES]]
    if top:
        lines.append("  top: " + ", ".join(top))
    return "\n".join(lines)
