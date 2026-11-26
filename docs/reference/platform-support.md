# Platform support

This matrix describes the local unpublished pre-refactor `2.0.0` candidate
(OPS-NEW-06). **Supported** means the linked check exercised the stated
combination and property. **Unsupported** means the named mechanism cannot
provide that property or the candidate refuses it. **Unverified** means
there is no matching executed evidence. Each cell applies only within the
scope named in its row.

| Host and configuration | App startup | Runtime and version | Filesystem isolation | Network isolation | Full process cleanup | Disk containment |
| --- | --- | --- | --- | --- | --- | --- |
| Ubuntu 24.04 x86-64, PostgreSQL 16.4, local/serve with plain `git_worktree` and trusted process group | supported | unverified | unsupported (Git separation and write-fence detection) | unsupported | unsupported (escaped descendants) | supported for SKM-managed writers. Arbitrary checkout writes are unsupported |
| Linux, Landlock write backend | unverified | unverified | supported for verified write restrictions. Read isolation from Landlock alone is unsupported | unsupported for the write backend alone | unsupported for the write backend alone | unsupported for arbitrary writes |
| Linux, local Docker container canary fixture, `network=none` | unverified | unverified | supported for the fixture's tested mount grants and read-only protections | supported for the fixture's no-network mode. A deployed egress allowlist is unverified | unverified for full cleanup under worker loss | unsupported for physical quotas on bind mounts |
| Linux runtime adapters, `claude_code` 2.1.266, `codex` 0.165.0 and `grok` 0.1.0 fixture versions | unverified | supported in offline replay/emulation. Live versions are unverified. Isolated unattended Grok is unsupported | unverified | unverified | unverified | unverified |
| `cursor` headless execution, version unknown | unverified | unsupported in the candidate | unverified | unverified | unverified | unverified |
| macOS, Windows or other untested host/backend combinations | unverified | unverified | unverified | unverified | unverified | unverified |

- **Startup and control plane.** Real Linux `skm serve` processes on PostgreSQL
  exercised readiness, HTTP and SSE. The local lifecycle check also starts
  the managed worker process against PostgreSQL. The web guide describes the
  corresponding browser auth and reconnect behavior.
  [Measured host and workload](../measurements.md#стенд) ·
  [Local lifecycle check](../../tests/e2e/test_local_lifecycle.py) ·
  [Web operator guide](../guides/web.md)
- **Runtime and isolation.** The recorded Linux run covers offline adapter
  contracts, Landlock and Docker security canaries, and ownership/process-group
  refusal paths. The Docker result is scoped to the local canary fixture and
  the socket used in that run. Production image digests and other daemon
  configurations remain unverified. Required capabilities must match the live
  host, executable and sandbox facts. Missing required isolation fails closed
  before spawn.
  `SKM_EVALS=1` provider checks are `opt_in` and remain **unverified** for this
  baseline. [Executed runtime and security checks](../evidence/runtime-matrix.md#execution-record) ·
  [Docker canary fixture](../../tests/security/test_sandbox_profiles.py) ·
  [Process containment checks](../../tests/security/test_process_containment.py)
- **Disk.** Bounded writers and a per-filesystem reserve cover SKM-managed
  captures and storage writes. Hard containment of arbitrary process writes
  requires a backend with an enforced quota. [Disk-pressure checks](../../tests/security/test_disk_pressure.py) ·
  [Isolation contract](../evidence/runtime-config-isolation.md)

## Operating limits

- Use an isolated `git_worktree` for production execution. Shared, actively
  edited user checkouts are unsupported for this baseline. Submodule or nested
  repository mutation and atomic writes across repositories are outside the
  supported path.
- Initialize 0.1.0 from its clean PostgreSQL baseline. Drain workers before stopping
  a running 0.1.0 server for maintenance.
  [Server maintenance procedure](../guides/server-mode.md#maintain-a-010-installation)
- Restore PostgreSQL and referenced immutable blobs into quarantine. Recovery
  needs fresh host bindings, credential rotation and verification of external
  dependencies. The backup cannot reconstruct host checkouts or worktrees.
  [Executed restore rehearsal](../evidence/backup-restore.md)
- Optional knowledge, learning and export modules can be disabled. Automatic
  learning policy promotion, active-active vault sync, plugin marketplace or
  hot reload, a universal importer or semantic merge, unlimited prompt
  retention and a standalone diagnostics package are outside this baseline.
  [Optional modules and porting record](../porting-log.md#p13--optional-modules-and-core-independence-p13z)
