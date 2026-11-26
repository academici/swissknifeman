# `planning.publish_revision` — SQL sequence of one transaction

Normative order for `adapters/postgres/planning/` (`spec/modules/planning.md` §7.5). Everything below runs on the
connection of the command's `PostgresUnitOfWork` (one transaction, READ COMMITTED). Domain decisions happen in
Python between the reads and the writes; no row is written before every check has passed.

```sql
-- 0. BEGIN is issued by the UoW; the bus has already validated the DTO, authorized plan.publish + plan.read on the plan scope
--    and looked up the idempotency receipt (a hit returns the stored plan-only result and nothing below runs).
--    The result contains published revision IDs/digest and material reference IDs only, never FileVersionView metadata.
--    Those references are now part of the plan document; separate file metadata reads require fresh file authorization.

-- 1. Read the draft owner without a row lock (scope/ownership preliminary check only).
SELECT plan_id, workspace_id FROM skm_planning.plan_drafts WHERE id = $draft_id;
-- owner must match supplied plan/workspace, otherwise NOT_FOUND.

-- 2. Lock plan first, then draft: the same plan -> drafts order as archive/rebase.
SELECT workspace_id, project_id, id, lifecycle_state, current_revision_id, next_revision_no, row_version
  FROM skm_planning.plans WHERE id = $plan_id FOR UPDATE;
-- archived -> PLAN_ARCHIVED
SELECT id, plan_id, workspace_id, base_revision_id, edit_version, state, document
  FROM skm_planning.plan_drafts WHERE id = $draft_id FOR UPDATE;
-- Recheck plan/workspace owner after both locks; stale scope/owner -> NOT_FOUND.
-- state <> open -> DRAFT_NOT_OPEN; expected_edit_version mismatch -> VERSION_CONFLICT.
-- draft.base_revision_id IS DISTINCT FROM plan.current_revision_id -> BASE_REVISION_CHANGED.

-- 3. Project must be active (facade workspace.public.require_active_project, same connection):
SELECT state FROM skm_workspace.projects WHERE workspace_id = $workspace_id AND id = $project_id;   -- archived -> PROJECT_ARCHIVED

-- 4. Validation context (reads only):
SELECT mount_name FROM skm_workspace.project_repositories WHERE workspace_id = $workspace_id AND project_id = $project_id;
SELECT entity_id, entity_kind FROM skm_planning.plan_entity_identities WHERE plan_id = $plan_id;        -- entity_kind_changed
SELECT p.id, a.alias FROM skm_planning.plans p JOIN skm_planning.plan_aliases a ON a.plan_id = p.id
 WHERE p.workspace_id = $workspace_id AND p.project_id = $project_id;                                    -- plan_relation targets
-- known skills / runtime catalog models: extensions.public.known_keys(uow, ...) (skm_extensions reads)
-- Python: from_document -> validate (all rules) -> any finding with severity error -> PLAN_NOT_READY (details.findings)
-- Preparation order (shared with readonly planning.preview_publication): resolve latest_at_publish as 6a below,
-- then normalize/from_document/validate and compute digest. 6a is a read dependency of this step, not a later write.
-- Python: digest = sha256(canonical_bytes(prepared normalized document)) (planning §5.6).
-- expected_content_digest is REQUIRED and must equal digest; otherwise VERSION_CONFLICT
-- (details.reason = 'candidate_changed'), before counter/revision/draft/event writes.
-- Raw draft.document_digest does not bind the resolved materials. A new version after preview can cause this
-- conflict; the caller must inspect another preview and explicitly retry with a new candidate/key.

-- 5. No-op publication.
SELECT content_digest FROM skm_planning.plan_revisions WHERE id = plans.current_revision_id;
-- equal to digest -> NO_CHANGES

-- 6a. Materials with freshness.policy = latest_at_publish: pin the newest ready version of the same file
--     (artifacts.public.latest_ready_version; runs BEFORE the digest of step 4 is final: the resolved
--     file_version_id is written into the normalized document, then digest and NO_CHANGES are computed).
SELECT fv.id FROM skm_artifacts.file_versions fv
  JOIN skm_artifacts.blobs b ON b.workspace_id = fv.workspace_id AND b.id = fv.blob_id
 WHERE fv.workspace_id = $workspace_id AND fv.file_id = $file_id AND b.availability = 'available'
 ORDER BY fv.version_no DESC LIMIT 1;
-- none -> PreconditionFailed(FILE_VERSION_NOT_READY, details.file_ids)

-- 6. Materials: pin and lock the referenced file versions against concurrent trash/delete (artifacts facade).
SELECT fv.id, fv.workspace_id, f.state, b.availability
  FROM skm_artifacts.file_versions fv
  JOIN skm_artifacts.files f  ON f.workspace_id = fv.workspace_id AND f.id = fv.file_id
  JOIN skm_artifacts.blobs b  ON b.workspace_id = fv.workspace_id AND b.id = fv.blob_id
 WHERE fv.workspace_id = $workspace_id AND fv.id = ANY($file_version_ids)
   FOR SHARE OF fv, b;
-- missing / other workspace / blob not 'available' -> PreconditionFailed(FILE_VERSION_NOT_READY, details.file_version_ids)
-- a trashed file is fine: published revisions keep reading their pinned version

-- 7. Allocate the revision number.
UPDATE skm_planning.plans SET next_revision_no = next_revision_no + 1
 WHERE id = $plan_id RETURNING next_revision_no - 1 AS revision_no;

-- 8. The revision row.
INSERT INTO skm_planning.plan_revisions
       (workspace_id, plan_id, id, revision_no, parent_revision_id, schema_version, content_digest,
        canonicalization_version, compiler_version, published_by, published_at, change_reason, origin, restored_from_revision_id)
VALUES ($workspace_id, $plan_id, $revision_id, $revision_no, $current_revision_id, 1, $digest, 1, 1, $actor, $now, $reason,
        'draft', NULL);

-- 9. Identities of entities that appear for the first time (existing ids are skipped).
INSERT INTO skm_planning.plan_entity_identities (workspace_id, plan_id, entity_id, entity_kind, first_revision_id, created_at)
SELECT $workspace_id, $plan_id, e.entity_id, e.entity_kind, $revision_id, $now
  FROM unnest($entity_ids::uuid[], $entity_kinds::text[]) AS e(entity_id, entity_kind)
ON CONFLICT (plan_id, entity_id) DO NOTHING;
-- uq_plan_entity_identities__entity_id violation (id used by another plan) -> Conflict(ID_CONFLICT)

-- 10. Members (trigger tg_revision_members__kind refuses a kind change).
INSERT INTO skm_planning.revision_members (workspace_id, plan_id, revision_id, entity_id, entity_kind, display_key, position)
SELECT ... FROM unnest(...);                        -- one row per phase, item, unit, requirement, criterion, check, decision, material

-- 11. Typed content, parents before children (FK order):
--     revision_specs -> phase_specs -> batch_specs -> item_specs -> unit_specs (parents first: topological by parent)
--     -> requirement_specs -> check_specs -> acceptance_criteria -> decision_specs -> material_specs
-- 12. Links (any order after 11):
--     batch_members, dependency_edges, entity_relations, entity_requirement_links, decision_supersessions,
--     decision_bindings, material_bindings, entity_check_bindings, criterion_check_bindings, review_requirements,
--     entity_path_specs, artifact_specs, entity_read_specs, entity_skill_requirements, plan_relations,
--     revision_file_bindings
--     Each table: one INSERT ... SELECT FROM unnest(arrays) (or executemany); never row-by-row round trips for > 50 rows.

-- 13. Payload (derived copy of the same normalized document; equality with the typed rows is a contract test).
INSERT INTO skm_planning.revision_payloads (workspace_id, plan_id, revision_id, document, document_digest)
VALUES ($workspace_id, $plan_id, $revision_id, $document::jsonb, $digest);

-- 14. Point the plan at the new revision.
UPDATE skm_planning.plans
   SET current_revision_id = $revision_id, title = $spec_title,
       row_version = row_version + 1, updated_at = $now
 WHERE id = $plan_id;

-- 15. Close the draft.
UPDATE skm_planning.plan_drafts
   SET state = 'published', published_revision_id = $revision_id, closed_at = $now,
       updated_at = $now, updated_by = $actor
 WHERE id = $draft_id;

-- 16. UoW.record(PlanRevisionPublished{origin: "draft"}) -> skm_core.event_streams / workspace_event_counters / domain_events / outbox
-- 17. bus: skm_core.idempotency_receipts (result), skm_core.audit_records (allowed)
-- 18. COMMIT (deferred constraints fk_plans__current_revision and tg_material_specs__has_pin are checked here)
```

