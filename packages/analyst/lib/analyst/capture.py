"""Explicit normalized capture and legacy migration commands."""
import json
import os
from pathlib import Path

from .common import die, parse_args
from .events import append_event
from .runs import migrate_legacy, normalize


def cmd_capture(env, argv):
    opts, _ = parse_args(argv, {"--provider": "str", "--schema": "str", "--input": "str", "--dry-run": "bool"})
    if opts["help"]:
        print("analyst capture --provider ID --schema N --input FILE [--dry-run]")
        return
    try:
        schema = int(opts["schema"] or "")
        raw = json.loads(Path(opts["input"] or "").read_text(encoding="utf-8"))
        event = normalize(opts["provider"] or "", schema, raw, project_id=Path(os.getcwd()).name,
                          raw_ref="local:capture")
    except (OSError, ValueError, TypeError) as exc:
        die(str(exc))
    if not opts["dry_run"]:
        append_event(os.getcwd(), event, audit={"reader_version": event["provenance"]["reader_version"], "redaction": "passed"})
    print(json.dumps(event, sort_keys=True))


def cmd_migrate(env, argv):
    opts, _ = parse_args(argv, {"--operation": "str", "--source": "str"})
    try:
        result = migrate_legacy(os.getcwd(), project_id=Path(os.getcwd()).name,
                                source=opts["source"] or "", operation=opts["operation"] or "")
    except ValueError as exc:
        die(str(exc))
    print(json.dumps(result, sort_keys=True))
