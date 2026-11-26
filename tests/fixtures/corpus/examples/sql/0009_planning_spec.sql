-- 0009_planning_spec: typed content of published revisions. Every row is immutable.
-- Typed membership: each spec row references revision_members with its constant entity_kind, so a unit row can
-- never point at a decision member (audits/arch.md "Пример typed membership").
-- Generic links reference revision_members (workspace_id, plan_id, revision_id, entity_id): both ends are in the
-- same revision and the same plan by construction.

-- ---------------------------------------------------------------- plan-level specification
CREATE TABLE skm_planning.revision_specs (
    workspace_id          uuid  NOT NULL,
    plan_id               uuid  NOT NULL,
    revision_id           uuid  NOT NULL,
    title                 text  NOT NULL,
    goal                  text  NOT NULL,
    context_md            text  NULL,
    non_goals             jsonb NOT NULL DEFAULT '[]',   -- array of text, order kept
    rules                 jsonb NOT NULL DEFAULT '[]',   -- array of text, order kept
    design_brief_id       uuid  NULL,
    brief                 jsonb NULL,                    -- urn:skm:planning:specification:v1#/$defs/brief
    execution_constraints jsonb NOT NULL DEFAULT '{}',   -- #/$defs/execution_constraints (read by execution through the facade)
    sections              jsonb NOT NULL DEFAULT '[]',
    extensions            jsonb NOT NULL DEFAULT '{}',
    CONSTRAINT fk_revision_specs__design_brief FOREIGN KEY (workspace_id, plan_id, design_brief_id)
        REFERENCES skm_planning.plan_design_briefs (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT pk_revision_specs PRIMARY KEY (revision_id),
    CONSTRAINT fk_revision_specs__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_revision_specs__arrays CHECK (jsonb_typeof(non_goals) = 'array' AND jsonb_typeof(rules) = 'array'
        AND jsonb_typeof(sections) = 'array' AND jsonb_typeof(extensions) = 'object' AND jsonb_typeof(execution_constraints) = 'object')
);

-- ---------------------------------------------------------------- phases and batches
CREATE TABLE skm_planning.phase_specs (
    workspace_id uuid    NOT NULL,
    plan_id      uuid    NOT NULL,
    revision_id  uuid    NOT NULL,
    phase_id     uuid    NOT NULL,
    entity_kind  text    NOT NULL DEFAULT 'phase' CONSTRAINT ck_phase_specs__entity_kind_valid CHECK (entity_kind = 'phase'),
    position     integer NOT NULL CONSTRAINT ck_phase_specs__position_valid CHECK (position >= 0),
    title        text    NOT NULL,
    goal         text    NOT NULL,
    context_md   text    NULL,
    design_state text    NOT NULL CONSTRAINT ck_phase_specs__design_state_valid CHECK (design_state IN ('skeleton', 'detailed')),
    strategy     text    NOT NULL DEFAULT 'dag' CONSTRAINT ck_phase_specs__strategy_valid CHECK (strategy IN ('dag', 'sequential')),
    depends_on_declared boolean NOT NULL,          -- false: depends_on absent in the document (default = previous phase)
    contract     jsonb   NOT NULL DEFAULT '{}',    -- {consumes[], produces[], boundaries[]}
    scope        jsonb   NULL,                     -- {include[], exclude[]}
    pitfalls     jsonb   NOT NULL DEFAULT '[]',
    deliverables jsonb   NOT NULL DEFAULT '[]',
    assurance    jsonb   NULL,
    sections     jsonb   NOT NULL DEFAULT '[]',
    CONSTRAINT pk_phase_specs PRIMARY KEY (revision_id, phase_id),
    CONSTRAINT uq_phase_specs__revision_id_position UNIQUE (revision_id, position),
    CONSTRAINT fk_phase_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, phase_id, entity_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind)
);

CREATE TABLE skm_planning.batch_specs (
    workspace_id uuid    NOT NULL,
    plan_id      uuid    NOT NULL,
    revision_id  uuid    NOT NULL,
    phase_id     uuid    NOT NULL,
    batch_key    text    NOT NULL CONSTRAINT ck_batch_specs__batch_key_valid CHECK (batch_key ~ '^B[0-9A-Za-z-]+$'),
    position     integer NOT NULL CONSTRAINT ck_batch_specs__position_valid CHECK (position >= 0),
    mode         text    NOT NULL CONSTRAINT ck_batch_specs__mode_valid CHECK (mode IN ('recommended', 'required')),
    note         text    NULL,
    CONSTRAINT pk_batch_specs PRIMARY KEY (revision_id, phase_id, batch_key),
    CONSTRAINT uq_batch_specs__phase_position UNIQUE (revision_id, phase_id, position),
    CONSTRAINT fk_batch_specs__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_batch_specs__phase FOREIGN KEY (revision_id, phase_id)
        REFERENCES skm_planning.phase_specs (revision_id, phase_id)
);

