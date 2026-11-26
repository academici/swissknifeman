---
type: plan-archived
plan: billing-v2
plan_id: 019a3f00-1a2b-7c3d-8e4f-5a6b7c8d9e0f
revision: 4
status: archived
archived: "2026-10-25T16:20:00Z"
project: Demo service
repository: "github.com/example/demo-service"
note_id: 019a4f00-7e8d-7c6b-9a59-483726150a0c
event_id: 019a4f00-7e8d-7c6b-9a59-483726150a0b
occurred_at: "2026-10-25T16:20:00Z"
materialized_at: "2026-10-25T16:20:04Z"
render_version: 1
revision_id: 019a3f00-1a2b-7c3d-8e4f-5a6b7c8d9e10
run_id: 019a4b00-1111-7222-8333-444455556666
classification: restricted
source: skm
tags: [plan, archived]
---
# Billing v2: invoices with taxes

> Invoices compute totals with regional tax rates, and the HTTP API exposes them.
> Old totals stay readable for one release.

| Phase | Title | Status |
| --- | --- | --- |
| P1 | Tax rates model | accepted |
| P2 | Invoice totals and API | accepted with deviations |
| P3 | Removal of legacy totals \| cleanup | skipped |

Counts: items 9, accepted 7, accepted with deviations 1, failed 0, skipped 1.

Archived 2026-10-25T16:20:00Z.
