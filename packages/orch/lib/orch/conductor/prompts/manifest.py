"""The ``prompt-manifest/v1`` document of a prompt, and the comparison of two manifests (``prompt-diff/v1``)."""
from __future__ import annotations

from typing import Optional

from aicore.content.budget import estimate_tokens
from aicore.util.digest import sha256_hex

from orch.conductor import records
from orch.conductor.policies.budget import budgets
from orch.conductor.prompts.blocks import render


def manifest(blocks, *, step: str, role: str, route: dict, excluded=(), limits=None, resumed_session: bool = False,
             digest: Optional[str] = None) -> dict:
    """The ``prompt-manifest/v1`` document of a prompt: its blocks (kind, origin, digest, estimated tokens), what was left
    out and why, the digest and size of the whole prompt, and, when ``limits`` (``{class: tokens}``) is given, the tokens
    of each budget class against its limit. ``resumed_session`` marks the delta prompt of a resumed session; ``digest`` is
    the ``task_digest`` of the full prompt of the step."""
    text = render(blocks)
    rows = []
    for block in blocks:
        row = {"kind": block.kind, "origin": block.origin, "sha256": sha256_hex(block.text.encode("utf-8")),
               "tokens": estimate_tokens(block.text)}
        if block.id:
            row["id"] = block.id
        rows.append(row)
    doc = {"schema": "prompt-manifest/v1", "step": step, "role": role,
           "route": {key: route[key] for key in ("provider", "model", "effort") if route.get(key)},
           "blocks": rows, "excluded": [dict(row) for row in excluded], "estimated_tokens": estimate_tokens(text),
           "prompt_sha256": sha256_hex(text.encode("utf-8"))}
    if limits is not None:
        doc["budgets"] = budgets(blocks, limits)
    if resumed_session:
        doc["resumed_session"] = True
    if digest:
        doc["task_digest"] = digest
    return doc


def top_blocks(doc: dict, limit: int = 5) -> list:
    """The ``limit`` blocks of a manifest with the most tokens, the first of equals first."""
    return sorted(doc.get("blocks", []), key=lambda row: -row["tokens"])[:limit]


def explain_table(doc: dict) -> str:
    """The manifest as a table: kind, origin, tokens and the start of the digest of each block, then what was excluded."""
    route = "/".join(doc.get("route", {}).get(key, "") for key in ("provider", "model", "effort")
                     if doc.get("route", {}).get(key))
    lines = [f"{doc['step']} ({doc['role']}{', ' + route if route else ''}): {len(doc['blocks'])} block(s), "
             f"{doc['estimated_tokens']} estimated tokens, prompt sha256 {doc['prompt_sha256'][:12]}", "",
             "kind | origin | tokens | sha256"]
    for row in doc["blocks"]:
        name = row["kind"] + (f" {row['id']}" if row.get("id") else "")
        lines.append(f"{name} | {row['origin']} | {row['tokens']} | {row['sha256'][:12]}")
    if doc.get("excluded"):
        lines += ["", "excluded:"] + [f"- {row['id']}: {row['reason']}" for row in doc["excluded"]]
    return "\n".join(lines)


def diff_manifests(base: dict, target: dict) -> dict:
    """What changed from the prompt of manifest ``base`` to that of ``target``: per block (matched by kind and origin; a
    block without an origin by kind and its order among the blocks of that kind) ``added``, ``removed``, ``changed``
    (another digest) or ``same``, with the tokens of both sides; and the totals of the whole prompt."""
    def keyed(doc: dict) -> dict:
        seen: dict = {}
        found = {}
        for row in doc.get("blocks") or []:
            name = (row.get("kind"), row.get("origin") or "")
            seen[name] = seen.get(name, 0) + 1
            found[(*name, seen[name])] = row
        return found

    before, after = keyed(base), keyed(target)
    rows = []
    for key in list(before) + [key for key in after if key not in before]:
        old, new = before.get(key), after.get(key)
        change = "added" if old is None else "removed" if new is None else \
            "same" if old.get("sha256") == new.get("sha256") else "changed"
        tokens = {"from": (old or {}).get("tokens", 0), "to": (new or {}).get("tokens", 0)}
        rows.append({"kind": key[0], "origin": key[1] or None, "change": change,
                     "tokens": dict(tokens, delta=tokens["to"] - tokens["from"]),
                     "sha256": {"from": (old or {}).get("sha256"), "to": (new or {}).get("sha256")}})
    total = {"from": base.get("estimated_tokens", 0), "to": target.get("estimated_tokens", 0)}
    doc = {"schema": "prompt-diff/v1", "base": {"step": base.get("step"), "prompt_sha256": base.get("prompt_sha256")},
           "target": {"step": target.get("step"), "prompt_sha256": target.get("prompt_sha256")},
           "blocks": rows, "tokens": dict(total, delta=total["to"] - total["from"]),
           "counts": {change: sum(1 for row in rows if row["change"] == change)
                      for change in ("added", "removed", "changed", "same")}}
    return records.check(doc, "prompt-diff", "prompt diff", hint=records.WRITER_HINT)  # records/v1 prompt-diff


def diff_table(doc: dict) -> str:
    """The prompt diff as lines: every block that is not the same, then the token totals."""
    counts = doc["counts"]
    lines = [f"{doc['base']['step']} -> {doc['target']['step']}: {counts['added']} added, {counts['removed']} removed, "
             f"{counts['changed']} changed, {counts['same']} same; tokens {doc['tokens']['from']} -> "
             f"{doc['tokens']['to']} ({doc['tokens']['delta']:+d})"]
    for row in doc["blocks"]:
        if row["change"] != "same":
            lines.append(f"{row['change']}: {row['kind']} {row['origin'] or '-'} "
                         f"({row['tokens']['from']} -> {row['tokens']['to']}, {row['tokens']['delta']:+d})")
    return "\n".join(lines)
