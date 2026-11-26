"""Pure, bounded handoff of confirmed findings. Full evidence stays in the referenced artifacts."""
from __future__ import annotations

from orch.conductor.domain.report import finding_key
from orch.conductor.domain.item import done_steps

SCHEMA = "urn:swissknifeman:orch:conductor:fix-brief:v1"
DEFAULT_LIMITS = {"max_findings": 12, "max_chars": 24000}
SEVERITIES = ("Blocker", "Major", "Minor", "Nit")
CONFIDENCE = ("high", "medium", "low")
FIELD_LIMITS = {"problem": 1200, "fix": 800, "observed": 600, "cmd": 400}


def _clip(text: str, limit: int, ref: str, name: str) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    kept = limit
    for _ in range(8):
        marker = f"… [clipped {len(text) - kept} chars; full: {ref}#{name}]"
        size = max(0, limit - len(marker))
        if kept == size:
            break
        kept = size
    return text[:(kept + 1) // 2] + marker + (text[-(kept // 2):] if kept // 2 else ""), True


def render(doc: dict) -> str:
    """Render only the brief's closed fields, never a role's stream or transcript."""
    lines = ["The review found these defects and the triage reproduced each one:", ""]
    if any("exit" not in row.get("reproduction", {}) for row in doc["findings"]):
        lines[0] = "The group review reported these defects; reproduce each one before correction:"
    for row in doc["findings"]:
        lines.append(f"{row['id']} [{row['key']}] ({row['severity']}, {row['location']}): {row['problem']}")
        repro = row.get("reproduction")
        if repro:
            result = f"exit {repro['exit']}: " if "exit" in repro else "reported, not run: "
            lines.append(f"  reproduced: `{repro['cmd']}` → {result}{repro['observed']}")
        lines.append(f"  fix: {row['fix']}")
    deferred = doc["deferred"]
    if deferred["count"]:
        counts = ", ".join(f"{n} {severity}" for severity, n in deferred["by_severity"].items() if n)
        lines.append(f"Deferred: {deferred['count']} ({counts}); full findings: {deferred['ref']}")
    lines += [f"Scope constraint: {text}" for text in doc["scope_constraints"]]
    if doc["required_checks"]:
        lines.append("Required checks: " + ", ".join(doc["required_checks"]))
    return "\n".join(lines)


def build(findings_doc: dict, triage_doc: dict, keys: dict, limits: dict, refs: dict) -> dict:
    """Select by severity/confidence/id, clipping fields before admission; Blockers always survive.

    ``refs`` names review metadata, base, the full findings artifact, scope constraints and check ids.
    Unselected findings remain at that artifact and are counted explicitly.
    """
    limits = {**DEFAULT_LIMITS, **limits}
    doc = {"$schema": SCHEMA, "review": refs["review"], "base": refs["base"], "findings": [],
           "deferred": {"count": 0, "by_severity": {}, "ref": refs["findings"]},
           "scope_constraints": list(refs.get("scope_constraints", [])),
           "required_checks": list(refs.get("required_checks", [])), "limits": limits}
    by_id = {row["finding"]: row for row in triage_doc["confirmed"]}
    found = sorted((row for row in findings_doc["findings"] if row["id"] in by_id),
                   key=lambda row: (SEVERITIES.index(row["severity"]), CONFIDENCE.index(row["confidence"]), row["id"]))
    all_rows = []
    for finding in found:
        entry = by_id[finding["id"]]
        row = {"key": keys.get(finding["id"], finding_key(finding)), "id": finding["id"],
               "severity": finding["severity"], "location": finding["location"],
               "path": finding["location"].split(":", 1)[0], "problem": finding["failure_scenario"],
               "fix": entry["fix"], "clipped": []}
        if entry.get("reproduction"):
            row["reproduction"] = dict(entry["reproduction"])
        for field, maximum in FIELD_LIMITS.items():
            holder = row.get("reproduction", {}) if field in ("cmd", "observed") else row
            if field in holder:
                holder[field], clipped = _clip(holder[field], maximum, refs["findings"], row["id"])
                if clipped:
                    row["clipped"].append(field)
        all_rows.append(row)

    def deferred(selected):
        omitted = [row for row in all_rows if row not in selected]
        return {"count": len(omitted), "by_severity": {
            severity: sum(row["severity"] == severity for row in omitted)
            for severity in SEVERITIES if any(row["severity"] == severity for row in omitted)}, "ref": refs["findings"]}

    doc["deferred"] = deferred([])
    if not any(row["severity"] == "Blocker" for row in all_rows) and len(render(doc)) > limits["max_chars"]:
        raise ValueError("fix-brief max_chars cannot hold the framing and full deferred reference")
    # Reserve the complete deferred summary while measuring: adding it later must not push a brief over its cap.
    for row in all_rows:
        trial = doc["findings"] + [row]
        doc["deferred"] = deferred(trial)
        if row["severity"] == "Blocker" or (len(trial) <= limits["max_findings"]
                and len(render(dict(doc, findings=trial))) <= limits["max_chars"]):
            doc["findings"] = trial
    doc["deferred"] = deferred(doc["findings"])
    return doc

def correction_inputs(state: dict, number: int, findings: dict, triage: dict) -> tuple:
    """Merge undelivered confirmed findings with this round by conductor key, retaining full step evidence."""
    steps = done_steps(state.get("steps", {}))
    entries = {}
    for source in state.get("deferred_findings", []):
        old = steps[f"review.{source['round']}"]["result"]["findings"]
        checked = (steps.get(f"triage.{source['round']}-a") or steps[f"triage.{source['round']}"])["result"]["triage"]
        found = next(row for row in old["findings"] if row["id"] == source["id"])
        confirmed = next(row for row in checked["confirmed"] if row["finding"] == source["id"])
        entries[(source["key"], source["id"])] = (found, confirmed, source)
    by_id = {row["id"]: row for row in findings["findings"]}
    for entry in triage["confirmed"]:
        found = by_id[entry["finding"]]
        key = finding_key(found)
        entries[(key, found["id"])] = (found, entry, {"key": key, "round": number, "id": found["id"]})
    # Rejection by a later triage discharges an older queued obligation too.
    for entry in triage["rejected"]:
        entries.pop((finding_key(by_id[entry["finding"]]), entry["finding"]), None)
    merged, confirmed, sources, used = [], [], {}, set()
    for found, entry, source in entries.values():
        name = found["id"]
        if name in used:
            name = next(f"F{n}" for n in range(1, len(entries) * 2 + 1)
                        if f"F{n}" not in used and f"F{n}" not in by_id)
        used.add(name)
        merged.append(dict(found, id=name))
        confirmed.append(dict(entry, finding=name))
        sources[name] = source
    return dict(findings, findings=merged), dict(triage, confirmed=confirmed), sources

