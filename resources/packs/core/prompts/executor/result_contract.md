+++
schema = "urn:skm:extensions:prompt-block:v1"
block_type = "result_contract"
variables = ["role.result_schema", "permissions.write_scope"]
+++
## Result

End your session with exactly one JSON document and nothing after it. It must match the schema
`{{ role.result_schema }}`:

```json
{
  "schema": "{{ role.result_schema }}",
  "status": "done",
  "summary": "What changed and why, in a few lines.",
  "changed_paths": [
    { "mount": "repo", "path": "src/webhooks/delivery.py", "change": "modified" },
    { "mount": "repo", "path": "tests/test_delivery.py", "change": "added" }
  ],
  "evidence": ["pytest tests/test_delivery.py -q: 4 passed"],
  "checks_run": [
    { "id": "V1", "cmd": "pytest tests/test_delivery.py -q", "exit": 0 }
  ],
  "open_issues": [],
  "questions": [],
  "self_check": {
    "performed": true,
    "notes": "Verified retry backoff and negative payload cases.",
    "criteria": [
      { "criterion_key": "AC1", "status": "met", "evidence": "test_delivery_retry" }
    ]
  },
  "recommend_review": { "recommended": false },
  "subagents": { "used": false, "disclosed": true }
}
```

- `status`: `done`, `done_with_deviations` (requires a `deviation` item in `open_issues`), `done_pending_checks`
  (requires a `pending` item in `open_issues`), or `blocked` (requires an `escalation` item in `open_issues`).
- `changed_paths`: every repository path you added, modified, deleted or renamed (`mount`, `path`, `change`, and
  `old_path` for renames); each must lie inside the write scope:
{{ permissions.write_scope }}
- `checks_run`: only checks you actually ran (`{ "id": "V1", "cmd", "exit" }` or
  `{ "id": "V1", "procedure", "verdict": "pass" | "fail" }`). SKM runs acceptance checks independently.
- `open_issues`: `{ "text", "kind": "escalation" | "blocker" | "pending" | "deviation" | "note" | "assumption" }`.
  A `deviation` requires `class` (`write_set`, `spec_mismatch`, `test_env`, `docs`, `dependency`, `environment`,
  `other`), `outcome` (`accepted`, `follow_up`, `owner_decision`) and `impact`; an `escalation` requires
  `escalation_class` (`decision`, `environment`, `pre_existing_red`, `scope`, `authority`).
- `questions`: `{ "id": "Q1", "revision": 1, "kind": "clarification" | "decision" | "approval" | "credential",
  "text", "blocking": true | false, "assumed", "facts": { "reversibility", "scope_impact", "contract_change",
  "cost_class", "needs_external_fact", "needs_authority" } }`; `assumed` is required when `blocking` is `false`, and
  any `blocking: true` question requires `status = "blocked"`.
- `self_check`: `{ "performed": true | false, "notes", "criteria" }`.
- `recommend_review`: optional `{ "recommended": true | false, "reason" }` when a public contract, schema or
  security boundary changed.
