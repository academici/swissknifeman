"""The diff and the prompt of one review of several pieces: shared by ``scripts/batch-review.py`` and the group reviews of
a run (``review.strategy``)."""
from __future__ import annotations

from pathlib import Path
import re
from aicore.util.proc import run as run_with_timeout

from orch.conductor import contract, records
from orch.conductor.heal import heal
from orch.conductor.domain.report import json_block, findings_problems
from orch.conductor.domain.item import piece_commits
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import STATE_FILE

PROMPT = """You are an independent code reviewer. READ ONLY: do not run any command and do not edit anything. Work from the diff \
below; open a file only when a defect cannot be judged without it, and use at most {max_tools} tool calls in total. Keep your \
reasoning short.

Context: the diff is the production-code part of one batch of work items ({refs}) made by one run, so look at how the pieces \
interact as well as at each piece. Tests and docs are not in the diff; assume the tests of the author pass.

Review for CORRECTNESS and SAFETY only; report only real defects that you can trace to a concrete failing scenario: wrong \
behaviour on normal or edge input (state, resume/retry, empty values, ordering, concurrency); a project-controlled value \
reaching a command, a shell or a path; drift between a schema and the code that uses it; a failure swallowed silently or \
state saved inconsistently. Do NOT report style, naming, missing comments, test gaps or suggestions without a failing scenario.

Answer with one closed JSON block tagged `json review-findings`, and nothing else:
```json review-findings
{{"verdict":"GREEN|ATTENTION|RED","findings":[{{"id":"F1","severity":"Blocker|Major|Minor|Nit",
"confidence":"high|medium|low","location":"file:line","failure_scenario":"concrete input/state -> wrong result",
"basis":"correctness|security|performance|project rule|input contract","reproduction":"command or concrete steps, when known"}}],
"questions":[],"residual_risk":""}}
```
Use GREEN with an empty findings list when nothing real was found. Every finding needs a concrete failure scenario.
No additional properties. Do not cap findings or drop Blockers; the conductor bounds their delivery to the fixer.

--- DIFF ---
"""
INCLUDE = ["."]  # the whole project: the layout of a project is not known here (a hard-coded packages/ left every other project with an empty diff)
EXCLUDED = ("tests/", "/tests/", "docs/", "fixtures/", "golden/", "plans/", ".md", "CHANGELOG", "config.example.toml")


def has_hunks(diff: str) -> bool:
    """Whether a diff holds any changed line: file headers alone are nothing to review."""
    return any(line.startswith("@@") for line in diff.splitlines())


def commits_of_state(state: dict) -> tuple:
    """``(refs, shas)`` of the pieces of a run state that were committed, in the order of the state. An entry of ``shas``
    is the sha of a piece that has one commit and the list of its commits (in order) for a piece of a split run
    (``commit.mode: implementation-and-fixes``)."""
    refs, shas = [], []
    for ref, item in (state.get("items") or {}).items():
        found = piece_commits(item)
        if found:
            refs.append(ref)
            shas.append(found[0] if len(found) == 1 else found)
    return refs, shas


def last_sha(entry) -> str:
    """The newest commit of an entry of :func:`commits_of_state`."""
    return entry if isinstance(entry, str) else entry[-1]


def diff_of(project: Path, shas: list, include: list, exclude: list) -> str:
    """The production diff of the commits. A piece with one commit is read as ``sha~1..sha``; a piece of a split run (an entry
    that is a list) as one range from the parent of its first commit to its last."""
    out = []
    for entry in shas:
        first, last = (entry, entry) if isinstance(entry, str) else (entry[0], entry[-1])
        shown = run_with_timeout(["git", "diff", f"{first}~1", last, "--", *include], cwd=project, capture_output=True,
                               text=True, check=True, timeout=60).stdout
        shown = str(shown)  # text=True: a str
        for block in shown.split("\ndiff --git ")[0:]:
            head = block.splitlines()[0] if block else ""
            if any(mark in head for mark in exclude):
                continue
            out.append(block if block.startswith("diff --git") else "diff --git " + block)
    return "\n".join(out)




def commits_of(run_dir: Path) -> tuple:
    """The commits of the run in ``run_dir`` from its ``state.json`` (records/v1 state: ``STATE_INVALID`` when it does not
    match, ``RUN_UNKNOWN`` when there is none)."""
    state = records.read(Path(run_dir) / STATE_FILE, "state")
    if state is None:
        raise Stop("RUN_UNKNOWN", f"no state.json in {run_dir}")
    return commits_of_state(state)


def verdict(text: str) -> dict:
    """Parse the same closed review-findings contract as an item review. Invalid output fails closed."""
    doc, error = json_block(text, "review-findings")
    counts = {"Blocker": 0, "Major": 0, "Minor": 0}
    if not error and doc is not None:
        doc, _notes = heal("review-findings", doc)
        error = contract.problems(doc, "review-findings")
        if not error:
            error = findings_problems(doc)
    if error or doc is None:
        return {"format": "malformed", "counts": counts, "findings": []}
    for row in doc["findings"]:
        if row["severity"] in counts:
            counts[row["severity"]] += 1
    return {"format": "findings" if doc["findings"] else "none", "counts": counts,
            "findings": doc["findings"], "document": doc}


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
