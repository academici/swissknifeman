# ADR 0011: TOML for human-edited configuration layers, JSON for generated state

## Status

Accepted

## Context

The layered configuration needs a file format that people edit by hand, with comments, using only the standard
library.

## Decision

The machine layer `~/.config/swissknifeman/config.toml` and the project layer `<project>/.swissknifeman/config.toml`
are TOML, read with `tomllib` (Python 3.11 or newer). JSON is used for generated state, lock files and module
defaults. Each module ships `config.example.toml` generated from its schema and defaults; CI checks drift, and
`swissknifeman config init` copies it into a layer. `config set` uses a small writer for the subset of TOML the
schemas need.

## Alternatives considered

- JSON everywhere: no comments.
- YAML: needs a third-party parser.

## Consequences

- Layer locations from ADR 0005 are unchanged; only the file format of layers 2 and 3 changes.
- Python 3.11 becomes the minimum for the configuration layer.

## Supersedes

Refines ADR 0005.