-- ---------------------------------------------------------------- items
CREATE TABLE skm_planning.item_specs (
    workspace_id      uuid    NOT NULL,
    plan_id           uuid    NOT NULL,
    revision_id       uuid    NOT NULL,
    item_id           uuid    NOT NULL,
    entity_kind       text    NOT NULL DEFAULT 'item' CONSTRAINT ck_item_specs__entity_kind_valid CHECK (entity_kind = 'item'),
    phase_id          uuid    NOT NULL,
    position          integer NOT NULL CONSTRAINT ck_item_specs__position_valid CHECK (position >= 0),   -- position among all items of the revision
    title             text    NOT NULL,
    summary           text    NOT NULL,
    why               text    NOT NULL,
    work_kind         text    NOT NULL DEFAULT 'code' CONSTRAINT ck_item_specs__work_kind_valid CHECK (work_kind IN ('code', 'docs', 'research', 'config', 'test', 'review', 'ops')),
    unit_strategy     text    NOT NULL DEFAULT 'dag' CONSTRAINT ck_item_specs__unit_strategy_valid CHECK (unit_strategy IN ('dag', 'sequential')),
    authority_kind    text    NOT NULL DEFAULT 'routine' CONSTRAINT ck_item_specs__authority_kind_valid CHECK (authority_kind IN ('routine', 'owner_gate', 'external_gate')),
    authority_gate    text    NULL CONSTRAINT ck_item_specs__authority_gate_valid CHECK (authority_gate ~ '^[A-Z0-9][A-Z0-9._-]*$'),
    authority_label   text    NULL,
    authority_scope   text    NULL,
    research_need     text    NOT NULL DEFAULT 'none' CONSTRAINT ck_item_specs__research_need_valid CHECK (research_need IN ('none', 'optional', 'required')),
    research_question text    NULL,
    route             jsonb   NULL,                 -- preferences {class, effort, runtime?, model?, correction?}
    scope             jsonb   NULL,
    rules             jsonb   NOT NULL DEFAULT '[]',
    guidance_md       text    NULL,
    deliverables      jsonb   NOT NULL DEFAULT '[]',
    sections          jsonb   NOT NULL DEFAULT '[]',
    -- batch membership lives only in batch_members (one authoritative place, keeps the order inside the batch)
    CONSTRAINT pk_item_specs PRIMARY KEY (revision_id, item_id),
    CONSTRAINT uq_item_specs__revision_id_position UNIQUE (revision_id, position),
    CONSTRAINT fk_item_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, item_id, entity_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind),
    CONSTRAINT fk_item_specs__phase FOREIGN KEY (revision_id, phase_id)
        REFERENCES skm_planning.phase_specs (revision_id, phase_id),
    CONSTRAINT ck_item_specs__gate CHECK (
        (authority_kind = 'routine' AND authority_gate IS NULL AND authority_label IS NULL AND authority_scope IS NULL)
        OR (authority_kind <> 'routine' AND authority_scope IS NOT NULL
            AND ((authority_gate IS NULL) <> (authority_label IS NULL))))
);
CREATE INDEX ix_item_specs__revision_id_phase_id_position ON skm_planning.item_specs (revision_id, phase_id, position, item_id);

-- ---------------------------------------------------------------- units
CREATE TABLE skm_planning.unit_specs (
    workspace_id    uuid    NOT NULL,
    plan_id         uuid    NOT NULL,
    revision_id     uuid    NOT NULL,
    unit_id         uuid    NOT NULL,
    entity_kind     text    NOT NULL DEFAULT 'unit' CONSTRAINT ck_unit_specs__entity_kind_valid CHECK (entity_kind = 'unit'),
    item_id         uuid    NOT NULL,
    parent_unit_id  uuid    NULL,
    position        integer NOT NULL CONSTRAINT ck_unit_specs__position_valid CHECK (position >= 0),   -- position inside the item
    local_key       text    NOT NULL CONSTRAINT ck_unit_specs__local_key_valid CHECK (local_key ~ '^U[0-9]+$'),
    title           text    NOT NULL,
    goal            text    NOT NULL,
    unit_kind       text    NOT NULL DEFAULT 'implementation'
        CONSTRAINT ck_unit_specs__invariant_valid CHECK (unit_kind IN ('preparation', 'implementation', 'review', 'verification', 'integration', 'command')),
    work_kind       text    NULL CONSTRAINT ck_unit_specs__work_kind_valid CHECK (work_kind IN ('code', 'docs', 'research', 'config', 'test', 'review', 'ops')),
    mode            text    NOT NULL DEFAULT 'either' CONSTRAINT ck_unit_specs__mode_valid CHECK (mode IN ('self', 'delegate', 'either')),
    route           jsonb   NULL,
    instructions_md text    NULL,
    command         jsonb   NULL,          -- {kind: command|shell, definition} for unit_kind = command
    sections        jsonb   NOT NULL DEFAULT '[]',
    CONSTRAINT pk_unit_specs PRIMARY KEY (revision_id, unit_id),
    CONSTRAINT uq_unit_specs__item_local_key UNIQUE (revision_id, item_id, local_key),
    CONSTRAINT uq_unit_specs__item_position UNIQUE (revision_id, item_id, position),
    CONSTRAINT uq_unit_specs__revision_item_unit UNIQUE (revision_id, item_id, unit_id),
    CONSTRAINT fk_unit_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, unit_id, entity_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind),
    CONSTRAINT fk_unit_specs__item FOREIGN KEY (revision_id, item_id)
        REFERENCES skm_planning.item_specs (revision_id, item_id),
    -- the parent is another unit of the same item
    CONSTRAINT fk_unit_specs__parent FOREIGN KEY (revision_id, item_id, parent_unit_id)
        REFERENCES skm_planning.unit_specs (revision_id, item_id, unit_id),
    CONSTRAINT ck_unit_specs__no_self_parent CHECK (parent_unit_id IS NULL OR parent_unit_id <> unit_id),
    CONSTRAINT ck_unit_specs__command CHECK ((unit_kind = 'command') = (command IS NOT NULL))
);
CREATE INDEX ix_unit_specs__revision_id_item_id_position ON skm_planning.unit_specs (revision_id, item_id, position, unit_id);

