#!/usr/bin/env python3
"""One review of a whole batch: the production diff of every commit a conductor run made, read by one reviewer.

    batch-review.py RUN [--root DIR] [--project DIR] [--provider P] [--model M] [--effort E] [--max-tools N]
                    [--include PATH ...] [--exclude PATH ...] [--argv-json JSON] [--dry-run]

A Blocker or Major finding also writes ``batch-review.followup.json``, the execution-input of a commit that corrects it
(``orch conduct run --input FILE --commit``): its ``provenance.session_ref`` names the run and every piece and, when the last
piece kept a session, that session, so the follow-up resumes it or starts fresh with the handoff of the whole group.

The pieces of a batch are reviewed together (the conductor reviews per piece): the reviewer sees what the pieces did to
each other. The diff is the commits of the run (``state.json``), limited to the paths of ``--include`` (default
``.``, the whole project) without tests, docs, fixtures, goldens and plans (``--exclude`` adds more). The reviewer role
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
import time
import types

ORCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ORCH / "lib"))
if (ORCH.parent / "aicore" / "lib").is_dir():
    sys.path.insert(0, str(ORCH.parent / "aicore" / "lib"))

from orch.conductor import contract, records, review_batch  # noqa: E402
from orch.conductor.application import review_plan  # noqa: E402
from orch.conductor.infrastructure.files import STATE_FILE  # noqa: E402

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("run")
    parser.add_argument("--root", type=Path, help="conductor state folder (default: .swissknifeman/state/orch/conductor)")
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--provider", default="grok")
    parser.add_argument("--model", default="grok-4.7")
    parser.add_argument("--effort", default="medium", help="default medium: about a third of the time of high, most of its findings")
    parser.add_argument("--max-tools", type=int, default=12)
    parser.add_argument("--include", nargs="+", default=review_batch.INCLUDE)
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
    began = time.monotonic()
    done = subprocess.run(command, input=prompt, capture_output=True, text=True, cwd=args.project, check=False)
    seconds = round(time.monotonic() - began, 1)
    streams = run_dir / "streams"  # the raw reply and the measures, for step-profile.py and the observer
    streams.mkdir(parents=True, exist_ok=True)
    (streams / "batch-review.jsonl").write_text(done.stdout, encoding="utf-8")
    (streams / "batch-review.stderr").write_text(done.stderr, encoding="utf-8")
    (run_dir / "batch-review.json").write_text(json.dumps(
        {"provider": args.provider, "model": args.model, "effort": args.effort, "pieces": refs, "commits": shas,
         "prompt_bytes": len(prompt.encode()), "seconds": seconds, "returncode": done.returncode}, indent=2) + "\n",
        encoding="utf-8")
    print(f"BATCH_REVIEW: {args.provider}/{args.model}/{args.effort} in {seconds} s, prompt {len(prompt) // 1000} KB; "
          f"raw reply {streams / 'batch-review.jsonl'}", file=sys.stderr)
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
    read = review_batch.verdict(text)
    summary = {"format": read["format"], "counts": read["counts"], "file": str(run_dir / "batch-review.md")}
    problems = contract.problems(summary, "review-summary")
    if problems:
        raise ValueError("invalid batch review summary: " + "; ".join(problems))
    print(json.dumps(summary))
    if read["format"] == "malformed":
        print("GROUP_REVIEW_FAILED: malformed review-findings JSON", file=sys.stderr)
        return done.returncode or 1
    followup = followup_of(args, run_dir, refs, read)
    if followup:
        print(f"BATCH_REVIEW_FOLLOWUP: {followup}", file=sys.stderr)
    return done.returncode


class _Say:
    """The ``progress`` of the conductor that ``review_plan.followup_input`` reports to, here the standard error."""

    @staticmethod
    def emit(event, **fields):
        print(f"{fields.get('reason_code', event)}: {fields.get('message', '')}", file=sys.stderr)


def followup_of(args, run_dir: Path, refs: list, read: dict):
    """The follow-up execution-input of the Blocker and Major findings of the review (``review_plan.followup_input`` on the
    state of the run), or ``None`` when there is none to correct."""
    project = Path(args.project).resolve()

    def relative(path) -> str:
        try:
            return Path(path).resolve().relative_to(project).as_posix()
        except ValueError:
            return str(path)

    owner = types.SimpleNamespace(run_id=args.run, directory=run_dir, state=records.read(run_dir / STATE_FILE, "state"),
                                  progress=_Say(), _relative=relative)
    return review_plan.followup_input(owner, 1, refs, read, name="batch-review")


if __name__ == "__main__":
    sys.exit(main())
