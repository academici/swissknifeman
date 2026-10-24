"""``orch conduct prompt explain|diff``: what a prompt of a role step was made of (moved out of ``cli.py`` with the supervisor verbs, so
that the module of the command line does not grow)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

from orch.conductor import engine, prompts, records, runs


STEP_PATTERN = r"[a-z][a-z0-9-]*(\.[0-9]+(-q[0-9]+)?)?"


class _PromptError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


def _manifest(project: Path, run: Optional[str], item: str, step: str, missing: str = "MANIFEST_UNKNOWN") -> tuple:
    """``(run_id, manifest)`` of ``prompts/<step>.manifest.json`` of ``item`` in ``run`` (default: the latest run), the
    paths checked to stay inside the run; ``_PromptError`` otherwise (``missing`` names a manifest that is not there)."""
    if re.fullmatch(STEP_PATTERN, step) is None:
        raise _PromptError("PROMPT_PATH_INVALID", "step must be a role step such as executor.1")
    run_id = run or runs.latest_run_id(project)
    if run_id and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_id) is None:
        raise _PromptError("PROMPT_PATH_INVALID", "invalid run id")
    directory = engine.runs_root(project) / (run_id or "-")
    if not run_id or not (directory / engine.RUN_FILE).is_file():
        raise _PromptError("RUN_UNKNOWN", f"no conductor run {run or ''} in {engine.runs_root(project)}")
    item_dir = directory / engine.safe(item)
    file = item_dir / "prompts" / f"{step}.manifest.json"
    try:
        item_dir.resolve().relative_to(directory.resolve())
        file.resolve().relative_to(item_dir.resolve())
    except (ValueError, OSError, RuntimeError):
        raise _PromptError("PROMPT_PATH_INVALID", "manifest must resolve inside the item directory") from None
    doc = engine.read_json(file) if file.is_file() else None
    if not isinstance(doc, dict):
        raise _PromptError(missing, f"no prompt manifest for {item} {step} in run {run_id} ({file})")
    return run_id, doc


def _baseline(step: str) -> Optional[str]:
    """The previous attempt of the same step (``executor.2`` -> ``executor.1``), None for a first one."""
    found = re.fullmatch(r"([a-z][a-z0-9-]*)\.([0-9]+)(-q[0-9]+)?", step)
    if found is None or int(found.group(2)) <= 1:
        return None
    return f"{found.group(1)}.{int(found.group(2)) - 1}{found.group(3) or ''}"


def prompt(args, project: Path) -> int:
    """``prompt explain``: the blocks of the prompt a role step was given (``prompts/<step>.manifest.json``), their
    origin, size and digest, and what was left out. ``prompt diff``: what changed in it against the previous attempt of
    the step or a named ``RUN:ITEM:STEP``."""
    try:
        if args.prompt_verb == "diff":
            return _prompt_diff(args, project)
        _run_id, doc = _manifest(project, args.run, args.item, args.step)
    except (_PromptError, engine.Stop) as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        return 1
    print(json.dumps(doc, ensure_ascii=False, indent=2) if args.json else prompts.explain_table(doc))
    return 0


def _prompt_diff(args, project: Path) -> int:
    run_id, target = _manifest(project, args.run, args.item, args.step, missing="PROMPT_MANIFEST_MISSING")
    if args.against:
        parts = args.against.split(":")
        if len(parts) != 3 or not all(parts):
            raise _PromptError("PROMPT_PATH_INVALID", "--against takes RUN:ITEM:STEP")
        against = (parts[0], parts[1], parts[2])
    else:
        previous = _baseline(args.step)
        if previous is None:
            raise _PromptError("PROMPT_BASELINE_MISSING", f"{args.step} is the first attempt of its step: name the prompt "
                                                          "to compare with --against RUN:ITEM:STEP")
        against = (run_id, args.item, previous)
    _base_run, base = _manifest(project, *against, missing="PROMPT_MANIFEST_MISSING")
    doc = records.check(dict(prompts.diff_manifests(base, target), run=run_id, item=args.item,
                             against={"run": against[0], "item": against[1], "step": against[2]}),
                        "prompt-diff", "prompt diff", hint=records.WRITER_HINT)
    print(json.dumps(doc, ensure_ascii=False, indent=2) if args.json else prompts.diff_table(doc))
    return 0
