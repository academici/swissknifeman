# ADR 0044: Instruction overlays are resolved at run time

## Status

Accepted

## Context

ADR 0006 allowed weaving overlays in when projections are generated. A shared projection (a marketplace plugin, a file
in the repository) would then carry one person's private text.

## Decision

- **Runtime resolution.** `aicore.ext.overlays.resolve_overlays("<module>:<slot>")` reads the files of the slot from
  `[aicore.overlays]` in layer order. The slot must be in `provides.overlay_slots` of the module (`OVERLAY_SLOT_UNKNOWN`
  otherwise); the texts are limited to 32 KiB (`OVERLAY_TOO_LARGE`); a missing file is a warning (`OVERLAY_MISSING`);
  an unreadable or non-UTF-8 file, or one outside the project named by the project layer, is skipped
  (`OVERLAY_INVALID`).
- **Rendering.** `render_overlays` returns one marked block. A command calls `<cli> overlays <slot>` or
  `aicore ext overlays <slot>`.
- **Static embedding** is allowed only in projections generated into a project or onto a machine (vendored copies for
  Codex, Grok, Cursor), never in shared plugin projections or repository artifacts.

## Alternatives considered

- Always embed at generation: rejected, private text would reach shared outputs.
- Only runtime, no embedding: rejected, vendored runtimes cannot always call a command.

## Consequences

- Shared outputs stay free of personal text; a command has to call for its overlays.
- The planner adopts the command in its own phase.

## Supersedes

Refines ADR 0006.
