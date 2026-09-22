# P5 privacy and portability results

## Result

P5.1 repairs confirmed N-08 and N-09 with one policy-owned boundary:

- frozen `BundleInputPolicy/v1`, rather than a manifest/caller declaration, requires
  minimization and forbids raw transcript bodies, chain-of-thought, tool payloads and
  secrets;
- `classify_execution_input()` preserves the original and normalized spelling plus an
  explicit `internal|external|invalid` `path_kind`; Task Contract compilation retains
  external/invalid paths until `portability_lint()` returns a typed refusal;
- bundle and plan input paths use platform-neutral lexical checks for POSIX absolute,
  Windows drive/UNC, URI, home/env and traversal forms, followed by `lstat`/no-follow,
  regular-file and canonical-containment checks before member bytes are read;
- manifest aliases are normalized before duplicate/set comparison; links and special
  files fail closed; the canonical and Skiller source-evidence templates now import the
  policy rather than copying caller-controlled privacy data.

## Security boundary and focused review

The affected assets are minimized execution evidence and repository-local input bytes;
the attacker is a bundle/spec author controlling path spellings, manifest data and file
types. The repair denies disclosure/path escape and tampering paths without adding an
authentication or compliance claim. Negative coverage includes policy tampering,
sensitive transcript/secret bytes, POSIX/drive/UNC/file URI/home/env/traversal paths,
normalized duplicates, outward and broken symlinks and a FIFO. Positive coverage is a
minimized nested regular-file bundle. Review was intentionally light and limited to this
trust boundary; no independent audit was admitted.

## Compatibility and migration

- Repository Task Contract readers remain compatible because legacy
  `path/kind/producer` fields are retained; `original`, `normalized`, `path_kind` and
  `rejection` are additive. A third-party reader enforcing the archived v1
  `additionalProperties: false` shape must be upgraded before consuming newly compiled
  contracts; deterministic recompilation is the migration and old committed contracts
  remain readable.
- `bundle_lint(..., declared_privacy=...)` remains callable, but the value is now only an
  assertion and must equal `BundleInputPolicy/v1`; callers should pass
  `policy=BUNDLE_INPUT_POLICY` or omit the legacy declaration.
- The current P1.1 and P2.1 bundle sample kept byte-identical declarations and entry
  counts (21 and 13). Their manifest hashes change only because referenced source/test
  bytes changed; deterministic `plan_bundle.build()` regeneration is the migration.
- Rollback may narrow a policy allowlist only through a new policy revision and negative
  test. It must not restore caller-owned exclusions, silent external-input dropping or
  link/special-file reads.

## Validation

- Focused Task Contract/Bundle tests: 36 GREEN; the complete Task suite after
  implementation: 1159 GREEN, 1 skipped. The final broken-link case is included in the
  closure rerun below.
- `bash packages/task/scripts/validate.sh`: GREEN; provider projections no-op and plan
  conflict lint GREEN.
- `skiller registry`: regenerated canonical registry/provider outputs after the snippet
  change. Skiller's release dry-run now reports only the pre-existing foreign Harness
  immutable tuple (`package.harness@0.5.5`); P5-owned `general`, `task` and `skiller`
  versions were advanced.
- `git diff --check`: GREEN.

## Edufy P14.3 field gate

The paired run stopped before creating worktrees, as required by the frozen protocol's
invalid-run rules. At pinned Edufy commit
`11bbed76ada4cd7077ab388228227b9f33b1f224`, the P14.3 specification hashes to
`12c04c6bf17f449dedb821076211608fad2ab6dfe80bd734a52b3599de01da94`, not the frozen
`5095da298c4f86deefeb5a125502e4cc2d5656fa988c40387bb557237238575b`; its committed
handoff names P9.2, not P14.3, as Next. Launching either arm would therefore fabricate
readiness and produce an invalid comparison. The safe recovery is to repin the task/spec
and predecessor state in P6, then run both isolated arms with disposable services. The
original Edufy checkout remained untouched (HEAD observed
`f53b40f817a8b2c28fd27640d583c4026dc923dc`, dirty baseline 198 entries).

## Documentation decision

No additional package docs were changed: P6 explicitly owns public reason-code,
prompt/docs and consumer migration reconciliation. P5 records the compatibility contract
here and synchronizes the two executable source-evidence templates, avoiding premature
public wording before the invalid Edufy field sample is repinned.
