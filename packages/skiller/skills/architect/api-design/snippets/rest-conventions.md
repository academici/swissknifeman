# Optional REST conventions

Follow the API's existing contract. For a new contract, consider plural resources, consistent
HTTP methods/statuses/errors, shallow nesting, and bounded collection pagination. Select URL,
header or schema compatibility/versioning based on actual consumers; `/v1/` is not mandatory.
Action endpoints are valid where needed. GET does not request mutation; credentials stay out
of URLs. Cursor and page pagination are alternatives, not interchangeable defaults.
