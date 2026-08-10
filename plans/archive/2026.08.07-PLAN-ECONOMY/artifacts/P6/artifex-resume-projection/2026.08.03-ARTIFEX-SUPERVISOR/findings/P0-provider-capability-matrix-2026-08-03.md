# Provider capability matrix — 2026-08-03

## Method

Both installed clients were invoked from a freshly initialized temporary Git repository. The driver used a 45-second cap, 65,536-byte capture cap, read-only or plan permission, and retained no raw client output. The temporary directory is removed after the normalized records pass validation.

## Verdict

The matrix distinguishes supported, degraded, unsupported, and unknown local states; it does not assert provider parity. Harness remains a Claude Code-only exec-wave baseline, while provider audit is a read-only configuration audit.

## Provider observations

| Provider | Availability | Version | Structured output | Session identity | Usage / cache / cost |
|:--|:--|:--|:--|:--|:--|
| codex | available | codex-cli 0.146.0 | supported | observed | observed / unknown / unknown |
| claude-code | available | 2.1.220 (Claude Code) | degraded | observed | observed / unknown / observed |

The exact non-secret invocation shapes, exit classes, and observed event-field categories are in `artifacts/P0/provider-probes/`. Unsupported, authentication, quota, and missing fields remain first-class local observations rather than successful probes.
