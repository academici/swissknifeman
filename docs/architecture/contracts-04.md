# Contract inventory, part 4

| Признак | Control plane (bus handlers, подписчики) | Host operations |
|---|---|---|
| `src/skm/schemas/execution/work-policy.v1.json` | urn:skm:execution:work-policy:v1 | P00.04.d → P07.02 |
| `src/skm/schemas/execution/workflow.v1.json` | urn:skm:execution:workflow:v1 | P00.04.d → P07.04.a → P07.11 |
| `src/skm/schemas/exports/commands/purge-notes.v1.json` | urn:skm:exports:command:purge-notes:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/commands/record-note-written.v1.json` | urn:skm:exports:command:record-note-written:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/commands/requeue-note.v1.json` | urn:skm:exports:command:requeue-note:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/defs.v1.json` | urn:skm:exports:defs:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/events/vault-note-queued.v1.json` | urn:skm:exports:event:vault-note-queued:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/events/vault-note-written.v1.json` | urn:skm:exports:event:vault-note-written:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/host/locate-vault.v1.json` | urn:skm:exports:host:locate-vault:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/host/push-vault-docs.v1.json` | urn:skm:exports:host:push-vault-docs:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/host/push-vault-notes.v1.json` | urn:skm:exports:host:push-vault-notes:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/host-results/locate-vault.v1.json` | urn:skm:exports:host-result:locate-vault:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/host-results/push-vault-docs.v1.json` | urn:skm:exports:host-result:push-vault-docs:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/host-results/push-vault-notes.v1.json` | urn:skm:exports:host-result:push-vault-notes:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/queries/list-pending-notes.v1.json` | urn:skm:exports:query:list-pending-notes:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/queries/list-vault-notes.v1.json` | urn:skm:exports:query:list-vault-notes:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/queries/render-plan-markdown.v1.json` | urn:skm:exports:query:render-plan-markdown:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/queries/render-run-report.v1.json` | urn:skm:exports:query:render-run-report:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/results/purge-notes.v1.json` | urn:skm:exports:result:purge-notes:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/results/record-note-written.v1.json` | urn:skm:exports:result:record-note-written:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/results/requeue-note.v1.json` | urn:skm:exports:result:requeue-note:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/views/pending-note.v1.json` | urn:skm:exports:view:pending-note:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/views/pending-notes.v1.json` | urn:skm:exports:view:pending-notes:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/views/plan-markdown.v1.json` | urn:skm:exports:view:plan-markdown:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/views/run-report.v1.json` | urn:skm:exports:view:run-report:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/views/vault-note-list-item.v1.json` | urn:skm:exports:view:vault-note-list-item:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/exports/views/vault-notes.v1.json` | urn:skm:exports:view:vault-notes:v1 | P00.04.e → P13.04.a |
| `src/skm/schemas/extensions/agent-profile.v1.json` | urn:skm:extensions:agent-profile:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/commands/install-pack.v1.json` | urn:skm:extensions:command:install-pack:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/commands/quarantine-resource.v1.json` | urn:skm:extensions:command:quarantine-resource:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/commands/release-quarantine.v1.json` | urn:skm:extensions:command:release-quarantine:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/commands/sync-builtin-packs.v1.json` | urn:skm:extensions:command:sync-builtin-packs:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/commands/uninstall-pack-version.v1.json` | urn:skm:extensions:command:uninstall-pack-version:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/defs.v1.json` | urn:skm:extensions:defs:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/events/pack-installed.v1.json` | urn:skm:extensions:event:pack-installed:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/extensions/events/pack-version-uninstalled.v1.json` | urn:skm:extensions:event:pack-version-uninstalled:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/extensions/events/resource-quarantined.v1.json` | urn:skm:extensions:event:resource-quarantined:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/extensions/events/resource-released.v1.json` | urn:skm:extensions:event:resource-released:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/extensions/events/resource-version-added.v1.json` | urn:skm:extensions:event:resource-version-added:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/extensions/host/check-upstream.v1.json` | urn:skm:extensions:host:check-upstream:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/host/install-pack.v1.json` | urn:skm:extensions:host:install-pack:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/host-results/check-upstream.v1.json` | urn:skm:extensions:host-result:check-upstream:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/host-results/install-pack.v1.json` | urn:skm:extensions:host-result:install-pack:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/pack-payload.v1.json` | urn:skm:extensions:pack-payload:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/extensions/pack.v1.json` | urn:skm:extensions:pack:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/plan-template.v1.json` | urn:skm:extensions:plan-template:v1 | P00.04.c → P09.01.b → P09.08 |
| `src/skm/schemas/extensions/prompt-block.v1.json` | urn:skm:extensions:prompt-block:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/queries/get-pack.v1.json` | urn:skm:extensions:query:get-pack:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/queries/get-resource-version.v1.json` | urn:skm:extensions:query:get-resource-version:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/queries/list-packs.v1.json` | urn:skm:extensions:query:list-packs:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/queries/list-resources.v1.json` | urn:skm:extensions:query:list-resources:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/queries/resolve-resource.v1.json` | urn:skm:extensions:query:resolve-resource:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/results/install-pack.v1.json` | urn:skm:extensions:result:install-pack:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/results/quarantine-resource.v1.json` | urn:skm:extensions:result:quarantine-resource:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/results/release-quarantine.v1.json` | urn:skm:extensions:result:release-quarantine:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/results/sync-builtin-packs.v1.json` | urn:skm:extensions:result:sync-builtin-packs:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/results/uninstall-pack-version.v1.json` | urn:skm:extensions:result:uninstall-pack-version:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/skill-manifest.v1.json` | urn:skm:extensions:skill-manifest:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/steering.v1.json` | urn:skm:extensions:steering:v1 | P00.04.c → P09.01.b |
| `src/skm/schemas/extensions/views/pack.v1.json` | urn:skm:extensions:view:pack:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/extensions/views/packs.v1.json` | urn:skm:extensions:view:packs:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/extensions/views/resolution.v1.json` | urn:skm:extensions:view:resolution:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/extensions/views/resource-version.v1.json` | urn:skm:extensions:view:resource-version:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/extensions/views/resources.v1.json` | urn:skm:extensions:view:resources:v1 | P00.04.c → P09.01.a |
| `src/skm/schemas/integrations/bundle.v1.json` | urn:skm:integrations:bundle:v1 | P00.04.e → P10.06 |
| `src/skm/schemas/integrations/check-result.v1.json` | urn:skm:integrations:check-result:v1 | P00.04.e |
| `src/skm/schemas/integrations/commands/record-drift.v1.json` | urn:skm:integrations:command:record-drift:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/commands/record-hook-delivery-failure.v1.json` | urn:skm:integrations:command:record-hook-delivery-failure:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/commands/record-projection-applied.v1.json` | urn:skm:integrations:command:record-projection-applied:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/commands/remove-projection.v1.json` | urn:skm:integrations:command:remove-projection:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/commands/retry-hook-deliveries.v1.json` | urn:skm:integrations:command:retry-hook-deliveries:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/commands/test-hook-subscription.v1.json` | urn:skm:integrations:command:test-hook-subscription:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/defs.v1.json` | urn:skm:integrations:defs:v1 | P00.04.e → P10.05.a |
| `src/skm/schemas/integrations/events/hook-delivery-failed.v1.json` | urn:skm:integrations:event:hook-delivery-failed:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/events/hook-test-requested.v1.json` | urn:skm:integrations:event:hook-test-requested:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/events/projection-applied.v1.json` | urn:skm:integrations:event:projection-applied:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/events/projection-drift-detected.v1.json` | urn:skm:integrations:event:projection-drift-detected:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/events/projection-removed.v1.json` | urn:skm:integrations:event:projection-removed:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/host/adopt-file.v1.json` | urn:skm:integrations:host:adopt-file:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/apply-projection.v1.json` | urn:skm:integrations:host:apply-projection:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/detect-drift.v1.json` | urn:skm:integrations:host:detect-drift:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/doctor-report.v1.json` | urn:skm:integrations:host:doctor-report:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/drain-hook-spool.v1.json` | urn:skm:integrations:host:drain-hook-spool:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/evaluate-hook.v1.json` | urn:skm:integrations:host:evaluate-hook:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/first-turn-budget.v1.json` | urn:skm:integrations:host:first-turn-budget:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/hook-decision.v1.json` | urn:skm:integrations:host:hook-decision:v1 | P00.04.e → P10.05.a |
| `src/skm/schemas/integrations/host/plan-projection.v1.json` | urn:skm:integrations:host:plan-projection:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/projection-plan.v1.json` | urn:skm:integrations:host:projection-plan:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/remove-projection.v1.json` | urn:skm:integrations:host:remove-projection:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/run-doctor.v1.json` | urn:skm:integrations:host:run-doctor:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/sync-projections.v1.json` | urn:skm:integrations:host:sync-projections:v1 | P10.01.c → I-09.1 |
| `src/skm/schemas/integrations/host/untrack-service-files.v1.json` | urn:skm:integrations:host:untrack-service-files:v1 | P10.01.c → I-09.1 |
| `src/skm/schemas/integrations/host/test-host-subscription.v1.json` | urn:skm:integrations:host:test-host-subscription:v1 | P00.04.e |
| `src/skm/schemas/integrations/host/trust-hook-subscription.v1.json` | urn:skm:integrations:host:trust-hook-subscription:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-command-input.v1.json` | urn:skm:integrations:host-command-input:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-command-output.v1.json` | urn:skm:integrations:host-command-output:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/adopt-file.v1.json` | urn:skm:integrations:host-result:adopt-file:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/apply-projection.v1.json` | urn:skm:integrations:host-result:apply-projection:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/detect-drift.v1.json` | urn:skm:integrations:host-result:detect-drift:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/drain-hook-spool.v1.json` | urn:skm:integrations:host-result:drain-hook-spool:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/evaluate-hook.v1.json` | urn:skm:integrations:host-result:evaluate-hook:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/first-turn-budget.v1.json` | urn:skm:integrations:host-result:first-turn-budget:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/plan-projection.v1.json` | urn:skm:integrations:host-result:plan-projection:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/remove-projection.v1.json` | urn:skm:integrations:host-result:remove-projection:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/run-doctor.v1.json` | urn:skm:integrations:host-result:run-doctor:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/sync-projections.v1.json` | urn:skm:integrations:host-result:sync-projections:v1 | P10.01.c → I-09.1 |
| `src/skm/schemas/integrations/host-results/untrack-service-files.v1.json` | urn:skm:integrations:host-result:untrack-service-files:v1 | P10.01.c → I-09.1 |
| `src/skm/schemas/integrations/host-results/test-host-subscription.v1.json` | urn:skm:integrations:host-result:test-host-subscription:v1 | P00.04.e |
| `src/skm/schemas/integrations/host-results/trust-hook-subscription.v1.json` | urn:skm:integrations:host-result:trust-hook-subscription:v1 | P00.04.e |
| `src/skm/schemas/integrations/queries/get-applied-state.v1.json` | urn:skm:integrations:query:get-applied-state:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/queries/get-desired-projection.v1.json` | urn:skm:integrations:query:get-desired-projection:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/queries/get-hook-policy.v1.json` | urn:skm:integrations:query:get-hook-policy:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/queries/list-hook-deliveries.v1.json` | urn:skm:integrations:query:list-hook-deliveries:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/queries/list-hook-subscriptions.v1.json` | urn:skm:integrations:query:list-hook-subscriptions:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/queries/list-projections.v1.json` | urn:skm:integrations:query:list-projections:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/results/record-drift.v1.json` | urn:skm:integrations:result:record-drift:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/results/record-hook-delivery-failure.v1.json` | urn:skm:integrations:result:record-hook-delivery-failure:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/results/record-projection-applied.v1.json` | urn:skm:integrations:result:record-projection-applied:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/results/remove-projection.v1.json` | urn:skm:integrations:result:remove-projection:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/results/retry-hook-deliveries.v1.json` | urn:skm:integrations:result:retry-hook-deliveries:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/results/test-hook-subscription.v1.json` | urn:skm:integrations:result:test-hook-subscription:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/views/applied-state.v1.json` | urn:skm:integrations:view:applied-state:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/views/desired-projection.v1.json` | urn:skm:integrations:view:desired-projection:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/views/hook-deliveries.v1.json` | urn:skm:integrations:view:hook-deliveries:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/views/hook-delivery.v1.json` | urn:skm:integrations:view:hook-delivery:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/views/hook-policy.v1.json` | urn:skm:integrations:view:hook-policy:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/views/hook-subscription.v1.json` | urn:skm:integrations:view:hook-subscription:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/views/projection-summary.v1.json` | urn:skm:integrations:view:projection-summary:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/views/projections.v1.json` | urn:skm:integrations:view:projections:v1 | P00.04.e → P10.01.b |
| `src/skm/schemas/integrations/webhook-delivery.v1.json` | urn:skm:integrations:webhook-delivery:v1 | P00.04.e |
| `src/skm/schemas/kernel/check-result.v1.json` | urn:skm:kernel:check-result:v1 | P00.04.b → P01.01 → P01.02 → P01.05.a → P01.07 → P01.09.a |
| `src/skm/schemas/kernel/data/error-codes.json` | data document | P00.04.b → P01.02 |
| `src/skm/schemas/kernel/defs.v1.json` | urn:skm:kernel:defs:v1 | P00.04.b |
| `src/skm/schemas/kernel/error-catalog.v1.json` | urn:skm:kernel:error-catalog:v1 | P00.04.b → P01.02 |
| `src/skm/schemas/kernel/event-envelope.v1.json` | urn:skm:kernel:event-envelope:v1 | P00.04.b → P01.07 |
| `src/skm/schemas/knowledge/commands/deprecate-lesson.v1.json` | urn:skm:knowledge:command:deprecate-lesson:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/commands/expire-memory.v1.json` | urn:skm:knowledge:command:expire-memory:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/commands/forget.v1.json` | urn:skm:knowledge:command:forget:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/commands/import-graph.v1.json` | urn:skm:knowledge:command:import-graph:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/commands/promote-lesson.v1.json` | urn:skm:knowledge:command:promote-lesson:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/commands/remember.v1.json` | urn:skm:knowledge:command:remember:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/defs.v1.json` | urn:skm:knowledge:defs:v1 | P00.04.e → P13.01.b → P13.03.b |
| `src/skm/schemas/knowledge/events/graph-imported.v1.json` | urn:skm:knowledge:event:graph-imported:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/events/lesson-deprecated.v1.json` | urn:skm:knowledge:event:lesson-deprecated:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/events/lesson-promoted.v1.json` | urn:skm:knowledge:event:lesson-promoted:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/events/memory-forgotten.v1.json` | urn:skm:knowledge:event:memory-forgotten:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/events/memory-remembered.v1.json` | urn:skm:knowledge:event:memory-remembered:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/graph-answer.v1.json` | urn:skm:knowledge:graph-answer:v1 | P00.04.e → P13.01.a → P13.02.a |
| `src/skm/schemas/knowledge/host/derive-project-graph.v1.json` | urn:skm:knowledge:host:derive-project-graph:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/host/import-code-graph.v1.json` | urn:skm:knowledge:host:import-code-graph:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/host-results/derive-project-graph.v1.json` | urn:skm:knowledge:host-result:derive-project-graph:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/host-results/import-code-graph.v1.json` | urn:skm:knowledge:host-result:import-code-graph:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/queries/get-lesson.v1.json` | urn:skm:knowledge:query:get-lesson:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/queries/graph-neighbors.v1.json` | urn:skm:knowledge:query:graph-neighbors:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/queries/graph-path.v1.json` | urn:skm:knowledge:query:graph-path:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/queries/graph-stats.v1.json` | urn:skm:knowledge:query:graph-stats:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/queries/graph-subgraph.v1.json` | urn:skm:knowledge:query:graph-subgraph:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/queries/list-graph-indexes.v1.json` | urn:skm:knowledge:query:list-graph-indexes:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/queries/list-lessons.v1.json` | urn:skm:knowledge:query:list-lessons:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/queries/list-memory.v1.json` | urn:skm:knowledge:query:list-memory:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/queries/search-memory.v1.json` | urn:skm:knowledge:query:search-memory:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/results/deprecate-lesson.v1.json` | urn:skm:knowledge:result:deprecate-lesson:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/results/expire-memory.v1.json` | urn:skm:knowledge:result:expire-memory:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/results/forget.v1.json` | urn:skm:knowledge:result:forget:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/results/import-graph.v1.json` | urn:skm:knowledge:result:import-graph:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/results/promote-lesson.v1.json` | urn:skm:knowledge:result:promote-lesson:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/results/remember.v1.json` | urn:skm:knowledge:result:remember:v1 | P00.04.e → P13.01.a |
| `src/skm/schemas/knowledge/views/graph-index.v1.json` | urn:skm:knowledge:view:graph-index:v1 | P00.04.e → P13.01.b → P13.03.b |
| `src/skm/schemas/knowledge/views/graph-indexes.v1.json` | HTTP array of latest graph indexes | P13.02.b |
| `src/skm/schemas/knowledge/views/graph-indexes-result.v1.json` | Bus result envelope for latest graph indexes | P13.02.b |
| `src/skm/schemas/knowledge/queries/graph-neighbors-http.v1.json` | HTTP neighbors query with depth capped at 3 | P13.02.b |
| `src/skm/schemas/knowledge/views/lesson.v1.json` | urn:skm:knowledge:view:lesson:v1 | P00.04.e → P13.01.b → P13.03.b |
| `src/skm/schemas/knowledge/views/lessons.v1.json` | urn:skm:knowledge:view:lessons:v1 | P00.04.e → P13.01.b → P13.03.b |
| `src/skm/schemas/knowledge/views/memory-entry.v1.json` | urn:skm:knowledge:view:memory-entry:v1 | P00.04.e → P13.01.b → P13.03.b |
| `src/skm/schemas/knowledge/views/memory-search.v1.json` | urn:skm:knowledge:view:memory-search:v1 | P00.04.e → P13.01.b → P13.03.b |
| `src/skm/schemas/knowledge/views/memory.v1.json` | urn:skm:knowledge:view:memory:v1 | P00.04.e → P13.01.b → P13.03.b |
| `src/skm/schemas/learning/activity-summary.v1.json` | urn:skm:learning:activity-summary:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/commands/extract-candidates.v1.json` | urn:skm:learning:command:extract-candidates:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/commands/promote-candidate.v1.json` | urn:skm:learning:command:promote-candidate:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/commands/recompute-confidence.v1.json` | urn:skm:learning:command:recompute-confidence:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/commands/record-activity.v1.json` | urn:skm:learning:command:record-activity:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/commands/review-candidate.v1.json` | urn:skm:learning:command:review-candidate:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/defs.v1.json` | urn:skm:learning:defs:v1 | P00.04.e → P13.03.b → P13.03.c |
| `src/skm/schemas/learning/events/candidate-extracted.v1.json` | urn:skm:learning:event:candidate-extracted:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/events/candidate-promoted.v1.json` | urn:skm:learning:event:candidate-promoted:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/events/candidate-reviewed.v1.json` | urn:skm:learning:event:candidate-reviewed:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/events/candidate-state-changed.v1.json` | urn:skm:learning:event:candidate-state-changed:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/queries/get-candidate.v1.json` | urn:skm:learning:query:get-candidate:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/queries/list-candidates.v1.json` | urn:skm:learning:query:list-candidates:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/queries/list-signals.v1.json` | urn:skm:learning:query:list-signals:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/queries/pathology-stats.v1.json` | urn:skm:learning:query:pathology-stats:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/results/extract-candidates.v1.json` | urn:skm:learning:result:extract-candidates:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/results/promote-candidate.v1.json` | urn:skm:learning:result:promote-candidate:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/results/recompute-confidence.v1.json` | urn:skm:learning:result:recompute-confidence:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/results/record-activity.v1.json` | urn:skm:learning:result:record-activity:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/results/review-candidate.v1.json` | urn:skm:learning:result:review-candidate:v1 | P00.04.e → P13.03.a |
| `src/skm/schemas/learning/views/candidate-summary.v1.json` | urn:skm:learning:view:candidate-summary:v1 | P00.04.e → P13.03.b → P13.03.c |
| `src/skm/schemas/learning/views/candidate.v1.json` | urn:skm:learning:view:candidate:v1 | P00.04.e → P13.03.b → P13.03.c |
| `src/skm/schemas/learning/views/candidates.v1.json` | urn:skm:learning:view:candidates:v1 | P00.04.e → P13.03.b → P13.03.c |
| `src/skm/schemas/learning/views/pathology-stats.v1.json` | urn:skm:learning:view:pathology-stats:v1 | P00.04.e → P13.03.c |
| `src/skm/schemas/learning/views/signal.v1.json` | urn:skm:learning:view:signal:v1 | P00.04.e → P13.03.b → P13.03.c |
| `src/skm/schemas/learning/views/signals.v1.json` | urn:skm:learning:view:signals:v1 | P00.04.e → P13.03.b → P13.03.c |
| `src/skm/schemas/planning/change-replace-text.v1.json` | urn:skm:planning:change:replace-text:v1 | P00.04.c → P05.04.a → P05.10 → P06.04.b |
| `src/skm/schemas/planning/commands/design-plan.v1.json` | urn:skm:planning:command:design-plan:v1 | P05.04.b → I-11.1 |
| `src/skm/schemas/planning/commands/abandon-draft.v1.json` | urn:skm:planning:command:abandon-draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/commands/archive-plan.v1.json` | urn:skm:planning:command:archive-plan:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/commands/create-plan.v1.json` | urn:skm:planning:command:create-plan:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/commands/import-specification.v1.json` | urn:skm:planning:command:import-specification:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/commands/open-draft.v1.json` | urn:skm:planning:command:open-draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/commands/publish-revision.v1.json` | urn:skm:planning:command:publish-revision:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/commands/rebase-draft.v1.json` | urn:skm:planning:command:rebase-draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/commands/restore-revision.v1.json` | urn:skm:planning:command:restore-revision:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/commands/save-draft.v1.json` | urn:skm:planning:command:save-draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/data/finding-codes.json` | data document | P00.04.c → P05.03.a |
| `src/skm/schemas/planning/defs.v1.json` | urn:skm:planning:defs:v1 | P00.04.c → P05.01 → P05.07 → P05.09.b |
| `src/skm/schemas/planning/events/draft-abandoned.v1.json` | urn:skm:planning:event:draft-abandoned:v1 | P00.04.c → P05.04.a |
| `src/skm/schemas/planning/events/draft-opened.v1.json` | urn:skm:planning:event:draft-opened:v1 | P00.04.c → P05.04.a |
| `src/skm/schemas/planning/events/draft-rebased.v1.json` | urn:skm:planning:event:draft-rebased:v1 | P00.04.c → P05.04.a |
| `src/skm/schemas/planning/events/draft-saved.v1.json` | urn:skm:planning:event:draft-saved:v1 | P00.04.c → P05.04.a |
| `src/skm/schemas/planning/events/plan-archived.v1.json` | urn:skm:planning:event:plan-archived:v1 | P00.04.c → P05.04.a |
| `src/skm/schemas/planning/events/plan-created.v1.json` | urn:skm:planning:event:plan-created:v1 | P00.04.c → P05.04.a |
| `src/skm/schemas/planning/events/plan-revision-published.v1.json` | urn:skm:planning:event:plan-revision-published:v1 | P00.04.c → P05.04.a |
| `src/skm/schemas/planning/events/plan-revision-restored.v1.json` | urn:skm:planning:event:plan-revision-restored:v1 | P00.04.c → P05.04.a |
| `src/skm/schemas/planning/finding-catalog.v1.json` | urn:skm:planning:finding-catalog:v1 | P00.04.c → P05.01 → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/diff-revisions.v1.json` | urn:skm:planning:query:diff-revisions:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/export-specification.v1.json` | urn:skm:planning:query:export-specification:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/get-draft.v1.json` | urn:skm:planning:query:get-draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/get-entity.v1.json` | urn:skm:planning:query:get-entity:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/get-plan.v1.json` | urn:skm:planning:query:get-plan:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/get-revision.v1.json` | urn:skm:planning:query:get-revision:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/list-drafts.v1.json` | urn:skm:planning:query:list-drafts:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/list-entities.v1.json` | urn:skm:planning:query:list-entities:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/list-plans.v1.json` | urn:skm:planning:query:list-plans:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/list-revisions.v1.json` | urn:skm:planning:query:list-revisions:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/plan-stats.v1.json` | urn:skm:planning:query:plan-stats:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/preview-publication.v1.json` | urn:skm:planning:query:preview-publication:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/read-text.v1.json` | urn:skm:planning:query:read-text:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/ready-preview.v1.json` | urn:skm:planning:query:ready-preview:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/simulate.v1.json` | urn:skm:planning:query:simulate:v1 | P05.06 → I-11.4 |
| `src/skm/schemas/planning/queries/resolve-plan-ref.v1.json` | urn:skm:planning:query:resolve-plan-ref:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/queries/validate-draft.v1.json` | urn:skm:planning:query:validate-draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/results/design-plan.v1.json` | urn:skm:planning:result:design-plan:v1 | P05.04.b → I-11.1 |
| `src/skm/schemas/planning/results/abandon-draft.v1.json` | urn:skm:planning:result:abandon-draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/results/archive-plan.v1.json` | urn:skm:planning:result:archive-plan:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/results/create-plan.v1.json` | urn:skm:planning:result:create-plan:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/results/import-specification.v1.json` | urn:skm:planning:result:import-specification:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/results/list-drafts.v1.json` | urn:skm:planning:result:list-drafts:v1 | P05.06 |
| `src/skm/schemas/planning/results/open-draft.v1.json` | urn:skm:planning:result:open-draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/results/publish-revision.v1.json` | urn:skm:planning:result:publish-revision:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/results/rebase-draft.v1.json` | urn:skm:planning:result:rebase-draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/results/restore-revision.v1.json` | urn:skm:planning:result:restore-revision:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/results/save-draft.v1.json` | urn:skm:planning:result:save-draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/specification.v1.json` | urn:skm:planning:specification:v1 | P00.04.c → P05.01 → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/draft-summary.v1.json` | urn:skm:planning:view:draft-summary:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/draft.v1.json` | urn:skm:planning:view:draft:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/drafts.v1.json` | urn:skm:planning:view:drafts:v1 | P00.04.c → P05.04.a → P05.10 → P06.04.b |
| `src/skm/schemas/planning/views/entity-page.v1.json` | urn:skm:planning:view:entity-page:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/entity.v1.json` | urn:skm:planning:view:entity:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/execution-graph.v1.json` | urn:skm:planning:view:execution-graph:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/plan-ref.v1.json` | urn:skm:planning:view:plan-ref:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/plan-stats.v1.json` | urn:skm:planning:view:plan-stats:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/plan-summary.v1.json` | urn:skm:planning:view:plan-summary:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/plan.v1.json` | urn:skm:planning:view:plan:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/plans.v1.json` | urn:skm:planning:view:plans:v1 | P00.04.c → P05.04.a → P05.10 → P06.04.b |
| `src/skm/schemas/planning/views/publication-preview.v1.json` | urn:skm:planning:view:publication-preview:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/ready-preview.v1.json` | urn:skm:planning:view:ready-preview:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/simulation.v1.json` | urn:skm:planning:view:simulation:v1 | P05.06 → I-11.4 |
| `src/skm/schemas/planning/views/revision-summary.v1.json` | urn:skm:planning:view:revision-summary:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/revision.v1.json` | urn:skm:planning:view:revision:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/revisions.v1.json` | urn:skm:planning:view:revisions:v1 | P00.04.c → P05.04.a → P05.10 → P06.04.b |
| `src/skm/schemas/planning/views/spec-diff.v1.json` | urn:skm:planning:view:spec-diff:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/specification-export.v1.json` | urn:skm:planning:view:specification-export:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/text-fragment.v1.json` | urn:skm:planning:view:text-fragment:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/planning/views/validation-report.v1.json` | urn:skm:planning:view:validation-report:v1 | P00.04.c → P05.04.a → P05.07 → P05.09.b |
| `src/skm/schemas/platform/backup-manifest.v1.json` | urn:skm:platform:backup-manifest:v1 | P00.04.b → P15.01.b |
| `src/skm/schemas/platform/commands/repair-storage-safe.v1.json` | urn:skm:platform:command:repair-storage-safe:v1 | P00.04.b → P00.04.f → P03.01.b → P03.05.b → P15.01.a → P01.09.a |
| `src/skm/schemas/platform/commands/retry-outbox.v1.json` | urn:skm:platform:command:retry-outbox:v1 | P00.04.b → P03.05 |
| `src/skm/schemas/platform/queries/doctor.v1.json` | urn:skm:platform:query:doctor:v1 | P00.04.b → P03.01.b |
| `src/skm/schemas/platform/queries/list-dead-outbox.v1.json` | urn:skm:platform:query:list-dead-outbox:v1 | P00.04.b → P03.05 |
| `src/skm/schemas/platform/queries/migration-status.v1.json` | urn:skm:platform:query:migration-status:v1 | P00.04.b → P03.01.b |
| `src/skm/schemas/platform/queries/verify-storage.v1.json` | urn:skm:platform:query:verify-storage:v1 | P00.04.b → P00.04.f → P03.01.b → P03.05.b → P15.01.a → P01.09.a |
| `src/skm/schemas/platform/results/doctor.v1.json` | urn:skm:platform:result:doctor:v1 | P00.04.b → P03.01.b |
| `src/skm/schemas/platform/results/list-dead-outbox.v1.json` | urn:skm:platform:result:list-dead-outbox:v1 | P00.04.b → P03.05 |
| `src/skm/schemas/platform/results/migration-status.v1.json` | urn:skm:platform:result:migration-status:v1 | P00.04.b → P03.01.b |
| `src/skm/schemas/platform/results/repair-storage-safe.v1.json` | urn:skm:platform:result:repair-storage-safe:v1 | P00.04.b → P00.04.f → P03.01.b → P03.05.b → P15.01.a → P01.09.a |
| `src/skm/schemas/platform/results/retry-outbox.v1.json` | urn:skm:platform:result:retry-outbox:v1 | P00.04.b → P03.05 |
| `src/skm/schemas/platform/results/verify-storage.v1.json` | urn:skm:platform:result:verify-storage:v1 | P00.04.b → P00.04.f → P03.01.b → P03.05.b → P15.01.a → P01.09.a |
| `src/skm/schemas/policy/commands/approve-intent.v1.json` | urn:skm:policy:command:approve-intent:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/commands/deny-intent.v1.json` | urn:skm:policy:command:deny-intent:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/commands/expire-intents.v1.json` | urn:skm:policy:command:expire-intents:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/commands/propose-intent.v1.json` | urn:skm:policy:command:propose-intent:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/commands/record-intent-outcome.v1.json` | urn:skm:policy:command:record-intent-outcome:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/commands/record-tool-decisions.v1.json` | urn:skm:policy:command:record-tool-decisions:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/commands/start-intent-execution.v1.json` | urn:skm:policy:command:start-intent-execution:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/events/intent-approved.v1.json` | urn:skm:policy:event:intent-approved:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/events/intent-denied.v1.json` | urn:skm:policy:event:intent-denied:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/events/intent-execution-started.v1.json` | urn:skm:policy:event:intent-execution-started:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/events/intent-proposed.v1.json` | urn:skm:policy:event:intent-proposed:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/events/intent-resolved.v1.json` | urn:skm:policy:event:intent-resolved:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/intent-args-fs-write-external.v1.json` | urn:skm:policy:intent-args-fs-write-external:v1 | P07.01.b → I-04.1 |
| `src/skm/schemas/policy/intent-args-git-commit.v1.json` | urn:skm:policy:intent-args-git-commit:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/intent-args-git-push.v1.json` | urn:skm:policy:intent-args-git-push:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/intent-args-message.v1.json` | urn:skm:policy:intent-args-message:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/intent-args-pr-create.v1.json` | urn:skm:policy:intent-args-pr-create:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/intent-args-publish.v1.json` | urn:skm:policy:intent-args-publish:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/permission-layer.v1.json` | urn:skm:policy:permission-layer:v1 | P00.04.c → P07.01.a |
| `src/skm/schemas/policy/permission-request.v1.json` | urn:skm:policy:permission-request:v1 | P07.01.a |
| `src/skm/schemas/policy/profile.v1.json` | urn:skm:policy:profile:v1 | P00.04.c → P07.01.a |
| `src/skm/schemas/policy/queries/check-tool-call.v1.json` | urn:skm:policy:query:check-tool-call:v1 | P00.04.c |
| `src/skm/schemas/policy/queries/effective-permissions.v1.json` | urn:skm:policy:query:effective-permissions:v1 | P00.04.c |
| `src/skm/schemas/policy/queries/explain-permissions.v1.json` | urn:skm:policy:query:explain-permissions:v1 | P00.04.c |
| `src/skm/schemas/policy/queries/get-intent.v1.json` | urn:skm:policy:query:get-intent:v1 | P00.04.c |
| `src/skm/schemas/policy/queries/list-intents.v1.json` | urn:skm:policy:query:list-intents:v1 | P00.04.c |
| `src/skm/schemas/policy/queries/list-profiles.v1.json` | urn:skm:policy:query:list-profiles:v1 | P00.04.c |
| `src/skm/schemas/policy/results/approve-intent.v1.json` | urn:skm:policy:result:approve-intent:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/results/deny-intent.v1.json` | urn:skm:policy:result:deny-intent:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/results/expire-intents.v1.json` | urn:skm:policy:result:expire-intents:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/results/explain-permissions.v1.json` | urn:skm:policy:result:explain-permissions:v1 | P07.01.b |
| `src/skm/schemas/policy/results/list-profiles.v1.json` | urn:skm:policy:result:list-profiles:v1 | P07.01.b |
| `src/skm/schemas/policy/results/propose-intent.v1.json` | urn:skm:policy:result:propose-intent:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/results/record-intent-outcome.v1.json` | urn:skm:policy:result:record-intent-outcome:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/results/record-tool-decisions.v1.json` | urn:skm:policy:result:record-tool-decisions:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/results/start-intent-execution.v1.json` | urn:skm:policy:result:start-intent-execution:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/scope-roots.v1.json` | urn:skm:policy:scope-roots:v1 | P00.04.c → P07.01.a |
| `src/skm/schemas/policy/task-authority.v1.json` | urn:skm:policy:task-authority:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/tool-call.v1.json` | urn:skm:policy:tool-call:v1 | P00.04.c → P07.01.a |
| `src/skm/schemas/policy/views/effective-permissions.v1.json` | urn:skm:policy:view:effective-permissions:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/views/effective-permissions.v2.json` | urn:skm:policy:view:effective-permissions:v2 | P09.01.a |
| `src/skm/schemas/policy/views/explain-permissions.v1.json` | urn:skm:policy:view:explain-permissions:v1 | P00.04.c → P07.01.b |
| `src/skm/schemas/policy/views/intent-summary.v1.json` | urn:skm:policy:view:intent-summary:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/views/intent.v1.json` | urn:skm:policy:view:intent:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/views/intent.v2.json` | urn:skm:policy:view:intent:v2 | P12.06 |
| `src/skm/schemas/policy/views/intents.v1.json` | urn:skm:policy:view:intents:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/views/permission-set.v1.json` | urn:skm:policy:view:permission-set:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/views/permission-set.v2.json` | urn:skm:policy:view:permission-set:v2 | P09.01.a |
| `src/skm/schemas/policy/views/profile.v1.json` | urn:skm:policy:view:profile:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/views/profiles.v1.json` | urn:skm:policy:view:profiles:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/policy/views/tool-decision.v1.json` | urn:skm:policy:view:tool-decision:v1 | P00.04.c → P07.01.b → P07.01.a → P10.05.a |
| `src/skm/schemas/runtimes/agent-request.v1.json` | urn:skm:runtimes:agent-request:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/capabilities.v1.json` | urn:skm:runtimes:capabilities:v1 | P00.04.c → P08.01.a → P08.11 |
| `src/skm/schemas/runtimes/commands/record-capability-verification.v1.json` | urn:skm:runtimes:command:record-capability-verification:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/commands/record-host-runtimes.v1.json` | urn:skm:runtimes:command:record-host-runtimes:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/error-rules.v1.json` | urn:skm:runtimes:error-rules:v1 | P00.04.c → P08.01.a → P08.11 |
| `src/skm/schemas/runtimes/events/capability-verified.v1.json` | urn:skm:runtimes:event:capability-verified:v1 | P00.04.c → P08.01.b |
| `src/skm/schemas/runtimes/events/host-runtimes-recorded.v1.json` | urn:skm:runtimes:event:host-runtimes-recorded:v1 | P00.04.c → P08.01.b |
| `src/skm/schemas/runtimes/host/detect-runtimes.v1.json` | urn:skm:runtimes:host:detect-runtimes:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/host-results/detect-runtimes.v1.json` | urn:skm:runtimes:host-result:detect-runtimes:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/model-catalog.v1.json` | urn:skm:runtimes:model-catalog:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/queries/explain-routing.v1.json` | urn:skm:runtimes:query:explain-routing:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/queries/get-capabilities.v1.json` | urn:skm:runtimes:query:get-capabilities:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/queries/list-models.v1.json` | urn:skm:runtimes:query:list-models:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/queries/list-runtimes.v1.json` | urn:skm:runtimes:query:list-runtimes:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/results/list-runtimes.v1.json` | urn:skm:runtimes:result:list-runtimes:v1 | P08.01.b |
| `src/skm/schemas/runtimes/results/record-capability-verification.v1.json` | urn:skm:runtimes:result:record-capability-verification:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/results/record-host-runtimes.v1.json` | urn:skm:runtimes:result:record-host-runtimes:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/runtime-observation.v1.json` | urn:skm:runtimes:runtime-observation:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/runtime-result.v1.json` | urn:skm:runtimes:runtime-result:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/session-event.v1.json` | urn:skm:runtimes:session-event:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/usage-report.v1.json` | urn:skm:runtimes:usage-report:v1 | P00.04.c → P08.01.a |
| `src/skm/schemas/runtimes/views/models.v1.json` | urn:skm:runtimes:view:models:v1 | P00.04.c → P08.01.a → P08.11 |
| `src/skm/schemas/runtimes/views/route-explain.v1.json` | urn:skm:runtimes:view:route-explain:v1 | P00.04.c → P08.01.a → P08.11 |
| `src/skm/schemas/runtimes/views/runtime-capabilities.v1.json` | urn:skm:runtimes:view:runtime-capabilities:v1 | P00.04.c → P08.01.a → P08.11 |
| `src/skm/schemas/runtimes/views/runtimes.v1.json` | urn:skm:runtimes:view:runtimes:v1 | P00.04.c → P08.01.a → P08.11 |
| `src/skm/schemas/settings/access.v1.json` | urn:skm:settings:access:v1 | P00.04.b |
| `src/skm/schemas/settings/api.v1.json` | urn:skm:settings:api:v1 | P00.04.b → P02.09 → P11.01.a |
| `src/skm/schemas/settings/artifacts.v1.json` | urn:skm:settings:artifacts:v1 | P00.04.b |
| `src/skm/schemas/settings/background.v1.json` | urn:skm:settings:background:v1 | P00.04.b → P02.09 |
| `src/skm/schemas/settings/budgets.v1.json` | urn:skm:settings:budgets:v1 | P00.04.b → P07.03.b |
| `src/skm/schemas/settings/checks.v1.json` | urn:skm:settings:checks:v1 | P00.04.b |
| `src/skm/schemas/settings/commands/import-config.v1.json` | urn:skm:settings:command:import-config:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/commands/lock-value.v1.json` | urn:skm:settings:command:lock-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/commands/remove-value.v1.json` | urn:skm:settings:command:remove-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/commands/set-value.v1.json` | urn:skm:settings:command:set-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/commands/unlock-value.v1.json` | urn:skm:settings:command:unlock-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/commands/unset-value.v1.json` | urn:skm:settings:command:unset-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/context.v1.json` | urn:skm:settings:context:v1 | P00.04.b |
| `src/skm/schemas/settings/defs.v1.json` | urn:skm:settings:defs:v1 | P00.04.b → P02.07.a → P02.07.b |
| `src/skm/schemas/settings/document.v1.json` | urn:skm:settings:document:v1 | P00.04.b |
| `src/skm/schemas/settings/ecosystems.v1.json` | urn:skm:settings:ecosystems:v1 | P00.04.b → I-03.1 |
| `src/skm/schemas/settings/events/config-changed.v1.json` | urn:skm:settings:event:config-changed:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/events/config-locked.v1.json` | urn:skm:settings:event:config-locked:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/events/config-unlocked.v1.json` | urn:skm:settings:event:config-unlocked:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/events.v1.json` | urn:skm:settings:events:v1 | P00.04.b → P02.09 |
| `src/skm/schemas/settings/execution.v1.json` | urn:skm:settings:execution:v1 | P00.04.b → P07.03.b |
| `src/skm/schemas/settings/exports.v1.json` | urn:skm:settings:exports:v1 | P00.04.b → P13.04.a |
| `src/skm/schemas/settings/extensions.v1.json` | urn:skm:settings:extensions:v1 | P00.04.b → P09.01.b |
| `src/skm/schemas/settings/hooks.v1.json` | urn:skm:settings:hooks:v1 | P00.04.b → P10.08.a |
| `src/skm/schemas/settings/integrations.v1.json` | urn:skm:settings:integrations:v1 | P00.04.b |
| `src/skm/schemas/settings/knowledge.v1.json` | urn:skm:settings:knowledge:v1 | P00.04.b → P13.01.a |
| `src/skm/schemas/settings/learning.v1.json` | urn:skm:settings:learning:v1 | P00.04.b → P13.03.a |
| `src/skm/schemas/settings/logging.v1.json` | urn:skm:settings:logging:v1 | P00.04.b → P02.09 |
| `src/skm/schemas/settings/modules.v1.json` | urn:skm:settings:modules:v1 | P00.04.b → P02.09 |
| `src/skm/schemas/settings/planning.v1.json` | urn:skm:settings:planning:v1 | P00.04.b → P05.08 |
| `src/skm/schemas/settings/plugins.v1.json` | urn:skm:settings:plugins:v1 | P00.04.b → P02.09 |
| `src/skm/schemas/settings/policy.v1.json` | urn:skm:settings:policy:v1 | P00.04.b → P07.01.a |
| `src/skm/schemas/settings/queries/explain-config.v1.json` | urn:skm:settings:query:explain-config:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/queries/export-config.v1.json` | urn:skm:settings:query:export-config:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/queries/get-generation.v1.json` | urn:skm:settings:query:get-generation:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/queries/get-history.v1.json` | urn:skm:settings:query:get-history:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/queries/get-host-config.v1.json` | urn:skm:settings:query:get-host-config:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/queries/get-schema.v1.json` | urn:skm:settings:query:get-schema:v1 (`{scope?, section?}`) | P00.04.b → P02.07.b → P02.08.b |
| `src/skm/schemas/settings/queries/get-value.v1.json` | urn:skm:settings:query:get-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/queries/list-entries.v1.json` | urn:skm:settings:query:list-entries:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/results/get-generation.v1.json` | urn:skm:settings:result:get-generation:v1 | P00.04.b → P02.07.a → P02.07.b |
| `src/skm/schemas/settings/results/get-host-config.v1.json` | urn:skm:settings:result:get-host-config:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/results/import-config.v1.json` | urn:skm:settings:result:import-config:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/results/lock-value.v1.json` | urn:skm:settings:result:lock-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/results/remove-value.v1.json` | urn:skm:settings:result:remove-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/results/set-value.v1.json` | urn:skm:settings:result:set-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/results/unlock-value.v1.json` | urn:skm:settings:result:unlock-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/results/unset-value.v1.json` | urn:skm:settings:result:unset-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/runtimes.v1.json` | urn:skm:settings:runtimes:v1 | P00.04.b |
| `src/skm/schemas/settings/storage.v1.json` | urn:skm:settings:storage:v1 | P00.04.b → P02.09 |
| `src/skm/schemas/settings/ui.v1.json` | urn:skm:settings:ui:v1 | P00.04.b → P02.09 |
| `src/skm/schemas/settings/views/effective-key.v1.json` | urn:skm:settings:view:effective-key:v1 | P00.04.b → P02.07.a → P02.07.b |
| `src/skm/schemas/settings/views/export-config.v1.json` | urn:skm:settings:view:export-config:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/views/get-generation.v1.json` | urn:skm:settings:view:get-generation:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/views/get-history.v1.json` | urn:skm:settings:view:get-history:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/views/get-schema.v1.json` | urn:skm:settings:view:get-schema:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/views/get-value.v1.json` | urn:skm:settings:view:get-value:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/views/history.v1.json` | urn:skm:settings:view:history:v1 | P00.04.b → P02.07.a → P02.07.b |
| `src/skm/schemas/settings/views/list-entries.v1.json` | urn:skm:settings:view:list-entries:v1 | P00.04.b → P02.07.b |
| `src/skm/schemas/settings/worker.v1.json` | urn:skm:settings:worker:v1 | P00.04.b → P07.07.a |
| `src/skm/schemas/settings/workspace.v1.json` | urn:skm:settings:workspace:v1 | P00.04.b |
| `src/skm/schemas/workspace/checkout-marker.v1.json` | urn:skm:workspace:checkout-marker:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/add-repository-remote.v1.json` | urn:skm:workspace:command:add-repository-remote:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/archive-project.v1.json` | urn:skm:workspace:command:archive-project:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/archive-workspace.v1.json` | urn:skm:workspace:command:archive-workspace:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/attach-repository.v1.json` | urn:skm:workspace:command:attach-repository:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/bind-checkout.v1.json` | urn:skm:workspace:command:bind-checkout:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/create-project.v1.json` | urn:skm:workspace:command:create-project:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/create-workspace.v1.json` | urn:skm:workspace:command:create-workspace:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/detach-repository.v1.json` | urn:skm:workspace:command:detach-repository:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/record-checkout-verification.v1.json` | urn:skm:workspace:command:record-checkout-verification:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/record-worker-heartbeat.v1.json` | urn:skm:workspace:command:record-worker-heartbeat:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/register-host.v1.json` | urn:skm:workspace:command:register-host:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/register-repository.v1.json` | urn:skm:workspace:command:register-repository:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/register-worker.v1.json` | urn:skm:workspace:command:register-worker:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/commands/exchange-pairing-token.v1.json` | urn:skm:workspace:command:exchange-pairing-token:v1 | P00.04.b → I-10.1a |
| `src/skm/schemas/workspace/commands/set-worker-state.v1.json` | urn:skm:workspace:command:set-worker-state:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/defs.v1.json` | urn:skm:workspace:defs:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/events/checkout-binding-verified.v1.json` | urn:skm:workspace:event:checkout-binding-verified:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/checkout-bound.v1.json` | urn:skm:workspace:event:checkout-bound:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/host-registered.v1.json` | urn:skm:workspace:event:host-registered:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/project-archived.v1.json` | urn:skm:workspace:event:project-archived:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/project-created.v1.json` | urn:skm:workspace:event:project-created:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/repository-attached.v1.json` | urn:skm:workspace:event:repository-attached:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/repository-detached.v1.json` | urn:skm:workspace:event:repository-detached:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/repository-registered.v1.json` | urn:skm:workspace:event:repository-registered:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/worker-registered.v1.json` | urn:skm:workspace:event:worker-registered:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/worker-state-changed.v1.json` | urn:skm:workspace:event:worker-state-changed:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/workspace-archived.v1.json` | urn:skm:workspace:event:workspace-archived:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/events/workspace-created.v1.json` | urn:skm:workspace:event:workspace-created:v1 | P00.04.b → P04.03 |
| `src/skm/schemas/workspace/host/bind-checkout.v1.json` | urn:skm:workspace:host:bind-checkout:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/host/register-this-host.v1.json` | urn:skm:workspace:host:register-this-host:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/host/rotate-worker-token.v1.json` | urn:skm:workspace:host:rotate-worker-token:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/host/verify-checkout.v1.json` | urn:skm:workspace:host:verify-checkout:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/host-results/bind-checkout.v1.json` | urn:skm:workspace:host-result:bind-checkout:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/host-results/register-this-host.v1.json` | urn:skm:workspace:host-result:register-this-host:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/host-results/rotate-worker-token.v1.json` | urn:skm:workspace:host-result:rotate-worker-token:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/host-results/verify-checkout.v1.json` | urn:skm:workspace:host-result:verify-checkout:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/get-host.v1.json` | urn:skm:workspace:query:get-host:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/get-project.v1.json` | urn:skm:workspace:query:get-project:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/get-workspace.v1.json` | urn:skm:workspace:query:get-workspace:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/list-hosts.v1.json` | urn:skm:workspace:query:list-hosts:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/list-project-repositories.v1.json` | urn:skm:workspace:query:list-project-repositories:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/list-projects.v1.json` | urn:skm:workspace:query:list-projects:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/list-repositories.v1.json` | urn:skm:workspace:query:list-repositories:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/list-workers.v1.json` | urn:skm:workspace:query:list-workers:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/list-workspaces.v1.json` | urn:skm:workspace:query:list-workspaces:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/match-checkout.v1.json` | urn:skm:workspace:query:match-checkout:v1 | P00.04.b → P04.04.a |
| `src/skm/schemas/workspace/queries/resolve-checkout.v1.json` | urn:skm:workspace:query:resolve-checkout:v1 | P00.04.b → P04.04.a |
