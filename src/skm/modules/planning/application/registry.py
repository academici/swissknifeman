"""Bus operations of the planning module for authoring, publication, and queries (planning §7.1-§7.9, §8).

Legacy import operations belong to their owner leaves.
"""

from skm.modules.planning.application.commands import (
    abandon_draft,
    archive_plan,
    create_plan,
    design_plan,
    import_specification,
    open_draft,
    publish_revision,
    rebase_draft,
    restore_revision,
    save_draft,
)
from skm.modules.planning.application.queries import (
    diff_revisions,
    export_specification,
    get_draft,
    get_entity,
    get_plan,
    get_revision,
    list_drafts,
    list_entities,
    list_plans,
    list_revisions,
    plan_stats,
    preview_publication,
    read_text,
    ready_preview,
    resolve_plan_ref,
    simulate,
    validate_draft,
)

__all__ = ["COMMANDS", "QUERIES"]

COMMANDS = (
    create_plan.SPEC,
    design_plan.SPEC,
    open_draft.SPEC,
    save_draft.SPEC,
    abandon_draft.SPEC,
    rebase_draft.SPEC,
    publish_revision.SPEC,
    restore_revision.SPEC,
    archive_plan.SPEC,
    import_specification.SPEC,
)
QUERIES = (
    get_plan.SPEC,
    list_plans.SPEC,
    resolve_plan_ref.SPEC,
    get_draft.SPEC,
    list_drafts.SPEC,
    validate_draft.SPEC,
    get_revision.SPEC,
    list_revisions.SPEC,
    get_entity.SPEC,
    list_entities.SPEC,
    read_text.SPEC,
    preview_publication.SPEC,
    diff_revisions.SPEC,
    ready_preview.SPEC,
    simulate.SPEC,
    plan_stats.SPEC,
    export_specification.SPEC,
)