-- ---------------------------------------------------------------- requirements, criteria, decisions, materials
CREATE TABLE skm_planning.requirement_specs (
    workspace_id   uuid    NOT NULL,
    plan_id        uuid    NOT NULL,
    revision_id    uuid    NOT NULL,
    requirement_id uuid    NOT NULL,
    entity_kind    text    NOT NULL DEFAULT 'requirement' CONSTRAINT ck_requirement_specs__entity_kind_valid CHECK (entity_kind = 'requirement'),
    position       integer NOT NULL CONSTRAINT ck_requirement_specs__position_valid CHECK (position >= 0),
    statement      text    NOT NULL,
    priority       text    NOT NULL CONSTRAINT ck_requirement_specs__priority_valid CHECK (priority IN ('must', 'should', 'could')),
    source_kind    text    NOT NULL CONSTRAINT ck_requirement_specs__source_kind_valid CHECK (source_kind IN ('brief_message', 'owner', 'derived', 'external')),
    source_ref     text    NULL,
    CONSTRAINT pk_requirement_specs PRIMARY KEY (revision_id, requirement_id),
    CONSTRAINT fk_requirement_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, requirement_id, entity_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind)
);

CREATE TABLE skm_planning.check_specs (
    workspace_id            uuid    NOT NULL,
    plan_id                 uuid    NOT NULL,
    revision_id             uuid    NOT NULL,
    check_id                uuid    NOT NULL,
    entity_kind             text    NOT NULL DEFAULT 'check' CONSTRAINT ck_check_specs__entity_kind_valid CHECK (entity_kind = 'check'),
    owner_entity_id         uuid    NOT NULL,
    owner_kind              text    NOT NULL CONSTRAINT ck_check_specs__owner_kind_valid CHECK (owner_kind IN ('phase', 'item')),
    local_key               text    NOT NULL CONSTRAINT ck_check_specs__local_key_valid CHECK (local_key ~ '^V[0-9]+$'),
    position                integer NOT NULL CONSTRAINT ck_check_specs__position_valid CHECK (position >= 0),
    title                   text    NULL,
    kind                    text    NOT NULL CONSTRAINT ck_check_specs__kind_valid CHECK (kind IN ('command', 'shell', 'manual', 'external')),
    category                text    NOT NULL CONSTRAINT ck_check_specs__category_valid CHECK (category IN ('acceptance', 'impact', 'live')),
    required                boolean NOT NULL,
    rerun_after_integration boolean NOT NULL DEFAULT false,
    definition              jsonb   NOT NULL,   -- by kind: #/$defs/{command,shell,manual,external}_definition
    evidence_policy         jsonb   NULL,
    CONSTRAINT pk_check_specs PRIMARY KEY (revision_id, check_id),
    CONSTRAINT uq_check_specs__owner_local_key UNIQUE (revision_id, owner_entity_id, local_key),
    CONSTRAINT fk_check_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, check_id, entity_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind),
    CONSTRAINT fk_check_specs__owner FOREIGN KEY (workspace_id, plan_id, revision_id, owner_entity_id, owner_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind)
);
CREATE INDEX ix_check_specs__revision_id_owner_entity_id ON skm_planning.check_specs (revision_id, owner_entity_id);

CREATE TABLE skm_planning.acceptance_criteria (
    workspace_id      uuid    NOT NULL,
    plan_id           uuid    NOT NULL,
    revision_id       uuid    NOT NULL,
    criterion_id      uuid    NOT NULL,
    entity_kind       text    NOT NULL DEFAULT 'criterion' CONSTRAINT ck_acceptance_criteria__entity_kind_valid CHECK (entity_kind = 'criterion'),
    owner_entity_id   uuid    NOT NULL,
    owner_kind        text    NOT NULL CONSTRAINT ck_acceptance_criteria__owner_kind_valid CHECK (owner_kind IN ('item', 'unit')),
    position          integer NOT NULL CONSTRAINT ck_acceptance_criteria__position_valid CHECK (position >= 0),
    statement         text    NOT NULL,
    verification_mode text    NOT NULL CONSTRAINT ck_acceptance_criteria__verification_mode_valid CHECK (verification_mode IN ('check', 'review', 'manual')),
    CONSTRAINT pk_acceptance_criteria PRIMARY KEY (revision_id, criterion_id),
    CONSTRAINT fk_acceptance_criteria__member FOREIGN KEY (workspace_id, plan_id, revision_id, criterion_id, entity_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind),
    CONSTRAINT fk_acceptance_criteria__owner FOREIGN KEY (workspace_id, plan_id, revision_id, owner_entity_id, owner_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind)
);
CREATE INDEX ix_acceptance_criteria__revision_id_owner_entity_id ON skm_planning.acceptance_criteria (revision_id, owner_entity_id);

