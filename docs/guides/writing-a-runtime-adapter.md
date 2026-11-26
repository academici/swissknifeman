# Writing a runtime adapter

A runtime adapter launches and observes an unattended agent on a worker.
Implement `AgentRuntime` through `skm.plugin_api`. The port covers detection,
capabilities, self-loaded context, session start, normalized events,
cancellation and the terminal result. Build the launch from the granted
context, permissions and isolation requirements. Keep the request, secrets
and provider-native payloads behind the adapter boundary. Missing terminal
output must surface as an incomplete stream. Report unknown usage when the
provider cannot establish it.
[Runtime port](../../src/skm/modules/runtimes/ports.py) ·
[Runtime contract](../architecture/runtimes-context-extensions.md#runtime-contracts)

## Declare and verify capabilities

Register a `Side.HOST` runtime component in the distribution's `skm.plugins`
entry point. Match the entry point name to the `PluginManifest.id`. Put
`capabilities.toml` and `error_rules.toml` under
`<top_package>/skm_runtimes/<runtime_id>/` so the control plane can read the
declarations without importing the adapter. Declare native, adapted,
unsupported or unknown capabilities, and account for the instructions and
settings the client loads on its own. Supply model entries through an
operator pack's `runtime_catalog` resource. [Plugin contract](../adr/0022-plugins-stable-api.md) ·
[Example data](../../src/skm/adapters/runtimes/claude_code/capabilities.toml)

Enforcing features need fresh verification tied to the exact
`VerificationContext`. Bind the host, runtime/version, executable digest,
OS/kernel, adapter version, isolation profile and launch configuration digest.
Reverify after a change to any input. Refuse before spawn if the launch cannot
satisfy a required capability. A static declaration and an offline replay
describe behavior under their own conditions. Keep live provider checks
opt-in and record observations only for the combination actually exercised.
[Runtime acceptance evidence](../evidence/runtime-matrix.md) ·
[Config isolation evidence](../evidence/runtime-config-isolation.md)

Run `skm plugins lint <source-directory>` to check Python imports. Run
`skm plugins lint <installed-distribution-name>` to check the installed
package's Python imports, entry points and runtime TOML. Exercise the
manifest factory, bounded event decoding, successful and
missing terminal records, cancellation, redaction, and refusals with offline
fixtures before any live probe. [Plugin fixture](../../tests/fixtures/plugins/skm-plugin-fixture/) ·
[Runtime contract tests](../../tests/contracts/runtimes/)


## Antigravity CLI

The built-in `antigravity` adapter detects `agy` on the worker. Configure an
explicit path with `runtimes.binaries.antigravity` in the host runtime binary
map and use `skm runtime detect` to inventory the binary and available flags.
The default runtime preference excludes AGY. To select it explicitly, the
instance's `runtimes.allowed` ceiling must include `antigravity` and the role
route must pass the normal worker and capability admission.

The adapter is limited to read-only checkouts on a trusted Linux worker with
Landlock ABI 3 or later. The role must choose the `landlock` profile and grant
zero workspace writes. Current AGY builds discover workspace customization,
so standard built-in profiles (such as `read-only` or `workspace-contained`)
are refused by config-isolation admission (`project_settings_not_suppressible`).
Inventory detection alone supplies neither capability verification nor
authorization. Do not relax shared routing or policy settings just to admit a
provider.

SKM sends one NDJSON prompt to a process with a private HOME and XDG paths.
For enterprise credentials the worker can supply documented AGY Application
Default Credentials environment variables. The adapter accepts an ordinary
successful process exit with a matching init and result for the requested
workspace and selector. Missing results, print timeouts, duplicates and
model or conversation mismatches fail the step. Reported input stays unknown
when cache accounting is ambiguous. The adapter does not provide resume, MCP
binding, or a verified network, IPC, metadata, or tool isolation boundary.
[Headless protocol](https://antigravity.google/docs/cli/headless/) ·
[Antigravity authentication](https://antigravity.google/docs/cli/install/)

## Host accounts and quota probes

`skm accounts` lists slots from `$XDG_CONFIG_HOME/skm/provider-pool.toml`
(default `~/.config/skm/provider-pool.toml`). `skm providers probe` reads the
six configured quota groups for each slot. Both commands accept `--registry PATH`
and `--json`. The same registry supplies the host pool when its caller omits the slot list.

The keys under `groups` identify the host's six accounting buckets. Each value is
the requested model selector for model-specific probes, or an empty string for a shared
bucket. The following example names six buckets and configures one quota source.

```toml
[groups]
frontier = "opus"
implementation = "sonnet"
economy = "haiku"
session = ""
weekly = ""
credits = ""

[slots.primary]
runtime_id = "claude_code"

[slots.primary.quota_urls]
frontier = "https://quota.example.org/primary/frontier"
```

Each configured endpoint serves an HTTPS GET with a JSON integer counter such as
`{"remaining": 12}`. Missing readings produce `unknown` and a null counter. An
explicit zero means exhausted. HTTP 402, 429 and 529 identify a payment requirement,
a rate limit and provider overload, respectively. Each excludes that slot for the
affected group in the current ranking.

The host passes available slots, effective `runtimes.allowed`, supported capabilities
and quota readings to `AdaptiveExecutorRouter.rank`. Higher configured provider weights
rank first, with ties resolved by runtime ID and slot ID. A missing weight defaults to
zero. `ProviderPoolManager.acquire_ranked` tries the next eligible slot if another
worker has already leased the first choice. A local execution probe can supply its
`RuntimeObservation` to detect Opus fallback. The provider-reported model remains
available on the observation for execution attribution.
