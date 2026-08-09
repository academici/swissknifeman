<!-- instruction:skiller.identity -->
## skiller.identity
`skiller` is the registry and source of truth for portable AI skills; it distributes skills without becoming the umbrella control layer.
<!-- instruction:skiller.distribution-channels -->
## skiller.distribution-channels
Keep the two distribution channels distinct: `connect` enables a marketplace source, while `vendor`/`sync` delivers managed physical skill copies. The channel is always asked of the user; legacy `vendor --agent` selection remains supported for existing configurations only.
<!-- instruction:skiller.configuration-ownership -->
## skiller.configuration-ownership
Keep `.swissknife.json` for connect and legacy vendor selection separate from `.swissknifeman/config.json` for skill-granular vendor sync. JSON files under `schema/` document these configs for editor DX only; runtime validation stays manual and does not read them as a live contract.
<!-- instruction:skiller.core-policy -->
## skiller.core-policy
Deliver the nine `CORE_SKILLS` by default through the selected channel; `--no-core` is the explicit opt-out and budget reporting remains authoritative. Also, take the resident CORE cost from `skiller budget --check-core`, never from a copied snapshot.
<!-- instruction:skiller.layout-and-generation -->
## skiller.layout-and-generation
Keep skills under `skills/<bucket>/<name>/SKILL.md`; treat `skills.json`, `skills/_index.md`, marketplace manifests, graph, and budget documentation as registry-generated outputs. Also, presets expand before the selection formula `(presets ∪ buckets ∪ include) − exclude`.
<!-- instruction:skiller.module-boundaries -->
## skiller.module-boundaries
Keep skill selection in `config.resolve_selection`, vendor sync in `skillset.do_sync`, and environment preset ownership delegated to `harness`. Also, keep token math in `budget.py` as the single source.
<!-- instruction:skiller.engineering-invariants -->
## skiller.engineering-invariants
Keep `lib/` stdlib-only, pass frozen `Env` explicitly, use Russian diagnostics and merge-only project writes, and edit local skills in the canonical EN-only `SKILL.md` before regenerating registry/provider projections. Also, create a new skill only when it does not overlap an existing one — otherwise extend the existing skill.
<!-- instruction:skiller.validation-release -->
## skiller.validation-release
Before release run `bash scripts/test.sh` and `bash scripts/validate.sh`; after skill or bucket changes run `skiller registry` and use Russian Conventional Commit messages.
