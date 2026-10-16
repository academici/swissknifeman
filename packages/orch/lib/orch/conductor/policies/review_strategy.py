"""The review strategy of a batch, chosen before the first piece runs (``review.strategy``).

``each``: the pieces are reviewed one by one as before (``review.*``, dynamic by risk); ``groups``: one review per group of
pieces after the last piece of the group; ``single``: one review of the whole batch after its last piece; ``none``: no
review. The choice is the job of a small model call (the strategist) that sees every piece (title, goal, write set,
route, what it depends on); this module holds what is not a model's: the facts it is given, a deterministic choice the run
falls back to (and that ``review.strategist: rules`` uses on its own), and the check of whatever the strategist answers.
"""
from __future__ import annotations

import json
import re

MODES = ("each", "groups", "single", "none")
MAX_GROUP = 4          # pieces one review reads at most: a longer chain is cut into groups
FOUNDATION = ("packages/aicore/",)   # a piece that changes the foundation is read on its own, at a high effort
HIGH_EFFORT_MARKS = ("security", "secret", "permission", "auth", "redact", "sandbox", "guard")


def facts(ref: str, title: str, brief: dict) -> dict:
    """What the strategist is told about one piece, from its execution-input."""
    scope = brief.get("scope") or {}
    route = (brief.get("route") or {}).get("minimum") or {}
    return {"ref": ref, "title": title, "goal": str(brief.get("goal") or "")[:300],
            "include": list(scope.get("include") or [])[:12], "write_set": list(scope.get("write_set") or [])[:20],
            "route": {key: route[key] for key in ("class", "effort") if key in route},
            "checks": len((brief.get("acceptance") or {}).get("checks") or [])}


def _top(path: str) -> str:
    """The folder a write-set entry works in (up to three levels): a file counts by its folder, a pattern by its fixed prefix."""
    parts = [part for part in str(path).split("/") if part]
    fixed = []
    for part in parts:
        if any(mark in part for mark in "*?["):
            break
        fixed.append(part)
    else:
        if fixed and "." in fixed[-1]:  # a file: its folder
            fixed.pop()
    return "/".join(fixed[:3])


def _coupled(left: dict, right: dict) -> bool:
    """Two neighbours go in one review when they work on the same folders."""
    a, b = {_top(path) for path in left["write_set"]}, {_top(path) for path in right["write_set"]}
    a.discard(""), b.discard("")
    return bool(a & b) or bool(a and b and any(x.startswith(y) or y.startswith(x) for x in a for y in b))


def _alone(piece: dict) -> bool:
    return any(path.startswith(FOUNDATION) for path in piece["write_set"]) \
        or (piece["route"].get("class") == "frontier")


def rules(pieces: list) -> dict:
    """The deterministic choice: a batch of coupled neighbours is read together (cut at ``MAX_GROUP``), a piece on the
    foundation or on a frontier route is read alone, and uncoupled pieces are reviewed each."""
    if not pieces:
        return {"mode": "none", "groups": [], "reviewer": {"effort": "medium"}, "reason": "no pieces", "source": "rules"}
    if len(pieces) == 1:
        return {"mode": "each", "groups": [[pieces[0]["ref"]]], "reviewer": {"effort": "medium"},
                "reason": "one piece: reviewed on its own as configured", "source": "rules"}
    groups, current = [], []
    for piece in pieces:
        if _alone(piece):
            if current:
                groups.append(current)
            groups.append([piece])
            current = []
        elif current and _coupled(current[-1], piece) and len(current) < MAX_GROUP:
            current.append(piece)
        else:
            if current:
                groups.append(current)
            current = [piece]
    if current:
        groups.append(current)
    refs = [[piece["ref"] for piece in group] for group in groups]
    if len(refs) == 1:
        mode = "single"
    elif all(len(group) == 1 for group in refs):
        mode = "each"
    else:
        mode = "groups"
    text = " ".join(f"{piece['title']} {' '.join(piece['write_set'])}" for piece in pieces).lower()
    effort = "high" if any(mark in text for mark in HIGH_EFFORT_MARKS) else "medium"
    reason = f"{len(pieces)} pieces in {len(refs)} group(s): neighbours that work on the same folders are read together"
    return {"mode": mode, "groups": refs, "reviewer": {"effort": effort}, "reason": reason, "source": "rules"}


def prompt(pieces: list, proposal: dict) -> str:
    """The question to the strategist: the pieces, the rules' proposal and the answer to give."""
    return ("You choose how the review of one batch of work pieces is organised, before any piece runs. READ ONLY: answer "
            "from the facts below, run nothing.\n\nModes: `each` (every piece reviewed on its own), `groups` (neighbouring pieces "
            f"reviewed together, at most {MAX_GROUP} per group, in order), `single` (the whole batch reviewed once after its "
            "last piece), `none` (no review). A review costs time (its reasoning, minutes) and finds defects that the pieces "
            "cause in each other when read together; read a piece alone only when it is risky (the foundation, security, a "
            "public contract) or unrelated to its neighbours. Keep the order of the pieces; every piece is in exactly one "
            "group.\n\nPieces:\n" + json.dumps(pieces, ensure_ascii=False, indent=1) + "\n\nA proposal by rules: "
            + json.dumps({key: proposal[key] for key in ("mode", "groups", "reviewer")}, ensure_ascii=False)
            + "\n\nAnswer with ONE fenced `json` block and nothing else: `{\"mode\": \"each|groups|single|none\", "
            "\"groups\": [[\"ref\", ...], ...], \"reviewer\": {\"effort\": \"medium|high\"}, \"reason\": \"one sentence\"}`.")


def parse(text: str) -> dict | None:
    """The JSON object of the strategist's reply (a fenced block or the whole text), else ``None``."""
    found = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text or "", re.S)
    candidate = found.group(1) if found else (text or "").strip()
    try:
        doc = json.loads(candidate)
    except ValueError:
        return None
    return doc if isinstance(doc, dict) else None


def check(answer: dict | None, refs: list) -> dict | None:
    """The answer as a strategy when it is sound for ``refs`` (a partition in order, a known mode, a known effort), else ``None``."""
    if not isinstance(answer, dict) or answer.get("mode") not in MODES:
        return None
    mode, groups = answer["mode"], answer.get("groups")
    if mode == "none":
        groups = []
    else:
        if not isinstance(groups, list) or [ref for group in groups if isinstance(group, list) for ref in group] != list(refs):
            return None
        if any(not isinstance(group, list) or not group or len(group) > MAX_GROUP for group in groups):
            return None
        if mode == "single" and len(groups) != 1 or mode == "each" and any(len(group) != 1 for group in groups):
            return None
    effort = (answer.get("reviewer") or {}).get("effort", "medium")
    if effort not in ("low", "medium", "high"):
        return None
    return {"mode": mode, "groups": groups, "reviewer": {"effort": effort},
            "reason": str(answer.get("reason") or "")[:300], "source": "model"}
