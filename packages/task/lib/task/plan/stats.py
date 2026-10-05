"""``plan.py stats``: scout, unit and friction numbers of one plan, read from ``log.jsonl`` only (D3 point 4).

Pure reading: no thresholds and no decisions. The owner decides whether scout or delegation become defaults.
"""
from __future__ import annotations

from collections import Counter
from statistics import median

from . import lifecycle, store

UNIT_OUTCOMES = ("accepted", "reworked", "rejected")


def collect(plan: store.Plan) -> dict:
    """Aggregates of ``plan``: ``friction`` by type and item, ``scout`` outcomes, ``units`` by class and model."""
    friction_types: Counter = Counter()
    friction_items: dict[str, Counter] = {}
    scout_outcomes: Counter = Counter()
    scout_seconds: list[float] = []
    groups: dict[tuple[str, str], dict] = {}
    for _, event, _error in store.log_lines(plan.root):
        if not event:
            continue
        kind, data = event.get("type"), event.get("data") if isinstance(event.get("data"), dict) else {}
        if kind in lifecycle.FRICTION_TYPES:
            friction_types[kind] += 1
            friction_items.setdefault(event.get("item") or event.get("phase") or "plan", Counter())[kind] += 1
        elif kind == "scout":
            scout_outcomes[data.get("outcome", "?")] += 1
            if isinstance(data.get("seconds"), (int, float)):
                scout_seconds.append(float(data["seconds"]))
        elif kind == "delegate" and data.get("status") in UNIT_OUTCOMES:
            group = groups.setdefault((str(data.get("class", "unknown")), str(data.get("model", "unknown"))),
                                      {"counts": Counter(), "minutes": []})
            group["counts"][data["status"]] += 1
            if isinstance(data.get("minutes"), (int, float)) and not isinstance(data.get("minutes"), bool):
                group["minutes"].append(data["minutes"])
    return {
        "friction": {"by_type": dict(sorted(friction_types.items())),
                     "by_item": {k: dict(sorted(v.items())) for k, v in sorted(friction_items.items())}},
        "scout": {"runs": sum(scout_outcomes.values()),
                  "outcomes": {o: scout_outcomes.get(o, 0) for o in ("ok", "failed", "skipped")},
                  "mean_seconds": round(sum(scout_seconds) / len(scout_seconds), 1) if scout_seconds else None},
        "units": [{"class": klass, "model": model, **{o: g["counts"].get(o, 0) for o in UNIT_OUTCOMES},
                   "median_minutes": median(g["minutes"]) if g["minutes"] else None}
                  for (klass, model), g in sorted(groups.items())],
    }


def text(stats: dict) -> str:
    """Plain-text report of ``collect`` output."""
    friction, scout, units = stats["friction"], stats["scout"], stats["units"]
    lines = ["friction: " + (", ".join(f"{k} {v}" for k, v in friction["by_type"].items()) or "none")]
    lines += [f"  {item}: " + ", ".join(f"{k} {v}" for k, v in counts.items()) for item, counts in friction["by_item"].items()]
    mean = f", mean {scout['mean_seconds']}s" if scout["mean_seconds"] is not None else ""
    lines.append("scout: " + (f"{scout['runs']} run(s): " + ", ".join(f"{k} {v}" for k, v in scout["outcomes"].items()) + mean
                              if scout["runs"] else "no runs"))
    lines.append("units: " + ("" if units else "none"))
    for row in units:
        minutes = f", median {row['median_minutes']} min" if row["median_minutes"] is not None else ""
        lines.append(f"  {row['class']}/{row['model']}: accepted {row['accepted']}, reworked {row['reworked']}, "
                     f"rejected {row['rejected']}{minutes}")
    return "\n".join(lines)