CREATE TABLE skm_planning.decision_specs (
    workspace_id uuid    NOT NULL,
    plan_id      uuid    NOT NULL,
    revision_id  uuid    NOT NULL,
    decision_id  uuid    NOT NULL,
    entity_kind  text    NOT NULL DEFAULT 'decision' CONSTRAINT ck_decision_specs__entity_kind_valid CHECK (entity_kind = 'decision'),
    position     integer NOT NULL CONSTRAINT ck_decision_specs__position_valid CHECK (position >= 0),
    title        text    NOT NULL,
    state        text    NOT NULL CONSTRAINT ck_decision_specs__state_valid CHECK (state IN ('open', 'proposed', 'accepted', 'rejected', 'superseded')),
    source_date  date    NULL,                     -- historical date only, never a fabricated time
    question     text    NULL,
    options      jsonb   NOT NULL DEFAULT '[]',    -- [{key A-Z, text}]
    context_md   text    NULL,
    decision     text    NULL,
    rationale    text    NULL,
    consequences jsonb   NOT NULL DEFAULT '[]',
    is_global    boolean NOT NULL DEFAULT false,
    evidence     jsonb   NOT NULL DEFAULT '[]',
    origin_kind  text    NULL CONSTRAINT ck_decision_specs__origin_kind_valid CHECK (origin_kind IN ('owner', 'agent', 'advice', 'panel', 'import')),
    origin_ref   text    NULL,
    answered_by  text    NULL CONSTRAINT ck_decision_specs__answered_by_valid CHECK (answered_by IN ('owner', 'agent')),
    sections     jsonb   NOT NULL DEFAULT '[]',
    CONSTRAINT pk_decision_specs PRIMARY KEY (revision_id, decision_id),
    CONSTRAINT fk_decision_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, decision_id, entity_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind),
    CONSTRAINT ck_decision_specs__fields CHECK (
        (state <> 'open' OR question IS NOT NULL)
        AND (state NOT IN ('proposed', 'accepted') OR (decision IS NOT NULL AND rationale IS NOT NULL)))
);

CREATE TABLE skm_planning.decision_supersessions (
    workspace_id           uuid NOT NULL,
    plan_id                uuid NOT NULL,
    revision_id            uuid NOT NULL,
    decision_id            uuid NOT NULL,
    superseded_decision_id uuid NOT NULL,
    CONSTRAINT pk_decision_supersessions PRIMARY KEY (revision_id, decision_id, superseded_decision_id),
    CONSTRAINT fk_decision_supersessions__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_decision_supersessions__decision FOREIGN KEY (revision_id, decision_id)
        REFERENCES skm_planning.decision_specs (revision_id, decision_id),
    CONSTRAINT fk_decision_supersessions__superseded FOREIGN KEY (revision_id, superseded_decision_id)
        REFERENCES skm_planning.decision_specs (revision_id, decision_id),
    CONSTRAINT ck_decision_supersessions__no_self CHECK (decision_id <> superseded_decision_id)
);

CREATE TABLE skm_planning.decision_bindings (
    workspace_id uuid NOT NULL,
    plan_id      uuid NOT NULL,
    revision_id  uuid NOT NULL,
    decision_id  uuid NOT NULL,
    entity_id    uuid NOT NULL,
    binding_kind text NOT NULL CONSTRAINT ck_decision_bindings__binding_kind_valid CHECK (binding_kind IN ('applies_to', 'cited_by')),
    CONSTRAINT pk_decision_bindings PRIMARY KEY (revision_id, decision_id, entity_id, binding_kind),
    CONSTRAINT fk_decision_bindings__decision FOREIGN KEY (revision_id, decision_id)
        REFERENCES skm_planning.decision_specs (revision_id, decision_id),
    CONSTRAINT fk_decision_bindings__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id)
);
CREATE INDEX ix_decision_bindings__revision_id_entity_id ON skm_planning.decision_bindings (revision_id, entity_id);

