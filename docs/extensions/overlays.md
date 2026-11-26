# Operator Overlays

Operator overlays are installable extension packs (`trust = "operator"`) that customize SKM behavior on top of the neutral `core` pack (`trust = "builtin"`, `priority = 0`) without editing product resources.

## Purpose of Operator Packs

- **Neutral core, explicit customization**: `core` ships neutral role profiles, prompt blocks, workflows, skills, plan templates, and baseline configuration. Team, organization, or personal defaults live in operator overlay packs.
- **Immutable & auditable**: Every overlay version is content-addressed (`sha256` digest), validated against schemas and permission ceilings on install, and pinned per run (`PackPins` + `FrozenConfig`).
- **Scope-controlled activation**: Installing an overlay registers its version in `skm_extensions`, while activation is controlled per scope (`instance`, `workspace`, `project`) via `extensions.packs.enabled`.

## Manifest Structure (`pack.toml`)

```toml
schema = "urn:skm:extensions:pack:v1"
slug = "example-overlay"
version = "1.0.0"
title = "Example Operator Overlay"
description = "Team defaults and verification policy overlay."
publisher = "operator"
trust = "operator"
priority = 100
license = "Apache-2.0"
requires_skm = ">=0.1.0,<1"

[config]
"runtimes.preference" = ["codex", "claude_code"]
"execution.work_policy.role_intensity" = { executor = "heavy", reviewer = "heavy" }

[[overrides]]
kind = "prompt_block"
key = "shared/work_policy"
reason = "Add team-specific verification checklist on top of core work policy."
```

## Configuration Fragments (`[config]`) & No-Cycle Guarantee

An overlay's `[config]` table contributes a `Level.PACK` layer to configuration resolution:

1. **Layer Precedence**:
   `default` -> `pack` (ordered by ascending `(priority, slug)`, so higher priority wins) -> stored scopes (`instance` -> `workspace` -> `project` -> `plan` -> `run`) -> `invocation` (`env` -> `--config` -> `--set`).
2. **No Configuration Cycle**:
   `extensions.packs.enabled`, `extensions.packs.versions`, and `extensions.packs.priority` carry catalog flag `K` (`pack = false`). `PostgresPackConfigSource` resolves those selection keys using only `default`, stored scope entries, and `invocation` layers — never `pack` layers — before selecting active pack versions. A pack cannot enable itself, pin pack versions, or alter pack priorities.
3. **Trust & Security Boundaries (S26)**:
   - Only `builtin` and `operator` packs may carry `[config]`. Installing a `third_party` pack with `[config]` is rejected with `SCHEMA_INVALID` (`reason = "config_fragment_not_allowed_for_third_party"`), and `PostgresPackConfigSource` ignores `third_party` fragments even if present in storage.
   - Ceiling and isolation keys (flag `K`, `pack = false` — such as `policy.ceiling.*`, `runtimes.config_isolation.required`, and `context.inherit_user_global`) and `SECRET` keys are rejected at install time with `CONFIG_SCOPE_NOT_ALLOWED` and stripped by `PostgresPackConfigSource`.
   - Narrowing keys (such as `context.max_total_tokens`) still obey monotonic narrowing across layers and cannot widen a lower ceiling.

## Priorities and Deterministic Tie-Breaking

Default manifest priorities by trust tier:

| Trust Tier | Default `priority` | May Provide `[config]` | Override Capability |
|---|---:|---|---|
| `operator` | `100` | Yes | May override `operator`, `builtin`, and `third_party` when declared in `[[overrides]]` |
| `builtin` | `0` | Yes | May override `builtin` and `third_party` when declared in `[[overrides]]` |
| `third_party` | `-100` | No (S26) | Never overrides `builtin` or `operator` |

- **Instance priority override**: Operators can adjust effective priority without republishing a pack via `extensions.packs.priority` (for example, `{"team-base": 100, "personal-overlay": 200}`).
- **Tie-breaking**:
  - For **resources**, candidates sort by `(-priority, -TRUST_RANK[trust], slug)` — higher priority wins, then higher trust (`operator` > `builtin` > `third_party`), then lexicographically smaller `slug`.
  - For **`[config]` layers**, fragments apply in ascending `(priority, slug)` order — higher priority applies later and wins, with equal-priority ties broken deterministically by `slug`.

## Declaring Resource Overrides (`[[overrides]]`)

When an overlay supplies a `(kind, key)` pair that already belongs to `core` or another pack:

1. Every overridden resource pair **must** be listed in `[[overrides]]` with `kind`, `key`, and a human-readable `reason`.
2. The installing pack's trust rank must be greater than or equal to the strongest existing holder of that resource (`TRUST_RANK[new] >= TRUST_RANK[existing]`).
3. Omitting `[[overrides]]` or attempting to override `builtin`/`operator` from `third_party` fails the entire installation with `Conflict(EXTENSION_OVERRIDE_NOT_DECLARED)`.
4. Agent profiles in an operator pack are still checked against the instance permission ceiling (`policy.ceiling.*`); no profile can widen permissions above the ceiling.

## Connecting a Personal or Team Overlay

1. **Create the overlay directory** with `pack.toml` (`trust = "operator"`) and at least one resource file (for example `prompts/...`, `steering/...`, `skills/...`, or `agent-profiles/...`).
2. **Install the overlay** as an operator:
   ```bash
   skm ext install --path /path/to/my-overlay --trust operator
   ```
3. **Enable the overlay** at the desired scope (`instance`, `workspace`, or `project` — `extensions.packs.enabled` merges by `union`, keeping `core` active automatically):
   ```bash
   skm config set extensions.packs.enabled '["my-overlay"]' --scope workspace:<workspace_id>
   ```
4. **(Optional) Pin version constraints or adjust priorities** when stacking multiple overlays (for example, a personal overlay at `priority = 200` over a team overlay at `priority = 100`):
   ```bash
   skm config set extensions.packs.versions '{"my-overlay": ">=1.0.0,<2.0.0"}' --scope workspace:<workspace_id>
   skm config set extensions.packs.priority '{"team-overlay": 100, "my-overlay": 200}' --scope instance:<instance_id>
   ```
5. **Verify provenance** with explain:
   ```bash
   skm config explain --scope workspace:<workspace_id>
   ```
   Active overlay contributions appear as `level = "pack"` with `pack_id` and `pack_priority`, showing which keys won or were shadowed by scope-level settings.
