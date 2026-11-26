---
name: model-verification
description: "Use for final digital acceptance, export or a requested whole-model audit of a declared assembly. Covers provenance, inventory, evaluated geometry, interfaces, evidence and restore."
---

# Complete-model acceptance and export verification

Use this lifecycle for final acceptance/export or an explicitly requested audit
of the declared assembly. An ordinary config/geometry edit uses `build-loop` and
checks the changed zone and affected interfaces. The latest owner instruction
and local model contract define required properties; this skill does not add a
full variant matrix or arbitrary flexible-wire pose certificate.

## Load and declare the contract

Resolve the project root, model and mode through its loader. Read the model rules,
configuration and local verification instruction; its fields are described in
[model-local-template](references/model-local-template.md). Inventory, interfaces,
thresholds, printer facts, required views and physical claims stay model-local.
An absent authoritative inventory/interface source prevents a complete acceptance
claim; independent work with known inputs may continue within the authorized scope.

Declare a release candidate or diagnostic run before collecting evidence. Dirty
source is `candidate-uncommitted`, not a committed release. A diagnostic collected
after RED keeps its diagnostic-red result; correcting the source requires fresh
applicable gates rather than promoting that failed run.

## Ordered lifecycle

1. **Provenance/preflight:** pin root and loaded paths; record model/mode/tool
   versions, source/config state and hashes of declared build/acceptance inputs.
2. **Pure gates:** configuration, derivation, inventory schema and cross-part checks
   before building/capture.
3. **Production build/inventory:** normal entrypoint in full/default mode; exact
   owned final universe matches its SSOT. Preserve foreign objects outside that
   universe; leaked tools or undeclared owned output remain failures.
4. **Geometry/interfaces:** evaluated post-operation world-space measurements of
   every final printable object and required real interface, with config-owned
   tolerances. Check non-empty/nondegenerate geometry, documented components,
   sane volume, actual boundary/self-intersection defects and required walls.
   Preserve closed-cavity winding and nonzero small faces; bbox-only fit,
   unchecked copies or a pretty render are insufficient.
5. **Views/context:** readable technical and mating-context views needed for each
   required printable part/property. Bought references support their declared
   placement/interface checks; do not require separate views or tool calls for
   every repeated reference merely because it is a mesh. Section/cut is supplemental,
   never production topology/diameter/export proof.
6. **Observed evidence:** inspect every required image and write a falsifiable
   observation linked to its measured property. Missing, stale, occluded, edge-on
   or ambiguous required evidence does not pass.
7. **Report/restore:** one evidence-linked result per declared step; keep unknown
   inputs and physical non-claims explicit. Restore scene/viewport in `finally`
   and verify restoration before the aggregate verdict.

A failed provenance/pure/inventory/geometry gate stops expensive release capture.
An authorized diagnostic may collect additional evidence while keeping RED. A
failed build is fixed and retried within the task; this lifecycle adds no approval
request for routine reversible correction.

## Evidence and scene integrity

Use the model's declared evidence paths. Validate the exact output directory;
reject symlinks/escapes and never delete a parent, glob or another model's data.
Open a manifest before collection, recording candidate/run class, required IDs,
inputs, artifacts and restore status. Changes to relevant source/tool/mode/scale/
profile or acceptance input invalidate dependent evidence. Closure rechecks required
coverage, artifact bytes/hashes, input freshness and restoration.

Capture through an existing transaction where available: object/collection
visibility, selection, active object, scene, camera, affected viewports, projection,
lens/clipping, shading/overlays/xray/local view, and temporary measurement datablocks
must return to their prior state. Failure to restore is RED. One operator owns a
shared live scene; isolated background runs must restore their source scene too.

Promotion is a separate explicit command to a new baseline ID and refuses
incomplete, diagnostic, stale, restoration-failed or non-GREEN evidence. Reuse
prior measurements only through the local verified identity/freshness contract;
a sibling or old variant passing is not evidence for changed geometry.

Use per-step `GREEN`, `RED`, `BLOCKED` or `NOT_RUN`. Aggregate GREEN covers only the
required, measured scope with fresh complete evidence and verified restoration.
Unknown physical source dimensions are not manufacturer facts; a geometric design
reservation stays labelled. Physical fit, strength, material behaviour, optics and
print qualification require their own evidence and remain unverified until then.
