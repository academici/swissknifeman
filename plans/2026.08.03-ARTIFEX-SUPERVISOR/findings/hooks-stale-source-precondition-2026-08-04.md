# Effective Codex hook prerequisite — 2026-08-04

## Scope and command

This is read-only repository preflight evidence for post-D76 design remediation. No repair or
update command was run.

From repository root:

```text
packages/harness/bin/harness hooks --provider codex --target /home/vostrikov/projects/packages/swissknifeman --observer --trusted --dry-run
```

The command exited 0 but reported `Статус: warning` and exactly two non-green actions:

```text
harness.codex.lifecycle.hooks: stale-source → update (source-changed)
harness.codex.lifecycle.handler: stale-source → update (source-changed)
```

The dry-run plan hash was
`sha256:07046506f26558afb8088ec0fad45fcaf718fd0a32f962788fb12ec3e7d43ca2`.
An exit code of zero is therefore not effective-hook GREEN. RAG:— (repo-grounded: observed
worktree-local Harness output on 2026-08-04).

## Owning command surface

`packages/harness/bin/harness hooks --help` exposes the same target/provider surface with
`--repair`; the repair/recheck producer can therefore remain worktree-local and avoid package
source edits. The exact future mutation command is:

```text
packages/harness/bin/harness hooks --provider codex --target /home/vostrikov/projects/packages/swissknifeman --observer --trusted --repair
```

Its acceptance recheck is the original `--dry-run` command and must return `Статус: ok` with no
`stale-source` or `→ update` rows. This finding does not authorize or perform that mutation; it
only identifies the existing owner surface for a plan item. RAG:— (repo-grounded: worktree-local
CLI help and dry-run output).

## Verdict

P4.4 cannot start directly after P4.3 while this prerequisite is known non-green. A dedicated
plan item must own one exact repair, one exact recheck and a minimized evidence carrier before
P4.4 consumes effective-hook GREEN. Syntax checks, doctor output or exit 0 with `warning` are not
substitutes.

