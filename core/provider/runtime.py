"""Provider-specific runtime locators used by generated projections."""
from __future__ import annotations


def codex_task_plugin_root_expression() -> str:
    """Return the shared task runtime from the configured SKM marketplace.

    Codex's marketplace cache deliberately contains only declared skills, not
    the task Python runtime.  Project-selected skills therefore link to the
    canonical marketplace checkout; this locator discovers that single shared
    checkout and never falls back to a consumer-local `packages/task` copy.
    """
    return (
        "$(codex plugin marketplace list --json | python3 -c "
        "'import json,sys,pathlib; data=json.load(sys.stdin); roots=[item[\"root\"] "
        "for item in data.get(\"marketplaces\", []) if item.get(\"name\")==\"swissknifeman\" "
        "and (pathlib.Path(item[\"root\"])/\"packages/task/lib/task\").is_dir()]; "
        "len(roots)==1 or sys.exit(\"task runtime unavailable: expected one marketplace "
        "root with packages/task/lib/task\"); print(roots[0]+\"/packages/task\")')"
    )
