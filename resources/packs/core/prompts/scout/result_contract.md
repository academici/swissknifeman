+++
schema = "urn:skm:extensions:prompt-block:v1"
block_type = "result_contract"
variables = ["role.result_schema"]
+++
## Result

End your session with exactly one JSON document and nothing after it. It must match the schema
`{{ role.result_schema }}`:

```json
{
  "schema": "{{ role.result_schema }}",
  "status": "complete",
  "summary": "Concise orientation to the modules, contracts and tests touched by this task.",
  "relevant_paths": [
    {
      "mount": "repo",
      "path": "src/auth/token_repository.py",
      "why": "Repository contract the implementation calls inside the transaction."
    }
  ],
  "entry_points": [
    {
      "mount": "repo",
      "path": "src/http/auth_routes.py",
      "why": "Caller of the token service."
    }
  ],
  "risks": [
    "Compare token expiry against database time rather than process wall clock."
  ],
  "suggested_checks": [
    {
      "argv": ["python", "-m", "pytest", "tests/auth", "-q"],
      "why": "Covers existing token storage contracts."
    }
  ],
  "open_questions": []
}
```

- `status`: `complete` when the relevant context was mapped; `insufficient` when missing files or unresolved
  ambiguities prevent a reliable map.
- `relevant_paths`: repository-relative paths (`mount`, `path`, `why`) the executor should inspect or modify.
- `entry_points`: optional list of callers or surface entry points (`mount`, `path`, `why`).
- `risks`: optional concrete technical risks observed in the codebase.
- `suggested_checks`: optional focused commands (`argv`, `why`) relevant to the mapped paths.
- `open_questions`: unresolved unknowns or ambiguities discovered while mapping; `[]` when none.
