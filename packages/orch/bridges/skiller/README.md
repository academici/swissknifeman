# Bridge orch ↔ Skiller

The only place where orch knows Skiller. The orch core stays neutral (role manifests list skill names; nothing
here is imported by the core), and Skiller knows nothing about orch: this bridge asks Skiller's generic
`skiller resolve <skill…> --json` and combines the answer with orch's own data.

| Verb | Entrypoint | Direction |
| --- | --- | --- |
| `resolve-role` | `resolve_role.py` | orch → Skiller: a role's skill closure and its delivery mode |

```text
python3 packages/orch/bridges/skiller/resolve_role.py (--role ID | --manifest PATH) --provider claude-code|codex|grok [--binding native|cao|claude-only] [--json]
```

- Reads `roles/<id>.json` (or `--manifest`) and `bindings/capabilities/<binding>--<provider>.json` of orch.
- Passes the manifest's `skills[].name` to the partner; transitive requirements come back in `skills[].required_by`.
- `--json`: `{"role", "provider", "skills": [{"name", "id", "bucket", "path", "required", "required_by"}],
  "delivery": {"mode", "source"}, "diagnostics": []}`. `required` is true for a manifest-required skill and for
  anything a required skill needs. Without `--json` a short table is printed.
- `delivery.mode` is the seed's `skill_delivery.mode`; a missing or unreadable seed gives `unknown` and a
  `DELIVERY_UNKNOWN` warning.
- Errors are `CODE: message` on stderr, exit 1: `ROLE_UNKNOWN`, `ROLE_MANIFEST_INVALID`, `CONTRACT_VERSION`
  (manifest is not `exec/v1`), `RESOLVE_FAILED`. An error diagnostic from the partner (`SKILL_UNKNOWN`,
  `SKILL_AMBIGUOUS`) is reported with the partial result and exit 1.
- Nothing is installed or delivered to a run; that is the engine's job.

## Finding the partner

`SKM_SKILLER_ROOT` (a package root holding `bin/skiller`) → a `skiller` command on `PATH` → in the monorepo,
the sibling package. Otherwise `BRIDGE_PARTNER_UNAVAILABLE` with exit 3; the orch core keeps working.

## Tests

`bridges/skiller/tests` run with the package validate (`scripts/validate.sh`); the conformance cases are skipped
when the partner is not found.
