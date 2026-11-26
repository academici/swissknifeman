-- 0008_planning_identity: plan identity, aliases, drafts, immutable revisions, entity identities, revision members.
-- Owner module: planning. FKs only to skm_core and skm_workspace (ADR 0003).
-- Conventions: spec/00-conventions.md §1.4. Data model: 05-data-model.md §8, spec/modules/planning.md §11.

CREATE SCHEMA IF NOT EXISTS skm_planning;

-- Shared trigger function: rows of a published revision never change.
CREATE FUNCTION skm_planning.tg_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'skm_planning.%: rows are immutable (published revision content)', TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END;
$$;

-- ---------------------------------------------------------------- plans
CREATE TABLE skm_planning.plans (
    workspace_id        uuid        NOT NULL,
    project_id          uuid        NOT NULL,
    id                  uuid        NOT NULL REFERENCES skm_core.scopes (id),
    title               text        NOT NULL CONSTRAINT ck_plans__title_valid CHECK (length(title) BETWEEN 1 AND 300),
    lifecycle_state     text        NOT NULL DEFAULT 'active',
    purpose             text        NOT NULL DEFAULT 'standard',   -- review_requests: system plan of execution.request_review (D-EX-1)
    current_revision_id uuid        NULL,
    next_revision_no    integer     NOT NULL DEFAULT 1,
    row_version         bigint      NOT NULL DEFAULT 1,
    created_by          uuid        NOT NULL,          -- principal id (no FK: access is not a direct dependency; principals are never deleted)
    created_at          timestamptz NOT NULL,
    updated_at          timestamptz NOT NULL,
    archived_at         timestamptz NULL,
    CONSTRAINT pk_plans PRIMARY KEY (id),
    CONSTRAINT uq_plans__workspace_id_id UNIQUE (workspace_id, id),
    CONSTRAINT uq_plans__workspace_id_project_id_id UNIQUE (workspace_id, project_id, id),
    CONSTRAINT fk_plans__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_plans__lifecycle_state CHECK (lifecycle_state IN ('active', 'archived')),
    CONSTRAINT ck_plans__purpose CHECK (purpose IN ('standard', 'review_requests')),
    CONSTRAINT ck_plans__next_revision_no CHECK (next_revision_no >= 1),
    CONSTRAINT ck_plans__archived_at CHECK ((lifecycle_state = 'archived') = (archived_at IS NOT NULL))
);
CREATE INDEX ix_plans__workspace_id_project_id_lifecycle_state_updated_at_id
    ON skm_planning.plans (workspace_id, project_id, lifecycle_state, updated_at DESC, id DESC);
-- at most one system review-requests plan per project
CREATE UNIQUE INDEX uq_plans__project_id_review_requests ON skm_planning.plans (project_id) WHERE purpose = 'review_requests';