CREATE TABLE skm_planning.material_specs (
    workspace_id   uuid    NOT NULL,
    plan_id        uuid    NOT NULL,
    revision_id    uuid    NOT NULL,
    material_id    uuid    NOT NULL,
    entity_kind    text    NOT NULL DEFAULT 'material' CONSTRAINT ck_material_specs__entity_kind_valid CHECK (entity_kind = 'material'),
    position       integer NOT NULL CONSTRAINT ck_material_specs__position_valid CHECK (position >= 0),
    title          text    NOT NULL,
    kind           text    NOT NULL CONSTRAINT ck_material_specs__kind_valid CHECK (kind IN ('file_version', 'repository_path', 'external_source')),
    role           text    NOT NULL CONSTRAINT ck_material_specs__role_valid CHECK (role IN ('input', 'reference')),
    required_for   text[]  NOT NULL DEFAULT '{}',      -- stages that wait (BLOCKED_BY_MATERIAL) while the material is unavailable or stale
    freshness_policy    text    NOT NULL DEFAULT 'pinned' CONSTRAINT ck_material_specs__freshness_policy_valid CHECK (freshness_policy IN ('pinned', 'latest_at_publish', 'must_refresh')),
    freshness_max_age_s integer NULL CONSTRAINT ck_material_specs__freshness_max_age_s_valid CHECK (freshness_max_age_s BETWEEN 60 AND 31536000),
    why            text    NULL,
    is_global      boolean NOT NULL DEFAULT false,
    mount_name     text    NULL,
    path           text    NULL,
    external_url   text    NULL,
    retrieved_at   timestamptz NULL,
    content_digest text    NULL CONSTRAINT ck_material_specs__content_digest_valid CHECK (content_digest ~ '^sha256:[0-9a-f]{64}$'),
    selector       jsonb   NULL,
    CONSTRAINT pk_material_specs PRIMARY KEY (revision_id, material_id),
    CONSTRAINT uq_material_specs__scope UNIQUE (workspace_id, plan_id, revision_id, material_id),
    CONSTRAINT fk_material_specs__member FOREIGN KEY (workspace_id, plan_id, revision_id, material_id, entity_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind),
    CONSTRAINT ck_material_specs__required_for CHECK (required_for <@ ARRAY['execution', 'review', 'acceptance']::text[]),
    CONSTRAINT ck_material_specs__max_age CHECK ((freshness_policy = 'must_refresh') = (freshness_max_age_s IS NOT NULL)),
    -- repository_path: content at the run baseline (pinned only); external_source: no latest_at_publish (planning never fetches)
    CONSTRAINT ck_material_specs__freshness_kind CHECK (
        (kind = 'file_version')
     OR (kind = 'repository_path' AND freshness_policy = 'pinned')
     OR (kind = 'external_source' AND freshness_policy IN ('pinned', 'must_refresh'))),
    -- exactly the columns of the kind are filled; the file_version pin lives in revision_file_bindings (0011)
    CONSTRAINT ck_material_specs__target CHECK (
        (kind = 'file_version'    AND mount_name IS NULL AND path IS NULL AND external_url IS NULL)
     OR (kind = 'repository_path' AND mount_name IS NOT NULL AND path IS NOT NULL AND external_url IS NULL)
     OR (kind = 'external_source' AND mount_name IS NULL AND path IS NULL AND external_url IS NOT NULL))
);

CREATE TABLE skm_planning.material_bindings (
    workspace_id uuid NOT NULL,
    plan_id      uuid NOT NULL,
    revision_id  uuid NOT NULL,
    material_id  uuid NOT NULL,
    entity_id    uuid NOT NULL,
    CONSTRAINT pk_material_bindings PRIMARY KEY (revision_id, material_id, entity_id),
    CONSTRAINT fk_material_bindings__material FOREIGN KEY (revision_id, material_id)
        REFERENCES skm_planning.material_specs (revision_id, material_id),
    CONSTRAINT fk_material_bindings__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id)
);

-- ---------------------------------------------------------------- links
CREATE TABLE skm_planning.entity_requirement_links (
    workspace_id   uuid NOT NULL,
    plan_id        uuid NOT NULL,
    revision_id    uuid NOT NULL,
    entity_id      uuid NOT NULL,
    requirement_id uuid NOT NULL,
    relation       text NOT NULL CONSTRAINT ck_entity_requirement_links__relation_valid CHECK (relation IN ('implements', 'verifies', 'owns')),
    CONSTRAINT pk_entity_requirement_links PRIMARY KEY (revision_id, entity_id, requirement_id, relation),
    CONSTRAINT fk_entity_requirement_links__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id),
    CONSTRAINT fk_entity_requirement_links__requirement FOREIGN KEY (revision_id, requirement_id)
        REFERENCES skm_planning.requirement_specs (revision_id, requirement_id)
);
CREATE INDEX ix_entity_requirement_links__revision_id_requirement_id ON skm_planning.entity_requirement_links (revision_id, requirement_id);

-- dependent -> prerequisite (B depends_on A: dependent = B, prerequisite = A)
CREATE TABLE skm_planning.dependency_edges (
    workspace_id           uuid    NOT NULL,
    plan_id                uuid    NOT NULL,
    revision_id            uuid    NOT NULL,
    dependent_entity_id    uuid    NOT NULL,
    prerequisite_entity_id uuid    NOT NULL,
    dependency_kind        text    NOT NULL CONSTRAINT ck_dependency_edges__dependency_kind_valid CHECK (dependency_kind IN ('phase_depends_on', 'item_depends_on', 'unit_depends_on')),   -- unit parent: unit_specs.parent_unit_id
    implicit               boolean NOT NULL DEFAULT false,   -- true only for the default "previous phase" dependency
    CONSTRAINT pk_dependency_edges PRIMARY KEY (revision_id, dependent_entity_id, prerequisite_entity_id, dependency_kind),
    CONSTRAINT fk_dependency_edges__dependent FOREIGN KEY (workspace_id, plan_id, revision_id, dependent_entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id),
    CONSTRAINT fk_dependency_edges__prerequisite FOREIGN KEY (workspace_id, plan_id, revision_id, prerequisite_entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id),
    CONSTRAINT ck_dependency_edges__no_self CHECK (dependent_entity_id <> prerequisite_entity_id),
    CONSTRAINT ck_dependency_edges__implicit CHECK (NOT implicit OR dependency_kind = 'phase_depends_on')
);
CREATE INDEX ix_dependency_edges__revision_id_prerequisite ON skm_planning.dependency_edges (revision_id, prerequisite_entity_id);

