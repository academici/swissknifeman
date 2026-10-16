"""Record the event in OUT (argv[1]); for an event without subject "chained", emit one more event into the
same project with sync delivery (the running deliverer holds the lock, so that delivery gives way)."""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # the aicore package folder
from tests.ext.fixtures.subscribers._record import record  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "lib"))
from aicore.ext import events  # noqa: E402

event = json.load(sys.stdin)
record(sys.argv[1], event)
if event.get("subject") != "chained":
    events.emit("demo.thing.happened", source="demo", subject="chained", project=os.environ["SKM_PROJECT_ROOT"],
                delivery="sync", strict=True)
