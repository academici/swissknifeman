"""Shared by the subscriber fixtures: append what a delivery looked like to a JSON-lines file."""
import json
import os


def record(path, event):
    """Append one line; ``repeat`` is true when the event id was seen before (an idempotent subscriber
    would do nothing then)."""
    seen = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as handle:
            seen = {json.loads(line)["id"] for line in handle if line.strip()}
    parent = os.getppid()
    entry = {
        "id": event["id"], "type": event["type"], "subject": event.get("subject"), "repeat": event["id"] in seen,
        "attempt": os.environ.get("SKM_EVENT_ATTEMPT"), "subscription": os.environ.get("SKM_EVENT_SUBSCRIPTION"),
        "project": os.environ.get("SKM_PROJECT_ROOT"), "journal": os.environ.get("SKM_EVENT_JOURNAL"),
        "cwd": os.getcwd(), "names": sorted(os.environ), "parent": parent, "parent_sid": os.getsid(parent),
    }
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