CREATE TABLE skm_planning.entity_relations (
    workspace_id     uuid    NOT NULL,
    plan_id          uuid    NOT NULL,
    revision_id      uuid    NOT NULL,
    source_entity_id uuid    NOT NULL,
    target_entity_id uuid    NOT NULL,
    relation         text    NOT NULL CONSTRAINT ck_entity_relations__relation_valid CHECK (relation IN ('informs', 'consumes', 'conflicts', 'follows_up', 'supersedes')),
    position         integer NOT NULL CONSTRAINT ck_entity_relations__position_valid CHECK (position >= 0),
    note             text    NULL,
    CONSTRAINT pk_entity_relations PRIMARY KEY (revision_id, source_entity_id, target_entity_id, relation),
    CONSTRAINT fk_entity_relations__source FOREIGN KEY (workspace_id, plan_id, revision_id, source_entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id),
    CONSTRAINT fk_entity_relations__target FOREIGN KEY (workspace_id, plan_id, revision_id, target_entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id),
    CONSTRAINT ck_entity_relations__no_self CHECK (source_entity_id <> target_entity_id)
);

CREATE TABLE skm_planning.batch_members (
    workspace_id uuid    NOT NULL,
    plan_id      uuid    NOT NULL,
    revision_id  uuid    NOT NULL,
    phase_id     uuid    NOT NULL,
    batch_key    text    NOT NULL,
    item_id      uuid    NOT NULL,
    position     integer NOT NULL CONSTRAINT ck_batch_members__position_valid CHECK (position >= 0),
    CONSTRAINT pk_batch_members PRIMARY KEY (revision_id, phase_id, batch_key, item_id),
    CONSTRAINT uq_batch_members__item UNIQUE (revision_id, item_id),         -- an item is in at most one batch
    CONSTRAINT fk_batch_members__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_batch_members__batch FOREIGN KEY (revision_id, phase_id, batch_key)
        REFERENCES skm_planning.batch_specs (revision_id, phase_id, batch_key),
    CONSTRAINT fk_batch_members__item FOREIGN KEY (revision_id, item_id)
        REFERENCES skm_planning.item_specs (revision_id, item_id)
);

CREATE TABLE skm_planning.entity_check_bindings (
    workspace_id uuid NOT NULL,
    plan_id      uuid NOT NULL,
    revision_id  uuid NOT NULL,
    entity_id    uuid NOT NULL,       -- unit that is gated by an item check
    check_id     uuid NOT NULL,
    binding_role text NOT NULL DEFAULT 'gate' CONSTRAINT ck_entity_check_bindings__binding_role_valid CHECK (binding_role IN ('gate', 'advisory')),
    CONSTRAINT pk_entity_check_bindings PRIMARY KEY (revision_id, entity_id, check_id),
    CONSTRAINT fk_entity_check_bindings__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id),
    CONSTRAINT fk_entity_check_bindings__check FOREIGN KEY (revision_id, check_id)
        REFERENCES skm_planning.check_specs (revision_id, check_id)
);

CREATE TABLE skm_planning.criterion_check_bindings (
    workspace_id uuid NOT NULL,
    plan_id      uuid NOT NULL,
    revision_id  uuid NOT NULL,
    criterion_id uuid NOT NULL,
    check_id     uuid NOT NULL,
    CONSTRAINT pk_criterion_check_bindings PRIMARY KEY (revision_id, criterion_id, check_id),
    CONSTRAINT fk_criterion_check_bindings__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_criterion_check_bindings__criterion FOREIGN KEY (revision_id, criterion_id)
        REFERENCES skm_planning.acceptance_criteria (revision_id, criterion_id),
    CONSTRAINT fk_criterion_check_bindings__check FOREIGN KEY (revision_id, check_id)
        REFERENCES skm_planning.check_specs (revision_id, check_id)
);

