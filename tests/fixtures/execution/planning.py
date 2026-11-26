"""Draft publication inputs and a ready revision, all through the real planning facade."""

from typing import cast

from contracts.execution.harness import _publish_revision
from skm.kernel.json_types import JsonObject
from skm.modules.planning import public as planning
from skm.modules.planning.application.publication_candidate import prepare
from skm.modules.planning.domain.specification import to_document
from skm.modules.planning.generated.commands import OpenDraft, PublishRevision, SaveDraft
from skm.modules.planning.ports import DraftRepository, PlanRepository
from unit.execution.application._support import context


def ready_revision(side):
    with side.uow(readonly=True) as uow:
        document = to_document(planning.get_revision_specification(uow, side.rev2))
    for phase in cast("list[JsonObject]", document["phases"]):
        phase["design_state"] = "detailed"
    for item in cast("list[JsonObject]", document["items"]):
        item["scope"] = {"include": ["repo:src/**"], "exclude": []}
        item["deliverables"] = ["A reproducible context manifest"]
        item["reads"] = [
            {"kind": "material", "ref": "material/guide-doc", "why": "Input contract", "required": True}
        ]
    return _publish_revision(side.app, side.client, side.owner, side.clock, side.plan1, document, "current")


def draft(side, patch=None):
    opened = side.client.dispatch(OpenDraft(side.plan1, "current"), idempotency_key=f"open:{side.new_id()}")
    saved = side.client.dispatch(
        SaveDraft(
            side.plan1,
            opened.draft_id,
            opened.edit_version,
            merge_patch=patch or {"goal": "Concurrent publication"},
        ),
        idempotency_key=f"save:{side.new_id()}",
    )
    with side.uow(readonly=True) as uow:
        candidate = prepare(
            uow,
            context(side, uow),
            uow.repo(PlanRepository).get(side.plan1),
            uow.repo(DraftRepository).get(opened.draft_id),
        )
        assert not candidate.has_errors, candidate.report
    return (
        opened,
        saved,
        PublishRevision(
            side.plan1,
            opened.draft_id,
            saved.edit_version,
            candidate.content_digest,
            reason="P07.10 publication race",
        ),
    )
