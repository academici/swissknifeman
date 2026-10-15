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
from pathlib import Path
import subprocess
import sys

ORCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ORCH / "lib"))
if (ORCH.parent / "aicore" / "lib").is_dir():
    sys.path.insert(0, str(ORCH.parent / "aicore" / "lib"))

from orch.conductor import review_batch  # noqa: E402

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
    refs, shas = review_batch.commits_of(run_dir)
    if not shas:
        print(f"BATCH_REVIEW_EMPTY: run {args.run} made no commit", file=sys.stderr)
        return 1
    diff = review_batch.diff_of(args.project, shas, args.include, [*review_batch.EXCLUDED, *args.exclude])
    prompt = review_batch.PROMPT.format(refs=", ".join(refs), max_tools=args.max_tools) + diff
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
