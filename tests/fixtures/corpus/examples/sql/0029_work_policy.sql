-- 0029_work_policy: typed authoring overrides and immutable effective run policy.
-- Existing published documents keep their bytes/digest; NULL means absent, never current defaults.
ALTER TABLE skm_planning.item_specs ADD COLUMN work_policy jsonb NULL,
    ADD CONSTRAINT ck_item_specs__work_policy CHECK (work_policy IS NULL OR
        (jsonb_typeof(work_policy) = 'object' AND octet_length(work_policy::text) <= 4096));
ALTER TABLE skm_planning.unit_specs ADD COLUMN work_policy jsonb NULL,
    ADD CONSTRAINT ck_unit_specs__work_policy CHECK (work_policy IS NULL OR
        (jsonb_typeof(work_policy) = 'object' AND octet_length(work_policy::text) <= 4096));
ALTER TABLE skm_execution.execution_bundles ADD COLUMN work_policies jsonb NULL,
    ADD CONSTRAINT ck_execution_bundles__work_policies CHECK (work_policies IS NULL OR
        (jsonb_typeof(work_policies) = 'object' AND octet_length(work_policies::text) <= 16777216));
-- Existing immutable triggers cover the new columns. Application schema validation checks closed shapes,
-- seven roles, intensity enums, complete compiled-task coverage and digest. New runs require non-NULL;
-- historical NULL bundles remain readable for diagnostics, but cannot execute with invented policy.

ALTER TABLE skm_execution.readiness_reports ADD COLUMN work_policies jsonb NULL,
    ADD CONSTRAINT ck_readiness_reports__work_policies CHECK (work_policies IS NULL OR
        (jsonb_typeof(work_policies) = 'object' AND octet_length(work_policies::text) <= 16777216));
-- Historical NULL readiness snapshots are stale for new starts; the next validation writes a fresh row.

ALTER TABLE skm_execution.readiness_reports ADD COLUMN start_request jsonb NULL,
    ADD CONSTRAINT ck_readiness_reports__start_request CHECK (start_request IS NULL OR
        (jsonb_typeof(start_request) = 'object' AND octet_length(start_request::text) <= 1048576));
-- New reports bind exact authorized prospective overrides/selection; NULL old reports are stale.
