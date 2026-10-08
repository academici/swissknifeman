# core — common package foundation

**What is this.** stdlib-only monorepo foundation package: a single source of truth for primitives that
packages (`skiller`/`harness`/`maind`/`analyst`) have historically been copied independently. Connects via
PYTHONPATH (without pip); `Env` of each package inherits `core.BaseEnv`, import - `from core import …`.

**When to touch.** When a primitive is duplicated between ≥2 packets with a stable boundary - his place
here, not parallel copies. Domain add-ons (path-property `Env` of each package) remain in
`common.py` packages - they are at odds with the contract.

## What's inside

| Module | Gives |
|:--|:--|
| `term` | `die` · `warn` · `confirm` · `now_iso` · `parse_iso` |
| `text` | `parse_frontmatter` · `parse_inline_list` · `sanitize` (slug) |
| `env` | `BaseEnv` (frozen-dataclass core root/cmd/home) · `HOME` |
| `io` | `atomic_write_text/json` (tmp+`os.replace`) · `safe_load_json` · `load_json_db` · `read_ndjson` · **`backup_file`** |
| `repo` | `find_repo_root` · `find_monorepo_root` · **`sibling_bin`** (neighbor's launcher resolver) |
| `block` | managed markdown-block: `managed_block` · `upsert_block` · `content_hash` |
| `http` | urllib-client: `http_get_json` · `http_post_json` · `ping` |
| `cli` | `parse_flags` · `parse_args` · `run_cmd` (guarded subprocess) |
| `paths` | `is_within` · `is_within_lexical` · `state_dir` |
| `project` | `PROJECT_TYPES` · `detect_project_type` · docs-visibility |
| `pathology` | `detect` — detector «pathologies» run (common for `maind analyze` and `analyst digest`) |
| `usage` | token accumulator/usage run (`new_acc`/`feed_event`/`finish`) |
| `proc` · `runs` | `pid_alive` · `find_run_report` |
| **`provider/`** | domain subpackage of the provider model: `values` · `config` · `manifest` · `artifact` · `lock` · `registry` (see below) |

### Subpackage `provider/`

Single domain cluster `packages/aicore/lib/aicore/provider/` (`core.provider` is a compatibility alias) — six modules connected by mutual imports and common
dictionary (other modules are flat: the domain subpackage is started when ≥3 modules linked
MUTUAL imports and share the domain dictionary, «similar in topic» — not a criterion).

| Module | Gives |
|:--|:--|
| `provider.values` | domain values and enum's: `ProviderId` · `CapabilityId` · `SupportLevel` · `ProviderDecision` · `EffectiveProvider` |
| `provider.config` | layers and provider configuration resolution: `ProviderConfigCatalog` · `resolve_provider_config` · `effective_projection` |
| `provider.manifest` | parsing and canonicalization of the capabilities manifest: `load_provider_manifest` · `provider_manifest_sha256` · `provider_support_projection` |
| `provider.artifact` | planning the rendering of the artifact and its provenance: `plan_artifact_render` · `canonical_json_bytes` · `sha256_digest` |
| `provider.lock` | lock-managed artifact file and plan application: `plan_artifact_lock` · `apply_plan` · `artifact_dry_run` · `parse_lock` |
| `provider.registry` | adapter registry and selection from the catalog: `AdapterCatalog` · `AdapterDescriptor` · `AdapterSelection` |

Re-exports to `packages/aicore/lib/aicore/provider/__init__.py` NO: `core/__init__.py` is the transitional facade
(`from core import …`), deep-import goes directly to the submodule (`aicore.provider.manifest`, `aicore.artifacts.lock`).

## Reference: run telemetry (SCHEMA=2)

`packages/aicore/lib/aicore/usage.py` — a single accumulator of tokens on which all telemetry is based. Capture run
does SessionEnd-hook harness (`hooks/run-report/`): parses the transcript line by line → writes
`<project>/.claude/runs/<sid>.json` (**SCHEMA=2**: tests/lint/files/tool-failures/dev-loop-signal +
usage-partition in/out by model). This run-report read:

- **`maind analyze`** — post-run verdict GREEN/ATTENTION/RED (did the agent tug on his memory/graph);
- **`analyst token-report`** — usage-trend + rolling-baseline (`.claude/analyze/baseline.json`);
- **`core.pathology.detect`** — detector of recurrent pathologies (rule ≥2/5 on history run-report).

The operational layer of this is [Development §9](/develop#_9-performance-measurement★).

## Development

```bash
bash packages/aicore/scripts/test.sh                       # aicore tests
PYTHONPATH=. python3 -m unittest discover -s core/tests   # transitional core shim
```
