---
name: model-rules
bucket: blender-modeling
version: 0.1.0
description: "Use for model work: read its existing models/{name}/ai/rules.md for construction, axes, interfaces and scoped verification. Use the short template only for a new model."
risk: write
persona: oss-dev
tags: [blender, template, rules, 3d, cad, conventions]
requires: []
produces_for: [build-loop]
outputs: []
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Model-local contract entrypoint

Resolve the active model through the project loader, then read its existing
`models/{name}/ai/rules.md` and relevant construction/verification documentation.
Do not rewrite an existing model's rules to fill every section of a generic
template. The current owner instruction determines authorized construction/scope.

For a new model, document only its actual constraints and point to their SSOT:

- Shape, axes, symmetry and coordinate conventions.
- Accepted parts/assembly and interfaces; link the inventory and physical configs.
- Non-obvious dependency or build ordering needed to preserve those interfaces.
- Supported entrypoints, changed-zone checks and full acceptance/export contract.
- Ownership/cleanup and camera API, including handling of offset objects.
- Cut/section semantics when applicable; production geometry remains full.
- Printed-thread rules only if printed threads exist.

Keep numerical catalogs, part counts and test history in their config/inventory/
evidence sources. A changed constraint updates the relevant rule or link; ordinary
size changes do not require copying dimensions into rules. Camera framing comes
from current world geometry rather than a second stale list of fixed coordinates.

Shared configuration, layer, scene and build mechanics belong to
`config-conventions`, `parametric-config`, `scene-conventions` and `build-loop`.
