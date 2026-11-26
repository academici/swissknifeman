#!/usr/bin/env python3
"""Merge the three state files that `project migrate` leaves as PROJECT_MIGRATE_CONFLICT.

Usage: merge-project-state.py CHECKOUT LOCAL_STATE BACKUP_DIR [--apply]

CHECKOUT/.swissknifeman/state/{events.jsonl,ext/deliveries.jsonl,ext/cursors.json} are older than the files of
LOCAL_STATE (<workspace>/projects/<code>/local/state), which were started by commands run after the new code arrived.
The two jsonl files are append-only: old bytes first, new bytes after. In cursors.json every offset of the new file
shifts by the size of the old events.jsonl. The old files are moved into BACKUP_DIR (nothing is deleted).
Without --apply it only reports. Run it while no conductor or planner of the project runs.
"""
import json
import os
import shutil
import sys


def _read(path):
    with open(path, "rb") as stream:
        return stream.read()


def _with_newline(data):
    return data + b"\n" if data and not data.endswith(b"\n") else data


def main(argv):
    args = [a for a in argv[1:] if a != "--apply"]
    apply = "--apply" in argv
    if len(args) != 3:
        print(__doc__)
        return 2
    checkout, local, backup = args
    old = os.path.join(checkout, ".swissknifeman", "state")
    events_old = _with_newline(_read(os.path.join(old, "events.jsonl")))
    events_new = _read(os.path.join(local, "events.jsonl"))
    deliveries_old = _with_newline(_read(os.path.join(old, "ext", "deliveries.jsonl")))
    deliveries_new = _read(os.path.join(local, "ext", "deliveries.jsonl"))
    cursors = json.loads(_read(os.path.join(local, "ext", "cursors.json")))
    for blob in (events_old + events_new, deliveries_old + deliveries_new):
        for line in blob.splitlines():
            json.loads(line)  # a corrupt line stops the merge before anything is written
    for subscription in cursors["subscriptions"].values():
        for key in ("offset", "last_offset"):
            if isinstance(subscription.get(key), int):
                subscription[key] += len(events_old)
    print("events %d+%d bytes, deliveries %d+%d bytes, cursors shift %d" % (
        len(events_old), len(events_new), len(deliveries_old), len(deliveries_new), len(events_old)))
    if not apply:
        print("dry run: add --apply to write")
        return 0
    os.makedirs(os.path.join(backup, "ext"), exist_ok=True)
    for name in ("events.jsonl", os.path.join("ext", "cursors.json"), os.path.join("ext", "deliveries.jsonl")):
        shutil.move(os.path.join(old, name), os.path.join(backup, name))
    with open(os.path.join(local, "events.jsonl"), "wb") as stream:
        stream.write(events_old + events_new)
    with open(os.path.join(local, "ext", "deliveries.jsonl"), "wb") as stream:
        stream.write(deliveries_old + deliveries_new)
    with open(os.path.join(local, "ext", "cursors.json"), "w", encoding="utf-8") as stream:
        stream.write(json.dumps(cursors, indent=2) + "\n")
    print("merged; run `project migrate` in the checkout again")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
