"""The review analytics CLI publishes the same summary in JSON and human formats."""

import json
from typing import Any

from e2e.test_execution_cli import invoke
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import seeded
from unit.execution.application._support import side as side


def test_review_roi_cli(side: Any) -> None:
    run, _, _ = seeded(side)
    args = ("analytics", "review-roi", str(run.id))
    code, out, err = invoke(side, *args, "--json", human=True)
    assert code == 0, err
    result = json.loads(out)["result"]
    assert result["run_id"] == str(run.id)
    assert result["observed_cost_usd"] is None
    assert result["finished_reviewer_steps"] == 0

    code, out, err = invoke(side, *args, human=True)
    assert code == 0, err
    assert "Completed agent reviews" in out
    assert "unavailable" in out
    assert "labeled comparison sample" in out
