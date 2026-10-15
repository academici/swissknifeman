# Research sources

`[orch.research]` names where the researcher role and `orch.py research query` look things up (PLAN4 P10.1). Adapters
live in `orch.research.sources`; they use the standard library only.

## Configuration

| Key | Value | Default | Layers | Meaning |
|---|---|---|---|---|
| `research.policy` | `required`, `conditional`, `off` | `conditional` | all | when a piece of work gets a research stage: every piece, only a piece whose research need is `required`, or never (the stage itself arrives with the researcher role) |
| `research.sources.<id>.kind` | `command`, `filesystem`, `mcp-stdio` | none (required) | all | adapter of the source; `http` and `vector` do not exist yet |
| `research.sources.<id>.argv` | array of strings | empty | defaults, machine, invocation, flags | command line of a `command` or `mcp-stdio` source; a leading `~` is expanded |
| `research.sources.<id>.tool` | string | `search` | all | `mcp-stdio`: the tool that receives the query |
| `research.sources.<id>.roots` | array of paths | empty | all | `filesystem`: folders searched (absolute, `~…`, or relative to the project) |
| `research.sources.<id>.capabilities` | array of `search`, `citations`, `synthesis`, `deep` | empty | all | what the source can do |
| `research.sources.<id>.timeout_s` | integer | `600` | all | ceiling on one query |
| `research.sources.<id>.concurrency` | integer | `1` | all | queries of the source that run at once in one orch process |
| `research.sources.<id>.order` | integer | `100` | all | place on the ladder: lower first, ties by id |

`argv` chooses the process orch starts, so a project file cannot set it (`CONFIG_LAYER_FORBIDDEN`); a project file may
set `policy`, `roots` and the limits. An `<id>` is lowercase words joined by `-`.

## Adapters

All adapters answer `{source, text, sources, raw_ref}`: the text, the URLs or paths it rests on, and the sha256 of the
raw reply (`sha256:<hex>`).

- `command`: `argv` is started, the query goes to its stdin, a JSON object `{"text": str, "sources": [str]}` is read
  from stdout.
- `filesystem`: a read-only walk of `roots` (symlinks, `.git`, `node_modules`, files over 1 MB and non-UTF-8 files are
  skipped); a line that contains the whole query (case-insensitive) is a match, at most 50 are returned as
  `path:line: text`, `sources` lists the files.
- `mcp-stdio`: a generic JSON-RPC client over the stdio of a server: `initialize` → `notifications/initialized` →
  `tools/call {name: tool, arguments: {query}}`. Lines of the server that are not JSON are skipped. `sources` are the
  URLs found in the text. The message shape follows `docs/research/tools/pplx_stdio.py`.

A reply with `BROWSER_BUSY` (or an MCP error that says so) and a query that exceeds `timeout_s` are asked again by
`retry.decide` (`rate_limit` and `timeout` classes) up to 3 times, with a wait of 5, 10, 15 seconds for a busy answer;
after that, and for every other failure, the result is `SOURCE_UNAVAILABLE`. `concurrency` is held inside one process;
another process (a second conductor) is not counted, so the server's own `BROWSER_BUSY` and the repeats remain the
guard.

Codes: `SOURCE_UNKNOWN`, `SOURCE_INVALID` (no `argv` or `roots`, no `kind`), `QUERY_EMPTY`, `SOURCE_UNAVAILABLE`.

## Command line

```
orch.py research sources [--json]
orch.py research query --source ID --query-file FILE [--json]
```

`sources` lists the policy and the sources on the ladder. `query` prints the text and one `source:` line per source, or
the answer as JSON. A failure prints `CODE: message` to stderr and exits 1.

## Example: Perplexity (machine file)

The MCP server `perplexity-web-mcp` is a stdio server; it answers `BROWSER_BUSY` when no browser tab is free, hence
`concurrency = 1` and the repeats. Put this in `$SKM_HOME/config/config.toml`, never in a project file:

```toml
[orch.research.sources.perplexity]
kind = "mcp-stdio"
argv = ["~/projects/packages/perplexity-web-mcp/start.sh"]
tool = "search"
capabilities = ["search", "citations", "synthesis"]
order = 1
timeout_s = 600
concurrency = 1
```

For a deep search add a second source with `tool = "search_deep"`, `capabilities = ["deep"]` and a higher `order`.
