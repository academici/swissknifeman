-- 0002_core_scopes: the scope tree (instance → workspace → project → [plan →] run; host under instance).
-- Every scope-owning entity (workspaces, projects, plans, runs, hosts) references its row with `id REFERENCES skm_core.scopes(id)`.

CREATE TABLE skm_core.scopes (
    id            uuid        PRIMARY KEY,
    kind          text        NOT NULL,
    parent_id     uuid        NULL,
    workspace_id  uuid        NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT fk_scopes__parent FOREIGN KEY (parent_id) REFERENCES skm_core.scopes (id) ON DELETE RESTRICT,
    CONSTRAINT ck_scopes__kind CHECK (kind IN ('instance', 'workspace', 'project', 'plan', 'run', 'host')),
    CONSTRAINT ck_scopes__root CHECK ((kind = 'instance') = (parent_id IS NULL)),
    CONSTRAINT ck_scopes__workspace_id CHECK (
        (kind IN ('instance', 'host') AND workspace_id IS NULL)
        -- IS NOT NULL: `NULL = id` is unknown and an unknown CHECK passes
        OR (kind = 'workspace' AND workspace_id IS NOT NULL AND workspace_id = id)
        OR (kind IN ('project', 'plan', 'run') AND workspace_id IS NOT NULL)
    )
);

-- at most one instance row
CREATE UNIQUE INDEX uq_scopes__single_instance ON skm_core.scopes (kind) WHERE kind = 'instance';
CREATE INDEX ix_scopes__parent_id ON skm_core.scopes (parent_id);
CREATE INDEX ix_scopes__workspace_id_kind ON skm_core.scopes (workspace_id, kind);

-- parent kind and workspace consistency (CHECK cannot look at another row)
CREATE OR REPLACE FUNCTION skm_core.check_scope_parent() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent_kind text;
    parent_workspace uuid;
    expected text[];
BEGIN
    IF NEW.kind = 'instance' THEN
        RETURN NEW;
    END IF;
    SELECT kind, workspace_id INTO parent_kind, parent_workspace FROM skm_core.scopes WHERE id = NEW.parent_id;
    expected := CASE NEW.kind
        WHEN 'workspace' THEN ARRAY['instance']
        WHEN 'host' THEN ARRAY['instance']
        WHEN 'project' THEN ARRAY['workspace']
        WHEN 'plan' THEN ARRAY['project']
        WHEN 'run' THEN ARRAY['plan', 'project']
    END;
    IF (parent_kind = ANY(expected)) IS NOT TRUE THEN
        RAISE EXCEPTION 'skm: scope of kind % needs a parent of kind %, got %', NEW.kind, expected, parent_kind
            USING ERRCODE = 'check_violation';
    END IF;
    IF NEW.kind IN ('project', 'plan', 'run') AND NEW.workspace_id IS DISTINCT FROM parent_workspace THEN
        RAISE EXCEPTION 'skm: scope % must belong to workspace % of its parent', NEW.id, parent_workspace
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END
$$;

CREATE TRIGGER tg_scopes__parent_kind BEFORE INSERT ON skm_core.scopes
    FOR EACH ROW EXECUTE FUNCTION skm_core.check_scope_parent();
CREATE TRIGGER tg_scopes__immutable BEFORE UPDATE ON skm_core.scopes
    FOR EACH ROW EXECUTE FUNCTION skm_core.forbid_update();

SELECT skm_core.grant_app('skm_core', ARRAY['scopes']::text[]);
