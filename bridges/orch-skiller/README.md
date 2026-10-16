# Bridge orch ↔ Skiller (`orch-skiller`)

The only place where orch knows Skiller. The orch core stays neutral (role manifests list skill names; nothing
here is imported by the core), and Skiller knows nothing about orch: this bridge asks Skiller's generic
`skiller resolve <skill…> --json` and combines the answer with orch's own data.

| Verb | Entrypoint | Direction |
| --- | --- | --- |
| `resolve-role` | `resolve_role.py` | orch → Skiller: a role's skill closure and its delivery mode |
| `select` | `resolve_role.py --select` | orch → Skiller: the skills of a role chosen from the work (`skiller select`, policy `auto`) |

```text
python3 bridges/orch-skiller/resolve_role.py (--role ID | --manifest PATH | --all-roles) --provider claude-code|codex|grok [--binding native|cao|claude-only] [--json]
```

- Reads `roles/<id>.json` (or `--manifest`) and `bindings/capabilities/<binding>--<provider>.json` of orch.
- Passes the manifest's `skills[].name` to the partner; transitive requirements come back in `skills[].required_by`.
- `--json`: `{"role", "provider", "skills": [{"name", "id", "bucket", "path", "digest", "required", "required_by"}],
  "delivery": {"mode", "source"}, "diagnostics": []}`. `required` is true for a manifest-required skill and for
  anything a required skill needs. Without `--json` a short table is printed.
- `digest` is the `sha256:` content digest of the skill from `skiller describe <id> --json` (skill-descriptor/v1). When
  the partner cannot describe a skill, `digest` is absent and the warning `SKILL_DIGEST_UNKNOWN` (with `skill`) is
  added; the exit code is not affected.
- `--all-roles` resolves every role manifest of orch and prints `{role_id: [{"name", "digest"}]}` as JSON, the file
  `orch.py prepare --skills` takes. A skill without a digest is left out; diagnostics go to stderr as JSON lines.
- `delivery.mode` is the seed's `skill_delivery.mode`; a missing or unreadable seed gives `unknown` and a
  `DELIVERY_UNKNOWN` warning.
- Errors are `CODE: message` on stderr, exit 1: `ROLE_UNKNOWN`, `ROLE_MANIFEST_INVALID`, `CONTRACT_VERSION`
  (manifest is not `exec/v1`), `RESOLVE_FAILED`. An error diagnostic from the partner (`SKILL_UNKNOWN`,
  `SKILL_AMBIGUOUS`) is reported with the partial result and exit 1.
- `--select --role ID --provider P [--paths P…] [--project DIR] [--budget N] [--include ID…] [--exclude ID…]` asks
  `skiller select --policy auto --json`: the role's required skills (manifest or `role-skills.json`, `required: true`) go in as explicit
  includes, path and dependency triggers add the rest. Output `{"role", "provider", "skills": [{"name", "id", "path",
  "reason", "tokens"}], "excluded": [{"id", "reason"}], "discoverable", "tokens", "diagnostics"}`; `path` is the
  absolute `SKILL.md` the conductor reads. `SELECT_FAILED` (exit 1) when `skiller select` gives no JSON. The
  transitive `requires` of a selected skill is not added here.
- Nothing is installed or delivered to a run; that is the engine's job.

## Finding the partner

`SKM_SKILLER_ROOT` (a package root holding `bin/skiller`) → a `skiller` command on `PATH`. The orch data (role
manifests, capability seeds) comes from `SKM_ORCH_ROOT` (a root holding `scripts/orch.py`) → an `orch` command on
`PATH`. There is no search by neighbouring folders. A partner that is not found gives `BRIDGE_PARTNER_UNAVAILABLE`
with exit 3; the orch core keeps working.

## Tests

`tests/` run with `bash scripts/test.sh` of the bridge or the hub runner `bash scripts/test-bridges.sh`; the
conformance cases are skipped when a partner is not found.
