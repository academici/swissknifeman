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
  "commit": {
    "type": "feat",
    "scope": "auth",
    "subject": "rotate refresh tokens and revoke family on reuse",
    "body": "Issue a new one-time refresh token in the same family and mark the prior token used in a single transaction; revoke the family when a used token is presented.",
    "breaking": false
  },
  "changelog_entry": {
    "section": "Security",
    "text": "Refresh tokens are single-use; presenting a used token revokes the token family."
  }
}
```

- `commit.type`: `feat | fix | refactor | docs | test | build | chore`.
- `commit.scope`: optional lowercase `[a-z0-9-]{1,40}` module or component identifier.
- `commit.subject`: single line of 3..72 characters without trailing newline.
- `commit.body`: factual summary (up to 4000 characters) without Git trailers.
- `commit.breaking`: optional boolean (`true` only for documented breaking changes).
- `changelog_entry`: optional `{ "section": "Added" | "Changed" | "Fixed" | "Removed" | "Security", "text" }`.
