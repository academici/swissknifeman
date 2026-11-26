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
  "query": "Does OAuth 2.0 Security BCP recommend revoking the token family on refresh token reuse?",
  "claims": [
    {
      "text": "When reuse of an invalidated refresh token is detected, the authorization server should revoke the active tokens of that grant.",
      "document_ids": ["0193a000-0000-7000-8000-000000200001"]
    }
  ],
  "contradictions": [],
  "unknowns": [],
  "sources_used": ["rfc-mirror"],
  "follow_up_queries": [],
  "usage_complete": true
}
```

- `status`: `complete` when the supplied documents answer the query, `partial` when material `unknowns` remain, or
  `blocked` when required sources were unavailable or unusable.
- `query`: the research question addressed by this result.
- `claims`: each claim has `text` and non-empty `document_ids` (exact UUIDs of documents from this step's research
  batches; SKM validates membership).
- `contradictions`: conflicting statements across retrieved sources (`[]` when none).
- `unknowns`: unanswered questions or unverified points (`[]` when none).
- `sources_used`: kebab-case identifiers of the research sources used (`[]` when none).
- `follow_up_queries`: focused follow-up queries for unresolved gaps (`[]` when none).
