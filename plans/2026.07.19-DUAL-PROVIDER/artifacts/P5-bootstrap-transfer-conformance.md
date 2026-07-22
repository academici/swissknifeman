# P5 bootstrap-transfer lifecycle conformance

**Scope:** P5.8 supplies the D104 native Codex observer fragment and its handler input only.
No root, P2 admission/lock, P6 deploy source, live apply, repair, P7, FOREMAN, fleet, tag or
push action is part of this evidence.

## P5-owned contribution

`codex_d104_observer_fragment()` returns exactly one `context.observer` native `SessionStart`
registration for `.codex/hooks.json` and the generated `.codex/hooks/lifecycle.py` bytes.
The P6 caller remains the owner of the existing memory registration and of composition.

`validate_d104_codex_lifecycle_composition()` parses a P6-composed document before P2
planning. It accepts exactly two distinct command registrations under `SessionStart`: the
caller-supplied original memory command and the generated P5 observer command. It refuses an
unknown event, missing/duplicate memory, duplicate observer, malformed registration or a
target other than `.codex/hooks.json`.

## Compatibility boundary

The ordinary `block_codex_observer` path is unchanged. A temporary root seeded with the
literal D103 preimage remains an ownership conflict; dry planning neither changes
`.codex/hooks.json` nor creates `.codex/hooks/lifecycle.py`. The transfer admission stays
exclusive to the D104 P2 public seam and its later P6 caller.