CREATE TABLE skm_planning.review_requirements (
    workspace_id      uuid    NOT NULL,
    plan_id           uuid    NOT NULL,
    revision_id       uuid    NOT NULL,
    owner_entity_id   uuid    NOT NULL,     -- the item
    owner_kind        text    NOT NULL DEFAULT 'item' CONSTRAINT ck_review_requirements__owner_kind_valid CHECK (owner_kind = 'item'),
    mode              text    NOT NULL CONSTRAINT ck_review_requirements__mode_valid CHECK (mode IN ('required', 'self', 'waived')),
    profile_key       text    NULL,
    independence      text    NULL CONSTRAINT ck_review_requirements__independence_valid CHECK (independence IN ('separate_session', 'separate_runtime', 'human')),
    reviewer          jsonb   NULL,
    max_rounds        integer NULL CONSTRAINT ck_review_requirements__max_rounds_valid CHECK (max_rounds BETWEEN 1 AND 10),
    covers            jsonb   NOT NULL DEFAULT '[]',   -- informational list of item keys a reviewer reads; not executed
    required_evidence text[]  NOT NULL DEFAULT '{}',
    reason            text    NULL,
    waived_by         text    NULL,
    CONSTRAINT pk_review_requirements PRIMARY KEY (revision_id, owner_entity_id),
    CONSTRAINT fk_review_requirements__owner FOREIGN KEY (workspace_id, plan_id, revision_id, owner_entity_id, owner_kind)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind),
    CONSTRAINT ck_review_requirements__mode CHECK (
        (mode = 'required' AND reason IS NULL AND waived_by IS NULL)
     OR (mode = 'self' AND reason IS NOT NULL AND waived_by IS NULL)
     OR (mode = 'waived' AND reason IS NOT NULL AND waived_by IS NOT NULL))
);

CREATE TABLE skm_planning.entity_path_specs (
    workspace_id uuid    NOT NULL,
    plan_id      uuid    NOT NULL,
    revision_id  uuid    NOT NULL,
    entity_id    uuid    NOT NULL,
    role         text    NOT NULL CONSTRAINT ck_entity_path_specs__role_valid CHECK (role IN ('change_hint', 'declared_write_scope', 'output')),
    position     integer NOT NULL CONSTRAINT ck_entity_path_specs__position_valid CHECK (position >= 0),
    mount_name   text    NOT NULL CONSTRAINT ck_entity_path_specs__mount_name_valid CHECK (mount_name ~ '^[a-z0-9][a-z0-9-]{0,62}$'),
    pattern      text    NOT NULL CONSTRAINT ck_entity_path_specs__pattern_valid CHECK (pattern !~ '^(/|~|[A-Za-z]:)' AND pattern !~ '(^|/)\.\.(/|$)'),
    change       text    NULL CONSTRAINT ck_entity_path_specs__change_valid CHECK (change IN ('create', 'modify', 'delete', 'any')),
    note         text    NULL,
    CONSTRAINT pk_entity_path_specs PRIMARY KEY (revision_id, entity_id, role, position),
    CONSTRAINT fk_entity_path_specs__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id),
    CONSTRAINT ck_entity_path_specs__change CHECK ((role = 'change_hint') = (change IS NOT NULL))
);

CREATE TABLE skm_planning.artifact_specs (
    workspace_id uuid    NOT NULL,
    plan_id      uuid    NOT NULL,
    revision_id  uuid    NOT NULL,
    item_id      uuid    NOT NULL,
    position     integer NOT NULL CONSTRAINT ck_artifact_specs__position_valid CHECK (position >= 0),
    artifact_key text    NULL CONSTRAINT ck_artifact_specs__artifact_key_valid CHECK (artifact_key ~ '^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$'),
    role         text    NOT NULL CONSTRAINT ck_artifact_specs__role_valid CHECK (role IN ('input', 'output')),
    mount_name   text    NOT NULL,
    path         text    NOT NULL,
    note         text    NULL,
    CONSTRAINT pk_artifact_specs PRIMARY KEY (revision_id, item_id, position),
    CONSTRAINT fk_artifact_specs__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_artifact_specs__item FOREIGN KEY (revision_id, item_id)
        REFERENCES skm_planning.item_specs (revision_id, item_id)
);
-- an output artifact key is declared once per revision
CREATE UNIQUE INDEX uq_artifact_specs__output_key ON skm_planning.artifact_specs (revision_id, artifact_key)
    WHERE role = 'output' AND artifact_key IS NOT NULL;

CREATE TABLE skm_planning.entity_read_specs (
    workspace_id      uuid    NOT NULL,
    plan_id           uuid    NOT NULL,
    revision_id       uuid    NOT NULL,
    entity_id         uuid    NOT NULL,     -- phase (supporting), item or unit
    purpose           text    NOT NULL CONSTRAINT ck_entity_read_specs__purpose_valid CHECK (purpose IN ('read', 'example', 'supporting')),
    position          integer NOT NULL CONSTRAINT ck_entity_read_specs__position_valid CHECK (position >= 0),
    target_kind       text    NOT NULL CONSTRAINT ck_entity_read_specs__target_kind_valid CHECK (target_kind IN ('repository_path', 'material', 'plan_entity', 'artifact', 'external_source')),
    mount_name        text    NULL,
    path              text    NULL,
    section           text    NULL,
    material_id       uuid    NULL,
    material_section  text    NULL,
    target_entity_id  uuid    NULL,
    artifact_key      text    NULL,
    external_url      text    NULL,
    required          boolean NOT NULL,
    why               text    NOT NULL,
    CONSTRAINT pk_entity_read_specs PRIMARY KEY (revision_id, entity_id, purpose, position),
    CONSTRAINT fk_entity_read_specs__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id),
    CONSTRAINT fk_entity_read_specs__material FOREIGN KEY (revision_id, material_id)
        REFERENCES skm_planning.material_specs (revision_id, material_id),
    CONSTRAINT fk_entity_read_specs__target FOREIGN KEY (workspace_id, plan_id, revision_id, target_entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id),
    -- exactly one target per kind (audits/arch.md "ровно один target")
    CONSTRAINT ck_entity_read_specs__target CHECK (
        (target_kind = 'repository_path' AND mount_name IS NOT NULL AND path IS NOT NULL
             AND material_id IS NULL AND target_entity_id IS NULL AND artifact_key IS NULL AND external_url IS NULL)
     OR (target_kind = 'material' AND material_id IS NOT NULL
             AND mount_name IS NULL AND path IS NULL AND target_entity_id IS NULL AND artifact_key IS NULL AND external_url IS NULL)
     OR (target_kind = 'plan_entity' AND target_entity_id IS NOT NULL
             AND mount_name IS NULL AND path IS NULL AND material_id IS NULL AND artifact_key IS NULL AND external_url IS NULL)
     OR (target_kind = 'artifact' AND artifact_key IS NOT NULL
             AND mount_name IS NULL AND path IS NULL AND material_id IS NULL AND target_entity_id IS NULL AND external_url IS NULL)
     OR (target_kind = 'external_source' AND external_url IS NOT NULL
             AND mount_name IS NULL AND path IS NULL AND material_id IS NULL AND target_entity_id IS NULL AND artifact_key IS NULL))
);