-- ---------------------------------------------------------------- plan design intake (immutable)
CREATE TABLE skm_planning.plan_design_briefs (
    id           uuid        NOT NULL,
    workspace_id uuid        NOT NULL,
    plan_id      uuid        NOT NULL,
    goal         text        NOT NULL,
    context_md   text        NULL,
    constraints  text[]      NOT NULL DEFAULT '{}',
    created_by   uuid        NOT NULL,
    created_at   timestamptz NOT NULL,
    CONSTRAINT pk_plan_design_briefs PRIMARY KEY (id),
    CONSTRAINT uq_plan_design_briefs__scope_id UNIQUE (workspace_id, plan_id, id),
    CONSTRAINT fk_plan_design_briefs__plans FOREIGN KEY (workspace_id, plan_id)
        REFERENCES skm_planning.plans (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_plan_design_briefs__goal CHECK (char_length(goal) BETWEEN 1 AND 20000 AND btrim(goal) <> '')
);
CREATE TRIGGER tg_plan_design_briefs__immutable BEFORE UPDATE OR DELETE ON skm_planning.plan_design_briefs
    FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

-- ---------------------------------------------------------------- aliases and counters
CREATE TABLE skm_planning.project_plan_counters (
    workspace_id uuid    NOT NULL,
    project_id   uuid    NOT NULL,
    next_plan_no integer NOT NULL DEFAULT 1 CONSTRAINT ck_project_plan_counters__next_plan_no_valid CHECK (next_plan_no >= 1),
    CONSTRAINT pk_project_plan_counters PRIMARY KEY (project_id),
    CONSTRAINT fk_project_plan_counters__projects FOREIGN KEY (workspace_id, project_id)
        REFERENCES skm_workspace.projects (workspace_id, id) ON DELETE RESTRICT
);

CREATE TABLE skm_planning.plan_aliases (
    workspace_id uuid        NOT NULL,
    project_id   uuid        NOT NULL,
    plan_id      uuid        NOT NULL,
    alias        text        NOT NULL,
    alias_kind   text        NOT NULL,
    created_at   timestamptz NOT NULL,
    CONSTRAINT pk_plan_aliases PRIMARY KEY (workspace_id, project_id, alias),
    CONSTRAINT fk_plan_aliases__plans FOREIGN KEY (workspace_id, project_id, plan_id)
        REFERENCES skm_planning.plans (workspace_id, project_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_plan_aliases__alias_kind CHECK (alias_kind IN ('short', 'system', 'legacy', 'external')),
    CONSTRAINT ck_plan_aliases__system CHECK (alias_kind <> 'system' OR alias = 'review-requests'),
    -- short alias: <planning.aliases.prefix><n>; the prefix AC would collide with criterion keys (AC1)
    CONSTRAINT ck_plan_aliases__short CHECK (alias_kind <> 'short' OR (alias ~ '^[A-Z]{2,8}[1-9][0-9]*$' AND alias !~ '^AC[0-9]')),
    CONSTRAINT ck_plan_aliases__alias CHECK (length(alias) BETWEEN 1 AND 200)
);
-- at most one primary alias per plan: short (PLAN<n>) for standard plans, system for the review-requests plan
CREATE UNIQUE INDEX uq_plan_aliases__plan_id_short ON skm_planning.plan_aliases (plan_id) WHERE alias_kind IN ('short', 'system');
CREATE INDEX ix_plan_aliases__plan_id ON skm_planning.plan_aliases (plan_id);

-- ---------------------------------------------------------------- revisions (immutable)
CREATE TABLE skm_planning.plan_revisions (
    workspace_id             uuid        NOT NULL,
    plan_id                  uuid        NOT NULL,
    id                       uuid        NOT NULL,
    revision_no              integer     NOT NULL CONSTRAINT ck_plan_revisions__revision_no_valid CHECK (revision_no >= 1),
    parent_revision_id       uuid        NULL,
    schema_version           integer     NOT NULL CONSTRAINT ck_plan_revisions__schema_version_valid CHECK (schema_version >= 1),
    content_digest           text        NOT NULL CONSTRAINT ck_plan_revisions__content_digest_valid CHECK (content_digest ~ '^sha256:[0-9a-f]{64}$'),
    canonicalization_version integer     NOT NULL DEFAULT 1,
    compiler_version         integer     NOT NULL DEFAULT 1,
    published_by             uuid        NOT NULL,
    published_at             timestamptz NOT NULL,
    change_reason            text        NOT NULL CONSTRAINT ck_plan_revisions__change_reason_valid CHECK (length(change_reason) BETWEEN 1 AND 2000),
    origin                   text        NOT NULL DEFAULT 'draft',
    restored_from_revision_id uuid       NULL,          -- planning.restore_revision: the revision whose payload was copied
    CONSTRAINT pk_plan_revisions PRIMARY KEY (id),
    CONSTRAINT uq_plan_revisions__plan_id_revision_no UNIQUE (plan_id, revision_no),
    CONSTRAINT uq_plan_revisions__workspace_id_plan_id_id UNIQUE (workspace_id, plan_id, id),
    CONSTRAINT fk_plan_revisions__plans FOREIGN KEY (workspace_id, plan_id)
        REFERENCES skm_planning.plans (workspace_id, id) ON DELETE RESTRICT,
    -- the parent belongs to the same plan
    CONSTRAINT fk_plan_revisions__parent FOREIGN KEY (workspace_id, plan_id, parent_revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_plan_revisions__restored_from FOREIGN KEY (workspace_id, plan_id, restored_from_revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_plan_revisions__parent CHECK ((revision_no = 1) = (parent_revision_id IS NULL)),
    CONSTRAINT ck_plan_revisions__origin CHECK (origin IN ('draft', 'restore', 'import', 'system')),
    CONSTRAINT ck_plan_revisions__restored_from CHECK (
        (origin = 'restore') = (restored_from_revision_id IS NOT NULL)
        AND (restored_from_revision_id IS NULL OR (restored_from_revision_id <> id AND parent_revision_id IS NOT NULL)))
);
CREATE TRIGGER tg_plan_revisions__immutable BEFORE UPDATE OR DELETE ON skm_planning.plan_revisions
    FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

-- current_revision_id points to a revision of the same plan (circular reference: deferred check)
ALTER TABLE skm_planning.plans
    ADD CONSTRAINT fk_plans__current_revision FOREIGN KEY (workspace_id, id, current_revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE skm_planning.revision_payloads (
    workspace_id    uuid  NOT NULL,
    plan_id         uuid  NOT NULL,
    revision_id     uuid  NOT NULL,
    document        jsonb NOT NULL,
    document_digest text  NOT NULL CONSTRAINT ck_revision_payloads__document_digest_valid CHECK (document_digest ~ '^sha256:[0-9a-f]{64}$'),
    CONSTRAINT pk_revision_payloads PRIMARY KEY (revision_id),
    CONSTRAINT fk_revision_payloads__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_revision_payloads__size CHECK (octet_length(document::text) <= 16777216)
);
CREATE TRIGGER tg_revision_payloads__immutable BEFORE UPDATE OR DELETE ON skm_planning.revision_payloads
    FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

-- ---------------------------------------------------------------- drafts (mutable)
CREATE TABLE skm_planning.plan_drafts (
    workspace_id          uuid        NOT NULL,
    plan_id               uuid        NOT NULL,
    id                    uuid        NOT NULL,
    base_revision_id      uuid        NULL,
    edit_version          bigint      NOT NULL DEFAULT 1 CONSTRAINT ck_plan_drafts__edit_version_valid CHECK (edit_version >= 1),
    schema_version        integer     NOT NULL DEFAULT 1,
    document              jsonb       NOT NULL,
    state                 text        NOT NULL DEFAULT 'open',
    published_revision_id uuid        NULL,
    created_by            uuid        NOT NULL,
    created_at            timestamptz NOT NULL,
    updated_by            uuid        NOT NULL,
    updated_at            timestamptz NOT NULL,
    closed_at             timestamptz NULL,
    CONSTRAINT pk_plan_drafts PRIMARY KEY (id),
    CONSTRAINT uq_plan_drafts__workspace_id_plan_id_id UNIQUE (workspace_id, plan_id, id),
    CONSTRAINT fk_plan_drafts__plans FOREIGN KEY (workspace_id, plan_id)
        REFERENCES skm_planning.plans (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_plan_drafts__base_revision FOREIGN KEY (workspace_id, plan_id, base_revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_plan_drafts__published_revision FOREIGN KEY (workspace_id, plan_id, published_revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_plan_drafts__state CHECK (state IN ('open', 'published', 'abandoned')),
    CONSTRAINT ck_plan_drafts__published CHECK ((state = 'published') = (published_revision_id IS NOT NULL)),
    CONSTRAINT ck_plan_drafts__closed CHECK ((state = 'open') = (closed_at IS NULL)),
    CONSTRAINT ck_plan_drafts__size CHECK (octet_length(document::text) <= 16777216)
);
CREATE INDEX ix_plan_drafts__plan_id_state ON skm_planning.plan_drafts (plan_id, state);

-- ---------------------------------------------------------------- identities and members
CREATE TABLE skm_planning.plan_entity_identities (
    workspace_id uuid        NOT NULL,
    plan_id      uuid        NOT NULL,
    entity_id    uuid        NOT NULL,
    entity_kind  text        NOT NULL,
    first_revision_id uuid   NOT NULL,
    created_at   timestamptz NOT NULL,
    CONSTRAINT pk_plan_entity_identities PRIMARY KEY (plan_id, entity_id),
    CONSTRAINT uq_plan_entity_identities__entity_id UNIQUE (entity_id),   -- an id is never reused, even across plans
    CONSTRAINT fk_plan_entity_identities__plans FOREIGN KEY (workspace_id, plan_id)
        REFERENCES skm_planning.plans (workspace_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_plan_entity_identities__first_revision FOREIGN KEY (workspace_id, plan_id, first_revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_plan_entity_identities__entity_kind CHECK (entity_kind IN
        ('phase', 'item', 'unit', 'requirement', 'criterion', 'check', 'decision', 'material'))
);
CREATE TRIGGER tg_plan_entity_identities__immutable BEFORE UPDATE OR DELETE ON skm_planning.plan_entity_identities
    FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

CREATE TABLE skm_planning.revision_members (
    workspace_id uuid    NOT NULL,
    plan_id      uuid    NOT NULL,
    revision_id  uuid    NOT NULL,
    entity_id    uuid    NOT NULL,
    entity_kind  text    NOT NULL,
    display_key  text    NOT NULL CONSTRAINT ck_revision_members__display_key_valid CHECK (length(display_key) BETWEEN 1 AND 200),
    position     integer NOT NULL CONSTRAINT ck_revision_members__position_valid CHECK (position >= 0),
    CONSTRAINT pk_revision_members PRIMARY KEY (revision_id, entity_id),
    CONSTRAINT uq_revision_members__revision_id_display_key UNIQUE (revision_id, display_key),
    CONSTRAINT uq_revision_members__scope_entity UNIQUE (workspace_id, plan_id, revision_id, entity_id),
    CONSTRAINT uq_revision_members__scope_entity_kind UNIQUE (workspace_id, plan_id, revision_id, entity_id, entity_kind),
    CONSTRAINT fk_revision_members__plan_revisions FOREIGN KEY (workspace_id, plan_id, revision_id)
        REFERENCES skm_planning.plan_revisions (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_revision_members__identities FOREIGN KEY (plan_id, entity_id)
        REFERENCES skm_planning.plan_entity_identities (plan_id, entity_id) ON DELETE RESTRICT,
    CONSTRAINT ck_revision_members__entity_kind CHECK (entity_kind IN
        ('phase', 'item', 'unit', 'requirement', 'criterion', 'check', 'decision', 'material'))
);
CREATE INDEX ix_revision_members__revision_id_entity_kind_position
    ON skm_planning.revision_members (revision_id, entity_kind, position);
CREATE TRIGGER tg_revision_members__immutable BEFORE UPDATE OR DELETE ON skm_planning.revision_members
    FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

-- kind of an entity never changes between revisions
CREATE FUNCTION skm_planning.tg_member_kind_matches_identity() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM skm_planning.plan_entity_identities i
                   WHERE i.plan_id = NEW.plan_id AND i.entity_id = NEW.entity_id AND i.entity_kind = NEW.entity_kind) THEN
        RAISE EXCEPTION 'entity % changes kind to %', NEW.entity_id, NEW.entity_kind USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;
CREATE TRIGGER tg_revision_members__kind BEFORE INSERT ON skm_planning.revision_members
    FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_member_kind_matches_identity();

SELECT skm_core.grant_app('skm_planning', ARRAY['plan_aliases','plan_design_briefs','plan_entity_identities','plan_revisions','revision_members','revision_payloads']::text[]);
