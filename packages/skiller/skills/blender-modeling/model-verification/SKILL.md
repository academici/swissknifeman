---
name: model-verification
bucket: blender-modeling
version: 0.1.0
description: "Verify complete parametric Blender models with ordered provenance, config, inventory, evaluated-mesh, interface, visual-evidence, restore, and report gates. Use when preparing release/export, auditing every printable part and mating context, or checking changes to geometry or config."
risk: write
persona: oss-dev
tags: [blender, cad, verification, evidence, release, fdm, sla]
requires: [mcp-blender, model-rules, parametric-config]
produces_for: [build-loop]
outputs: ["models/{model}/test/artifacts/verification/current/"]
snippets: []
adapters: [claude, cursor, fable]
sha256: ""
---

# Model verification

Verify a complete model through one portable lifecycle and one model-local
instruction. Keep capture mechanics generic; keep inventory, interfaces, views,
expected observations, thresholds, printer facts, and blockers model-local.

## Load the model contract

1. Read the active model and mode through the project's supported environment loader.
2. Read the model rules, configuration, and model-local verification instruction.
3. Validate that the instruction supplies the fields in
   [references/model-local-template.md](references/model-local-template.md).
4. Stop if no authoritative inventory or interface source exists. Do not reconstruct
   product truth from a capture script or another model.

## Declare the run

- Use `release` for a candidate that may become GREEN.
- Use `diagnostic` only when explicitly continuing after a known or discovered RED.
- Label every diagnostic output `diagnostic-red`; never promote it.
- Preserve dirty candidates as `candidate-uncommitted`; never call them committed releases.

## Execute the ordered lifecycle

Do not reorder or substitute later evidence for earlier gates.

1. **Provenance/preflight:** resolve and pin the project root, reject foreign imports,
   record model/mode/tool versions/source state, and hash configuration, builders,
   inventory, local instruction, runner, shared skill/template, and every other declared input.
2. **Plain-Python gates:** run configuration, derivation, inventory-schema, and
   cross-part checks before capture.
3. **Default production build:** build through the normal entry point in full/default
   mode and compare the exact owned final universe with the model inventory.
4. **Evaluated mesh and interfaces:** measure every final printable object and every
   real interface in evaluated world space with config-owned tolerances. Reject bbox-only
   fit claims and unchecked mirrors or siblings.
5. **Isolated views:** capture readable primary and oblique technical views for every
   final object; add detail/underside/interface views required by the local instruction.
6. **Assembly contexts:** expose only each target and its real counterparts in the
   prescribed technical, xray, or section view. Treat cut/section display as supplemental,
   never as topology, diameter, interface, or export proof.
7. **Expected-vs-observed analysis:** open every required image and record a falsifiable,
   metric-linked observation. Missing, stale, edge-on, occluded, unreadable, or ambiguous
   evidence is RED; screenshots never auto-pass themselves.
8. **Report and restore:** emit one evidence-linked row per required step, retain all
   owner gates and physical non-claims, restore scene/viewport state in `finally`, and
   verify restoration before computing the aggregate verdict.

A release run stops before costly capture when provenance, plain-Python, inventory, or
evaluated-mesh gates are RED. A requested diagnostic run may continue to collect evidence,
but its aggregate remains RED.

## Protect evidence state

- Write routine evidence only to the exact model-owned
  `test/artifacts/verification/current/` directory.
- Resolve the path, reject symlinks and escapes, and delete only the validated `current/`
  directory. Never delete a parent, glob, unresolved variable, or another model's data.
- Write an open manifest immediately after recreation. Record hashes, versions, run class,
  actual build mode, required ids, candidate state, artifact paths, and restore result.
- Mark evidence stale when any relevant source hash, tool version, mode, scale, profile,
  or local contract input changes.
- Before report closure or promotion, revalidate every required step id, artifact path,
  artifact hash, coverage row, source hash, and restore result against the open manifest.
- Promote only through a separate explicit command to a new non-existing baseline id.
  Refuse diagnostic, stale, incomplete, restoration-failed, or non-GREEN runs.

## Preserve transactional boundaries

Before capture, save object/collection visibility, selection, active object, scene,
camera, every affected viewport, projection, lens/clipping, shading, overlays, xray, and
local-view state. Isolate only declared context. Remove temporary measurement datablocks
and restore saved state in `finally`. Treat incomplete restoration as aggregate RED.

## Compute the verdict

Use per-step `GREEN`, `RED`, `BLOCKED`, or `NOT_RUN`. Aggregate GREEN requires every
required step GREEN, fresh evidence, exact coverage, verified restoration, and no owner
gate misrepresented as verified. Keep physical fit, strength, material behaviour, optical
performance, and print qualification unverified until direct evidence exists.

## Related skills

- `blender-modeling/build-loop` — incremental part work and the entry point for whole-model checks.
- `blender-modeling/model-rules` — model-local construction and camera conventions.
- `blender-modeling/parametric-config` — configuration, derivation, and plain-Python gates.
- `blender/mcp-blender` — Blender execution, viewport, camera, and geometry inspection tools.

<!-- ru-source-sha256: 358e66debc272cb7b238de4ea6e7f4bf9984a3ce733a6a8a948eac729f12a781 -->