CREATE TABLE skm_planning.entity_skill_requirements (
    workspace_id       uuid    NOT NULL,
    plan_id            uuid    NOT NULL,
    revision_id        uuid    NOT NULL,
    entity_id          uuid    NOT NULL,
    resource_key       text    NOT NULL CONSTRAINT ck_entity_skill_requirements__resource_key_valid CHECK (resource_key ~ '^[a-z][a-z0-9-]*(?:(?::|/)[a-z][a-z0-9-]*)?$'),
    version_constraint text    NULL,
    position           integer NOT NULL CONSTRAINT ck_entity_skill_requirements__position_valid CHECK (position >= 0),
    CONSTRAINT pk_entity_skill_requirements PRIMARY KEY (revision_id, entity_id, resource_key),
    CONSTRAINT fk_entity_skill_requirements__entity FOREIGN KEY (workspace_id, plan_id, revision_id, entity_id)
        REFERENCES skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id)
);

CREATE TABLE skm_planning.plan_relations (
    workspace_id   uuid    NOT NULL,
    plan_id        uuid    NOT NULL,
    revision_id    uuid    NOT NULL,
    position       integer NOT NULL CONSTRAINT ck_plan_relations__position_valid CHECK (position >= 0),
    kind           text    NOT NULL CONSTRAINT ck_plan_relations__kind_valid CHECK (kind IN ('predecessor', 'supersedes', 'related')),
    target_plan_id uuid    NULL,           -- resolved at publish when the target exists in the project
    target_ref     text    NOT NULL,       -- as written (PLAN<n> or plan:<uuid>); unresolved refs are kept, never dropped
    note           text    NULL,
    CONSTRAINT pk_plan_relations PRIMARY KEY (revision_id, position),
    CONSTRAINT fk_plan_relations__revision FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id),
    CONSTRAINT fk_plan_relations__target FOREIGN KEY (workspace_id, target_plan_id)
        REFERENCES skm_planning.plans (workspace_id, id),
    CONSTRAINT ck_plan_relations__no_self CHECK (target_plan_id IS NULL OR target_plan_id <> plan_id)
);
CREATE INDEX ix_plan_relations__target_plan_id ON skm_planning.plan_relations (target_plan_id) WHERE target_plan_id IS NOT NULL;

-- ---------------------------------------------------------------- immutability of every content table
DO $$
DECLARE t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['revision_specs', 'phase_specs', 'batch_specs', 'item_specs', 'unit_specs', 'requirement_specs',
        'check_specs', 'acceptance_criteria', 'decision_specs', 'decision_supersessions', 'decision_bindings',
        'material_specs', 'material_bindings', 'entity_requirement_links', 'dependency_edges', 'entity_relations',
        'batch_members', 'entity_check_bindings', 'criterion_check_bindings', 'review_requirements',
        'entity_path_specs', 'artifact_specs', 'entity_read_specs', 'entity_skill_requirements', 'plan_relations']
    LOOP
        EXECUTE format('CREATE TRIGGER tg_%1$s__immutable BEFORE UPDATE OR DELETE ON skm_planning.%1$s
                        FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable()', t);
    END LOOP;
END;
$$;

SELECT skm_core.grant_app('skm_planning', ARRAY['acceptance_criteria','artifact_specs','batch_members','batch_specs','check_specs','criterion_check_bindings','decision_bindings','decision_specs','decision_supersessions','dependency_edges','entity_check_bindings','entity_path_specs','entity_read_specs','entity_relations','entity_requirement_links','entity_skill_requirements','item_specs','material_bindings','material_specs','phase_specs','plan_aliases','plan_design_briefs','plan_entity_identities','plan_relations','plan_revisions','requirement_specs','review_requirements','revision_members','revision_payloads','revision_specs','unit_specs']::text[]);