Failure semantics: any error before COMMIT rolls everything back (draft stays `open` with the same `edit_version`).
`40001`/`40P01` is retried by the bus (≤ `storage.retry.max_attempts`); a retry re-runs from step 1.

## `planning.restore_revision` — differences from the sequence above

```sql
-- 1'. No draft. Lock the plan (step 2 as above): archived -> PLAN_ARCHIVED;
--     $expected_current_revision_id given and <> current_revision_id -> BASE_REVISION_CHANGED.
-- 2'. Source revision of the same plan:
SELECT r.id, r.content_digest, r.canonicalization_version, p.document
  FROM skm_planning.plan_revisions r JOIN skm_planning.revision_payloads p ON p.revision_id = r.id
 WHERE r.plan_id = $plan_id AND r.revision_no = $revision_no;                 -- none -> NOT_FOUND (details.kind = "revision")
-- 3'. Validation context and validation of the copied document (steps 3-4); errors -> PLAN_NOT_READY.
--     latest_at_publish is NOT re-resolved: the payload already holds the version pinned by the source revision.
-- 4'. source digest = current revision digest -> NO_CHANGES (step 5).
-- 5'. Steps 6, 7, 9-14 as above; step 8 writes origin = 'restore', restored_from_revision_id = source id,
--     content_digest = source digest (recomputed only if source canonicalization_version <> 1).
--     Step 9 inserts nothing new (every id of the source already has an identity; ids are never reused).
-- 6'. No draft update (step 15). Open drafts of the plan stay open and become stale (BASE_REVISION_CHANGED on publish).
-- 7'. Events: PlanRevisionPublished{origin: "restore"}, then PlanRevisionRestored (same stream, consecutive stream_seq).
```

