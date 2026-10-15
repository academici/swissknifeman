"""The diff and the prompt of one review of several pieces: shared by ``scripts/batch-review.py`` and the group reviews of
a run (``review.strategy``)."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from typing import Optional

PROMPT = """You are an independent code reviewer. READ ONLY: do not run any command and do not edit anything. Work from the diff \
below; open a file only when a defect cannot be judged without it, and use at most {max_tools} tool calls in total. Keep your \
reasoning short.

Context: the diff is the production-code part of one batch of work items ({refs}) made by one run, so look at how the pieces \
interact as well as at each piece. Tests and docs are not in the diff; assume the tests of the author pass.

Review for CORRECTNESS and SAFETY only; report only real defects that you can trace to a concrete failing scenario: wrong \
behaviour on normal or edge input (state, resume/retry, empty values, ordering, concurrency); a project-controlled value \
reaching a command, a shell or a path; drift between a schema and the code that uses it; a failure swallowed silently or \
state saved inconsistently. Do NOT report style, naming, missing comments, test gaps or suggestions without a failing scenario.

Answer in exactly this format, nothing else:
## Findings
For each: `[Blocker|Major|Minor] file:line - one-sentence defect`, then `Scenario: concrete inputs/state -> wrong result`, then \
`Fix: one line`. Most severe first, at most 12. If nothing real: `## Findings` then `none`.
## Checked and fine
At most 6 bullets naming the riskiest areas you traced and found sound.

--- DIFF ---
"""
EXCLUDED = ("tests/", "/tests/", "docs/", "fixtures/", "golden/", "plans/", ".md", "CHANGELOG", "config.example.toml")


def commits_of_state(state: dict) -> tuple:
    """``(refs, shas)`` of the pieces of a run state that were committed, in the order of the state."""
    refs, shas = [], []
    for ref, item in (state.get("items") or {}).items():
        sha = (((item.get("steps") or {}).get("commit") or {}).get("result") or {}).get("sha")
        if sha:
            refs.append(ref)
            shas.append(sha)
    return refs, shas


def diff_of(project: Path, shas: list, include: list, exclude: list) -> str:
    out = []
    for sha in shas:
        shown = subprocess.run(["git", "diff", f"{sha}~1", sha, "--", *include], cwd=project, capture_output=True,
                               text=True, check=True).stdout
        for block in shown.split("\ndiff --git ")[0:]:
            head = block.splitlines()[0] if block else ""
            if any(mark in head for mark in exclude):
                continue
            out.append(block if block.startswith("diff --git") else "diff --git " + block)
    return "\n".join(out)




def commits_of(run_dir: Path) -> tuple:
    return commits_of_state(json.loads((run_dir / "state.json").read_text(encoding="utf-8")))


# A finding line of the reply: ``[Major] file:line - defect``, as the prompt asks, also when the model dresses it as a list
# item, a number, bold or code (``- [Major]``, ``1. **[Major]**``, ```[Major]```).
SEVERITY = re.compile(r"^[ \t]*(?:[-*+][ \t]+|\d+[.)][ \t]+)?[`*_ \t]*\[(Blocker|Major|Minor)\][`*_ \t]*(.*)$", re.M)
_HEADER = re.compile(r"^[ \t]*#{1,6}[ \t]*\**[ \t]*(.+?)[ \t]*\**[ \t]*$", re.M)
_NONE = re.compile(r"^[ \t]*[`*_\-]*[ \t]*none[ \t]*[`*_.\-]*[ \t]*$", re.I | re.M)


def findings_section(text: str) -> Optional[str]:
    """The text under ``## Findings`` up to the next heading; ``None`` when the reply has no such heading."""
    heads = list(_HEADER.finditer(text or ""))
    for index, head in enumerate(heads):
        if head.group(1).strip().lower().rstrip(":") == "findings":
            end = heads[index + 1].start() if index + 1 < len(heads) else len(text)
            return text[head.end():end]
    return None


def verdict(text: str) -> dict:
    """What a review reply says: ``format`` is ``findings`` (at least one ``[Severity]`` line), ``none`` (the section says
    so) or ``malformed`` (no ``## Findings`` heading, or a section that is neither): a malformed reply is not a clean
    review; ``counts`` per severity and ``findings`` ``[{severity, location, text}]`` in the order of the reply."""
    section = findings_section(text)
    found = {"Blocker": 0, "Major": 0, "Minor": 0}
    rows = []
    for match in SEVERITY.finditer(section or ""):
        found[match.group(1)] += 1
        rest = match.group(2).strip().strip("`*_ ")
        location = rest.split(" - ", 1)[0].strip().strip("`*_ ") if " - " in rest else ""
        rows.append({"severity": match.group(1), "location": location, "text": rest})
    if section is None:
        kind = "malformed"
    elif rows:
        kind = "findings"
    elif _NONE.search(section):
        kind = "none"
    else:
        kind = "malformed"
    return {"format": kind, "counts": found, "findings": rows}


def counts(text: str) -> dict:
    """How many findings of each severity a reply holds."""
    return verdict(text)["counts"]


def followup_paths(findings: list) -> list:
    """The files that the Blocker and Major findings of a reply name (``file:line``), once each, in order."""
    paths = []
    for row in findings:
        if row["severity"] not in ("Blocker", "Major"):
            continue
        path = re.split(r":\d", row["location"], maxsplit=1)[0].strip() if row["location"] else ""
        if path and re.fullmatch(r"[\w./@+-]+", path) and not path.startswith(("/", "..")) and path not in paths:
            paths.append(path)
    return paths
