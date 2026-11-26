# Security

The following invariants apply to the local unpublished pre-refactor
`2.0.0` candidate. Host enforcement depends on the capabilities verified
for the particular installation. [Platform support](docs/reference/platform-support.md)

## Access, execution and host boundaries

| ID | Invariant |
| --- | --- |
| S1 | HTTP authenticates bearer tokens using a peppered HMAC and checks expiry and revocation. |
| S2 | Embedded CLI identity uses the private owner-token file (mode `0600`) or an explicitly supplied token. |
| S3 | Authorization evaluates the resource scope and role memberships. Token restrictions can only narrow permission. |
| S4 | Workspace-scoped keys and resource-scope authorization prevent unauthorized cross-workspace reads by ID. Workspace membership grants reads across its projects (SURF-17). |
| S5 | Worker claims require a matching workspace registration, worker authority and capabilities. Assignment credentials cannot claim work. |
| S6 | Worker writes require the current lease fence in the transaction. |
| S7 | Runtime and check launch require proven filesystem, network, credential and lifecycle properties where policy demands them. Missing proof blocks spawn. Write-scope checks also apply to acceptance. |
| S8 | Interactive hooks enforce tool policy. Unattended execution uses runtime permissions and host isolation. |
| S9 | Resource profiles, skills and steering are bounded by the policy ceiling during installation and context assembly. |
| S10 | Configuration narrowing and inherited locks prevent a nearer scope from weakening a ceiling. |
| S11 | Approval binds the normalized argument digest, expiry and use limit. Execution checks that binding. |
| S12, S12a | Secret fields use references and resolved values are redacted at output boundaries. Typed allowlists restrict diagnostic metadata in normal and debug output. |
| S13 | Untrusted path input is checked for containment and symlink escape. |
| S14 | SQL uses parameterized values and allowlisted identifiers. |
| S15 | Process calls use argv by default. Explicit shell checks require a risk acknowledgment and policy authorization. |
| S16 | Executable plugins require an instance allowlist. Control-plane code needs a separate grant. Host runtime metadata can be read as data. |
| S17 | Repository instructions and materials enter context as untrusted content and cannot alter policy. |
| S18 | Reading blob bytes requires an authorized file version and current permission or applicable worker grant. A digest or diagnostic reference grants no access. |
| S19 | Browser API authentication uses the bearer header and an origin allowlist. |
| S20 | Upload body limits are enforced before accepting an oversized upload. |
| S21 | Checkout locators require `checkout.read_locator`. |
| S22, S22a | Unattended client config isolation requires exact launch evidence and suppression of unsafe user and project settings. Missing required capability blocks routing or launch. |
| S23 | Runtime/MCP credentials are bound to the assignment and step, capped by the lease and parent credential expiry, and revoked at the lifecycle boundary. Worker management and database credentials stay out of the runtime. |
| S24 | Enforcement hooks deny when authority is unavailable. |
| S25 | Live policy is checked at stage admission so revoked authority can block a later stage. |
| S26 | Pack config fragments require built-in or operator trust. Security ceiling keys reject contributions at pack level. |

[Security test suite](tests/security/) ·
[Workspace access model](docs/guides/concepts.md#scopes-and-access) ·
[Runtime config-isolation checks](docs/evidence/runtime-config-isolation.md)

## Operations

Use TLS for remote operator and worker connections, separate application and
migrator database roles, and private token files. Verify the requested backend
properties before admitting unattended work. Keep archives private and
restore into quarantine. Activation revokes restored bearer tokens and embedded
grants. Recovery requires verified bindings for host and external effects.
[Server deployment](docs/guides/server-mode.md) ·
[Quarantine restore](docs/evidence/backup-restore.md)
