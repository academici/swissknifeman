# Provider harness conformance

> Generated from the validated provider-harness catalog and conformance report. Do not
> maintain a second capability table here.

`harness doctor --provider-audit [--json]` is a read-only provider conformance layer.
`settings_audit.py` remains the named Claude Code settings checker behind
`harness doctor --settings`; provider audit does not apply Claude merge semantics to Codex.

The validated inventory is 3 profiles, 23 semantic surfaces, 8 MCP descriptors and 44
agent roles. It projects Claude Code and Codex independently from committed common sources.
Unsupported native activation remains a provider-qualified diagnostic; it is never silently
emulated. Reports are canonical JSON with ordered rows, source SHA-256 values, and
missing/extra/duplicate fields for every inventory class.

Operational safety: doctor/check writes nothing; profile and artifact repair use the existing
P2 managed-boundary plan and never adopt unowned bytes. Full access is only the explicit
`self-host-apply` operation with a trusted repository target, never a default, project or
fleet setting. Catalogs, reports and this reference contain secret references only.

For P6 use the JSON report as the deployment preflight input: require `green=true`, empty
missing/extra/duplicates, and preserve every provider-qualified activation diagnostic. For P7
use the same report plus the temp-root check/repair evidence; live/self-host application is
not performed by this command.
