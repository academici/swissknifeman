#!/usr/bin/env python3
"""One review of a whole batch: the production diff of every commit a conductor run made, read by one reviewer.

    batch-review.py RUN [--root DIR] [--project DIR] [--provider P] [--model M] [--effort E] [--max-tools N]
                    [--include PATH ...] [--exclude PATH ...] [--argv-json JSON] [--dry-run]

The pieces of a batch are reviewed together (the conductor reviews per piece): the reviewer sees what the pieces did to
each other. The diff is the commits of the run (``state.json``), limited to the paths of ``--include`` (default
``packages bridges scripts``) without tests, docs, fixtures, goldens and plans (``--exclude`` adds more). The reviewer role
text is ``roles/reviewer.md``'s output contract in short form; the reply goes to ``<run dir>/batch-review.md``. The route
defaults to ``[orch.conductor] reviewer`` (``grok/grok-4.7``) at effort ``medium`` (measured on one batch: a third of the time of ``high``, 4 of its 5 Majors and one new); ``--max-tools`` cuts the time further,
which is the reviewer's reasoning (output tokens), not its reading.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ORCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ORCH / "lib"))
if (ORCH.parent / "aicore" / "lib").is_dir():
    sys.path.insert(0, str(ORCH.parent / "aicore" / "lib"))

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


def commits_of(run_dir: Path) -> tuple:
    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run")
    parser.add_argument("--root", type=Path, help="conductor state folder (default: .swissknifeman/state/orch/conductor)")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--provider", default="grok")
    parser.add_argument("--model", default="grok-4.7")
    parser.add_argument("--effort", default="medium", help="default medium: about a third of the time of high, most of its findings")
    parser.add_argument("--max-tools", type=int, default=12)
    parser.add_argument("--include", nargs="+", default=["packages", "bridges", "scripts"])
    parser.add_argument("--exclude", nargs="+", default=[])
    parser.add_argument("--argv-json", help="the reviewer command as a JSON list (default: the launch catalog)")
    parser.add_argument("--dry-run", action="store_true", help="print the size of the prompt and the command, run nothing")
    args = parser.parse_args(argv)
    root = args.root or args.project / ".swissknifeman" / "state" / "orch" / "conductor"
    run_dir = root / args.run
    refs, shas = commits_of(run_dir)
    if not shas:
        print(f"BATCH_REVIEW_EMPTY: run {args.run} made no commit", file=sys.stderr)
        return 1
    diff = diff_of(args.project, shas, args.include, [*EXCLUDED, *args.exclude])
    prompt = PROMPT.format(refs=", ".join(refs), max_tools=args.max_tools) + diff
    if args.argv_json:
        command = json.loads(args.argv_json)
    else:
        from orch import launch  # noqa: E402
        command = launch.build_argv(launch.load_catalog(), "reviewer", args.provider, model=args.model,
                                    effort=args.effort, cwd=args.project)
    if args.dry_run:
        print(json.dumps({"pieces": refs, "commits": shas, "prompt_bytes": len(prompt.encode()), "command": command}))
        return 0
    done = subprocess.run(command, input=prompt, capture_output=True, text=True, cwd=args.project, check=False)
    text = done.stdout
    for line in reversed(text.splitlines()):  # a streaming reply: the last `result` event holds the answer
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "result":
            text = event.get("result") or text
            break
    (run_dir / "batch-review.md").write_text(text, encoding="utf-8")
    print(text)
    return 0 if done.returncode == 0 else done.returncode


if __name__ == "__main__":
    sys.exit(main())
