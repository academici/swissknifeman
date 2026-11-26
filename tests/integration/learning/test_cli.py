"""All learning commands through the real CLI dispatcher in both output modes."""

from io import StringIO
from json import loads

import pytest

from contracts.knowledge.harness import KnowledgeSide, knowledge_side
from contracts.learning.test_repositories import record, session
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.ports_uow import Surface

__all__ = ["knowledge_side"]


@pytest.mark.parametrize("knowledge_side", ["memory"], indirect=True)
@pytest.mark.parametrize("json_mode", [True, False])
def test_cli_learning_surfaces(knowledge_side: KnowledgeSide, json_mode: bool) -> None:
    side = knowledge_side
    client = side.app.client(actor=side.owner, surface=Surface.CLI)
    record(side, session(side, "cli"))

    def invoke(verb: str, *args: str) -> str:
        out, err = StringIO(), StringIO()
        code = main(
            ["learning", verb, "--project", str(side.project), *args, *(["--json"] if json_mode else [])],
            stdout=out,
            stderr=err,
            environ={"HOME": "/unused"},
            backend=lambda *_: Backend(client, instance_id=side.app.instance_id),
        )
        assert code == 0, out.getvalue() + err.getvalue()
        document = out.getvalue()
        if json_mode:
            assert loads(document)["ok"]
        return document

    assert "LC-1" in invoke("candidates", "--state", "observed")
    shown = invoke("show", "LC-1")
    assert ("confidence" if json_mode else "source association") in shown
    assert "signals" in shown
    assert "review_id" in invoke("review", "LC-1", "--approve")
    assert "recomputed" in invoke("recompute")
    assert "records" in invoke("stats")
    assert "lesson_id" in invoke(
        "promote", "LC-1", "--yes", "--override-low-confidence", "--reason", "Verified in a local check"
    )
