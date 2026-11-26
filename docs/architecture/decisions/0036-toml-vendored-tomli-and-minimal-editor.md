# ADR 0036: TOML: vendored tomli and a minimal verified editor

## Status

Superseded by 0087 (floor 3.11)

## Context

[ADR 0011](0011-toml-for-human-edited-config.md) chose TOML for human-edited files. `tomllib` exists only from Python
3.11 and the minimum is 3.9 with no third-party installs ([ADR 0032](0032-ready-made-or-own-and-non-goals.md)). Writing
a config must not destroy a person's comments and layout.

## Decision

- **Reading.** `aicore.config.toml` uses `tomllib` on Python 3.11 and later and the vendored `tomli` before that;
  tests parse the same fixtures with both. A syntax error becomes `CONFIG_FILE_INVALID` with file and line, and
  `LineIndex` maps key paths to lines for explain and error messages.
- **Vendoring.** `tomli` 2.3.1 is copied byte for byte from the pure-Python wheel into `aicore/_vendor/tomli/` with its
  MIT licence; `VENDORED.json` records the version, the wheel hash and a hash per file, and `tests/test_vendor.py`
  fails on any drift or extra file. Vendored files are never edited. Updating means a new pin, a new wheel hash check
  and a new `VENDORED.json`. The pin is 2.3.x, not 2.4 or later: the 2.3 branch implements TOML 1.0, like `tomllib` in
  Python 3.11 to 3.14, while 2.4 and later read TOML 1.1, so a file valid on 3.9 could not be read on 3.12.
- **TOML 1.0 only.** Config files are TOML 1.0. `tomllib` on Python 3.15 or later accepts TOML 1.1, which 3.9 to 3.14
  cannot read; the editor and the generated example write the 1.0 subset, and the README says so. Nothing enforces it
  in code.
- **Writing.** `aicore.config.toml_edit` (`set_value`, `unset_value`) changes one leaf: replaces a one-line value
  keeping indentation and trailing comment, inserts a key into an existing table, or appends a new table. Dotted keys,
  inline tables, arrays of tables and multi-line values are refused with a hint to edit by hand. Every result is parsed
  and compared with the expected document; a mismatch raises `TomlEditError` and nothing is written. File writing,
  backup and atomic replacement belong to the config layer.

## Alternatives considered

- `tomlkit`: rejected, a large dependency for a rare edit.
- `tomli-w`: rejected, it rewrites the file and drops comments.
- `tomli` 2.4 or later: rejected, TOML 1.1 on 3.9 to 3.14 cannot be matched by `tomllib`.
- Requiring Python 3.11: rejected by ADR 0032.

## Consequences

- A file reads the same on Python 3.9 to 3.14.
- The editor covers the shapes the CLI itself writes; any other shape is edited by hand.

## Supersedes

None.