## `planning.rebase_draft` — one transaction, no revision is written

```sql
SELECT ... FROM skm_planning.plan_drafts WHERE id = $draft_id FOR UPDATE;        -- NOT_FOUND / DRAFT_NOT_OPEN / VERSION_CONFLICT
SELECT lifecycle_state, current_revision_id FROM skm_planning.plans WHERE id = $plan_id;   -- no lock: a later publish only makes the draft stale again
-- archived -> PLAN_ARCHIVED; $onto_revision_id given and <> current -> BASE_REVISION_CHANGED;
-- base_revision_id = current (or current IS NULL) -> result changed=false, nothing written, no event.
SELECT document FROM skm_planning.revision_payloads WHERE revision_id = ANY(ARRAY[$base_revision_id, $current_revision_id]);
-- Python: rebase_document(base, draft.document, current, resolutions) (spec §5.10)
--   unresolved conflicts -> Conflict(REBASE_CONFLICTS, details.conflicts): ROLLBACK, draft unchanged
UPDATE skm_planning.plan_drafts
   SET document = $merged::jsonb, base_revision_id = $current_revision_id, edit_version = edit_version + 1,
       updated_by = $actor, updated_at = $now
 WHERE id = $draft_id AND edit_version = $expected_edit_version AND state = 'open';     -- 0 rows cannot happen under FOR UPDATE
-- UoW.record(DraftRebased); bus: idempotency receipt, audit; COMMIT
```
