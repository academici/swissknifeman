"""Plan intake evidence and revision linkage round-trip on both storage adapters."""

from dataclasses import replace

import pytest

from contracts.execution.harness import ExecSide, _publish_revision, exec_side
from skm.kernel.errors import SkmError
from skm.modules.planning.generated.commands import DesignPlan, DesignPlanResearchReferencesItem
from skm.modules.planning.generated.results import DesignPlanResult
from skm.modules.planning.ports import PlanRepository, RevisionRepository
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "pg_session", "test_database"]


def test_design_brief_is_scoped_pinned_and_linked_to_a_published_revision(exec_side: ExecSide) -> None:
    side = exec_side
    reference = DesignPlanResearchReferencesItem("research:goal", "sha256:" + "c" * 64)
    command = DesignPlan(
        side.plan1,
        "Define the first deliverable",
        "Context for the design",
        ("Keep compatibility",),
        (side.fv1,),
        (reference,),
        visa_policy="required",
    )
    saved = side.client.dispatch(command)
    another = side.client.dispatch(replace(command, goal="Describe a later deliverable", visa_policy=None))
    assert isinstance(saved, DesignPlanResult)
    assert isinstance(another, DesignPlanResult)
    assert another.design_brief_id != saved.design_brief_id
    with side.uow(readonly=True) as uow:
        plans = uow.repo(PlanRepository)
        brief = plans.get_design_brief(side.plan1, saved.design_brief_id)
        assert brief.visa_policy == "required"
        assert plans.get_design_brief(side.plan1, another.design_brief_id).visa_policy == "optional"
        assert brief.goal == command.goal
        assert brief.context_md == command.context_md
        assert brief.constraints == command.constraints
        assert brief.rag_file_version_ids == (side.fv1,)
        (result,) = brief.research_references
        assert (result.reference, result.content_digest) == (reference.reference, reference.content_digest)
        with pytest.raises(SkmError):
            plans.get_design_brief(side.plan2, saved.design_brief_id)

    revision = _publish_revision(
        side.app,
        side.client,
        side.owner,
        side.clock,
        side.plan1,
        {"design_brief_id": str(saved.design_brief_id)},
        "current",
    )
    with side.uow(readonly=True) as uow:
        revisions = uow.repo(RevisionRepository)
        assert revisions.get_document(revision)["design_brief_id"] == str(saved.design_brief_id)
        assert revisions.load_typed_document(revision)["design_brief_id"] == str(saved.design_brief_id)

    with pytest.raises(SkmError):
        side.client.dispatch(replace(command, rag_file_version_ids=(side.new_id(),)))
    with pytest.raises(SkmError):
        side.client.dispatch(
            replace(
                command,
                research_references=(reference, replace(reference, content_digest="sha256:" + "f" * 64)),
            )
        )
