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
  "mode": "advice",
  "problem_ref": "question:0193a000-0000-7000-8000-000000130001@1",
  "options": [
    {
      "id": "revoke-family",
      "label": "Revoke the entire token family on reuse",
      "pros": "Satisfies the one-time rotation requirement and recorded security decision.",
      "cons": "Concurrent client tabs without single-flight coordination must re-authenticate."
    },
    {
      "id": "grace-window",
      "label": "Permit token reuse within a short grace window",
      "pros": "Tolerates uncoordinated tab races.",
      "cons": "Violates strict one-time rotation."
    }
  ],
  "recommendation": {
    "option_id": "revoke-family",
    "text": "Revoke the active token family immediately when a rotated token is reused."
  },
  "confidence": "high",
  "category": "bounded_ambiguity",
  "needs_owner": false,
  "rationale": "Recorded decision D1 and the requirement contract mandate strict single-use rotation.",
  "assumptions": ["Client single-flight coordination is handled by the planned client task."],
  "sources": [
    { "kind": "decision", "ref": "D1", "note": "Strict one-time refresh token rotation" },
    { "kind": "file", "ref": "src/auth/rotation.py" }
  ]
}
```

- `mode`: `advice` (standard consultation), `critique` (requires non-empty `sources`), or `plan_audit` (requires
  `verdict` and the 10-item `checklist`).
- `problem_ref`: exact problem identifier supplied by SKM (`question:<uuid>@<rev>`, `checks:<n>`, `findings:<n>`, or
  `readiness:<uuid>`).
- `recommendation` and `category` (`local_reversible | bounded_ambiguity | cross_module | architectural | authority_required | external_fact`)
  are required when `mode` is `advice` or `critique`.
- `confidence`: `low | medium | high`; `needs_owner`: `true | false`; `sources`: list of `{ "kind", "ref", "note" }`
  where `kind` is `file | check | finding | decision | url | material`.
