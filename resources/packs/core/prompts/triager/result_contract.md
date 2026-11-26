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
  "confirmed": [
    {
      "finding_id": "F1",
      "decision": "fix_now",
      "reproduction": {
        "argv": ["python", "-m", "pytest", "tests/auth/test_rotation.py", "-k", "expiry", "-q"],
        "exit": 1,
        "observed": "AssertionError: expired refresh token was rotated when local clock lagged."
      },
      "fix": "Compare expires_at against database now() inside the SELECT FOR UPDATE query."
    }
  ],
  "rejected": [
    {
      "finding_id": "F2",
      "reason": "Naming matches the module convention and causes no behavioral or contract defect."
    }
  ],
  "summary": "Confirmed F1 for immediate fix with reproduction; rejected F2 as non-defect style preference."
}
```

- Every finding id (`F<n>`) of the review round must appear exactly once in either `confirmed` or `rejected`.
- `confirmed`: each item has `finding_id`, `decision` (`fix_now` or `defer`), optional `reproduction` (`argv`,
  `exit`, `observed`), and optional `fix` guidance within the task write scope.
- `rejected`: each item has `finding_id`, `reason`, and `reproduction` (`argv`, `exit`, `observed`) whenever a
  reproduction ran (mandatory when rejecting a `blocker` or `major` finding).
- `summary`: concise summary of the triage decisions.
