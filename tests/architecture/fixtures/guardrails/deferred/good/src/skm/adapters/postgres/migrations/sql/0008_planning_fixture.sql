CREATE TABLE skm_planning.plans (
    id uuid REFERENCES skm_workspace.projects(id),
    scope_id uuid REFERENCES skm_core.scopes(id),
    parent_id uuid REFERENCES skm_planning.plans(id)
);
