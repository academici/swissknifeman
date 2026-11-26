-- 0011_planning_file_bindings: a material of kind file_version is always pinned to one exact file version
-- (never "latest"). Requires 0010_artifacts_files_blobs (skm_artifacts.file_versions with UNIQUE (workspace_id, file_id, id)
-- and UNIQUE (workspace_id, id)).

CREATE TABLE skm_planning.revision_file_bindings (
    workspace_id    uuid  NOT NULL,
    plan_id         uuid  NOT NULL,
    revision_id     uuid  NOT NULL,
    material_id     uuid  NOT NULL,
    file_version_id uuid  NOT NULL,
    role            text  NOT NULL CONSTRAINT ck_revision_file_bindings__role_valid CHECK (role IN ('input', 'reference')),
    selector        jsonb NULL,         -- #/$defs/selector of the specification schema
    CONSTRAINT pk_revision_file_bindings PRIMARY KEY (revision_id, material_id),
    CONSTRAINT fk_revision_file_bindings__material FOREIGN KEY (workspace_id, plan_id, revision_id, material_id)
        REFERENCES skm_planning.material_specs (workspace_id, plan_id, revision_id, material_id),
    -- same workspace as the plan: a revision cannot pin a file of another workspace
    CONSTRAINT fk_revision_file_bindings__file_version FOREIGN KEY (workspace_id, file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_revision_file_bindings__file_version_id ON skm_planning.revision_file_bindings (file_version_id);
CREATE TRIGGER tg_revision_file_bindings__immutable BEFORE UPDATE OR DELETE ON skm_planning.revision_file_bindings
    FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

-- every file_version material of a revision has its pin (checked at commit time)
CREATE FUNCTION skm_planning.tg_material_has_pin() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.kind = 'file_version' AND NOT EXISTS (
        SELECT 1 FROM skm_planning.revision_file_bindings b
        WHERE b.revision_id = NEW.revision_id AND b.material_id = NEW.material_id) THEN
        RAISE EXCEPTION 'material % of revision % has no file version pin', NEW.material_id, NEW.revision_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;
    RETURN NULL;
END;
$$;
CREATE CONSTRAINT TRIGGER tg_material_specs__has_pin AFTER INSERT ON skm_planning.material_specs
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_material_has_pin();

-- Design-time references are pinned separately from published execution materials.
CREATE TABLE skm_planning.plan_design_brief_rag_bindings (
    workspace_id    uuid NOT NULL,
    plan_id         uuid NOT NULL,
    design_brief_id uuid NOT NULL,
    file_version_id uuid NOT NULL,
    CONSTRAINT pk_plan_design_brief_rag_bindings PRIMARY KEY (design_brief_id, file_version_id),
    CONSTRAINT fk_design_brief_rag__brief FOREIGN KEY (workspace_id, plan_id, design_brief_id)
        REFERENCES skm_planning.plan_design_briefs (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT fk_design_brief_rag__file_version FOREIGN KEY (workspace_id, file_version_id)
        REFERENCES skm_artifacts.file_versions (workspace_id, id) ON DELETE RESTRICT
);
CREATE INDEX ix_plan_design_brief_rag__version ON skm_planning.plan_design_brief_rag_bindings (workspace_id, file_version_id);
CREATE TRIGGER tg_design_brief_rag__immutable BEFORE UPDATE OR DELETE ON skm_planning.plan_design_brief_rag_bindings
    FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

-- Research may come from outside SKM or from the downstream context module. Keep an opaque
-- reference and a content digest without a reverse foreign key into the context schema.
CREATE TABLE skm_planning.plan_design_brief_research_references (
    workspace_id    uuid NOT NULL,
    plan_id         uuid NOT NULL,
    design_brief_id uuid NOT NULL,
    reference       text NOT NULL,
    content_digest  text NOT NULL,
    CONSTRAINT pk_plan_design_brief_research_refs PRIMARY KEY (design_brief_id, reference),
    CONSTRAINT fk_design_brief_research__brief FOREIGN KEY (workspace_id, plan_id, design_brief_id)
        REFERENCES skm_planning.plan_design_briefs (workspace_id, plan_id, id) ON DELETE RESTRICT,
    CONSTRAINT ck_design_brief_research__reference CHECK (char_length(reference) BETWEEN 1 AND 1000 AND btrim(reference) <> ''),
    CONSTRAINT ck_design_brief_research__digest CHECK (content_digest ~ '^sha256:[0-9a-f]{64}$')
);
CREATE TRIGGER tg_design_brief_research__immutable BEFORE UPDATE OR DELETE ON skm_planning.plan_design_brief_research_references
    FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable();

SELECT skm_core.grant_app('skm_planning', ARRAY['acceptance_criteria','artifact_specs','batch_members','batch_specs','check_specs','criterion_check_bindings','decision_bindings','decision_specs','decision_supersessions','dependency_edges','entity_check_bindings','entity_path_specs','entity_read_specs','entity_relations','entity_requirement_links','entity_skill_requirements','item_specs','material_bindings','material_specs','phase_specs','plan_aliases','plan_design_brief_rag_bindings','plan_design_brief_research_references','plan_design_briefs','plan_entity_identities','plan_relations','plan_revisions','requirement_specs','review_requirements','revision_file_bindings','revision_members','revision_payloads','revision_specs','unit_specs']::text[]);
